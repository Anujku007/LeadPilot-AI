"""Local LeadPilot operator authentication (single shared-workspace MVP).

Protects all FastAPI /api/* routes except login and setup status. Sessions use
random HTTP-only cookies; only SHA256 token digests are persisted. No passwords,
raw session tokens or CRM records are logged by this module.
"""
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from .crm_store import Base, SessionLocal, engine, utcnow

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/auth', tags=['Operator Authentication'])
COOKIE = 'leadpilot_session'
SESSION_HOURS = 12
ITERATIONS = 600_000
USER_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_.-]{2,49}$')
ALLOWED_PUBLIC = {'/api/auth/login', '/api/auth/setup-status'}
# Only known local frontend origins are permitted to initiate state-changing
# cookie-authenticated requests. For HTTPS deployments set LP_AUTH_ORIGINS.
DEFAULT_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8001,http://localhost:8001'
ORIGINS = {s.strip().rstrip('/') for s in os.environ.get('LP_AUTH_ORIGINS', DEFAULT_ORIGINS).split(',') if s.strip()}
ATTEMPT_WINDOW = 600  # seconds
MAX_FAILURES = 8
_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


class Operator(Base):
    __tablename__ = 'lp_auth_operators'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OperatorSession(Base):
    __tablename__ = 'lp_auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('lp_auth_operators.id'), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


Operator.__table__.create(bind=engine, checkfirst=True)
OperatorSession.__table__.create(bind=engine, checkfirst=True)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def valid_password(password: str):
    return isinstance(password, str) and 12 <= len(password) <= 128 and not password.isspace()


def hash_password(password: str, *, salt: bytes | None = None):
    if not valid_password(password):
        raise ValueError('Use a password of 12–128 characters.')
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str):
    try:
        alg, iterations, salt_hex, digest_hex = stored.split('$')
        rounds = int(iterations)
        if alg != 'pbkdf2_sha256' or not 100_000 <= rounds <= 1_000_000:
            return False
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        calculated = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, rounds)
        return hmac.compare_digest(calculated, digest)
    except (ValueError, TypeError, AttributeError):
        return False


def create_operator(username: str, password: str, *, reset=False):
    """CLI only: no web self-registration or unauthenticated password reset."""
    from uuid import uuid4
    username = (username or '').strip().lower()
    if not USER_PATTERN.fullmatch(username):
        raise ValueError('Username must start with a letter, 3–50 letters/numbers/._-')
    if not valid_password(password):
        raise ValueError('Use a password of 12–128 characters.')
    with SessionLocal() as db:
        existing = db.scalar(select(Operator).where(Operator.username == username))
        count = db.scalar(select(func.count()).select_from(Operator)) or 0
        if existing:
            if not reset:
                raise ValueError('Operator already exists. Use --reset only for a local password reset.')
            existing.password_hash = hash_password(password)
            db.execute(delete(OperatorSession).where(OperatorSession.user_id == existing.id))
            db.commit()
            return 'Password reset and existing sessions revoked.'
        if count:
            raise ValueError('This local MVP supports one shared-workspace operator. Reset the existing account instead.')
        if reset:
            raise ValueError('Cannot reset a non-existent operator.')
        db.add(Operator(id=str(uuid4()), username=username, password_hash=hash_password(password)))
        db.commit()
        return 'Operator account created.'


def _session_user(raw_token: str | None):
    if not raw_token or len(raw_token) < 30 or len(raw_token) > 200:
        return None
    digest = hashlib.sha256(raw_token.encode('ascii', errors='ignore')).hexdigest()
    with SessionLocal() as db:
        session = db.get(OperatorSession, digest)
        if session is None or _utc(session.expires_at) <= datetime.now(timezone.utc):
            return None
        op = db.get(Operator, session.user_id)
        if op is None: return None
        from .team_access import role_for_operator
        role = role_for_operator(db, op.id)
        return {'id': op.id, 'username': op.username, 'role': role} if role else None


def _ip(request: Request):
    return request.client.host if request.client else 'local'


def _rate_limited(ip: str):
    now = time.monotonic()
    with _failures_lock:
        recent = [t for t in _failures.get(ip, []) if now - t < ATTEMPT_WINDOW]
        _failures[ip] = recent
        return len(recent) >= MAX_FAILURES


def _failed(ip: str):
    now = time.monotonic()
    with _failures_lock:
        _failures[ip] = [t for t in _failures.get(ip, []) if now-t < ATTEMPT_WINDOW] + [now]


def _passed(ip: str):
    with _failures_lock:
        _failures.pop(ip, None)


def _check_origin(request: Request):
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return True
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') not in ORIGINS:
        return False
    # SameSite=Strict blocks cross-site cookie submission; reject cross-site
    # Fetch Metadata even if the Origin header is missing.
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return False
    return True


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    protected = path.startswith('/api/') or path in ('/docs', '/redoc', '/openapi.json')
    if not protected:
        return await call_next(request)
    if not _check_origin(request):
        return JSONResponse({'detail': 'Request origin is not allowed'}, status_code=403, headers={'Cache-Control': 'no-store'})
    if path in ALLOWED_PUBLIC:
        return await call_next(request)
    operator = _session_user(request.cookies.get(COOKIE))
    if operator is None:
        return JSONResponse({'detail': 'Please sign in to LeadPilot AI'}, status_code=401, headers={'Cache-Control': 'no-store'})
    request.state.operator = operator
    if operator['role'] == 'sales':
        from .team_access import request_is_scoped
        if not request_is_scoped(path, request.method, operator['id']):
            return JSONResponse({'detail': 'This record is not assigned to your account'}, status_code=403, headers={'Cache-Control': 'no-store'})
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


def _cookie(response: Response, token: str, request: Request):
    secure = os.getenv('LP_AUTH_COOKIE_SECURE', '').strip().lower() in ('1', 'true', 'yes') or request.url.scheme == 'https'
    response.set_cookie(COOKIE, token, max_age=SESSION_HOURS*3600, path='/', httponly=True, secure=secure, samesite='strict')


def _remove_cookie(response: Response):
    response.delete_cookie(COOKIE, path='/', samesite='strict')


@router.get('/setup-status')
def setup_status():
    with SessionLocal() as db:
        exists = (db.scalar(select(func.count()).select_from(Operator)) or 0) > 0
    return {'setup_complete': exists, 'registration_open': False}


@router.post('/login')
def login(body: LoginRequest, response: Response, request: Request):
    ip = _ip(request)
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail='Too many login attempts. Try again later.')
    username = body.username.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(Operator).where(Operator.username == username))
        # Avoid a fast timing oracle on unknown usernames.
        valid = verify_password(body.password, user.password_hash) if user else verify_password(body.password, _DUMMY_HASH)
        if not user or not valid:
            _failed(ip)
            raise HTTPException(status_code=401, detail='Incorrect username or password')
        from .team_access import role_for_operator
        role = role_for_operator(db, user.id)
        if role is None:
            _failed(ip)
            raise HTTPException(status_code=401, detail='Incorrect username or password')
        _passed(ip)
        token = secrets.token_urlsafe(48)
        db.add(OperatorSession(
            token_hash=hashlib.sha256(token.encode('ascii')).hexdigest(),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc)+timedelta(hours=SESSION_HOURS),
        ))
        db.commit()
        result = {'authenticated': True, 'user': {'id': user.id, 'username': user.username, 'role': role}}
    _cookie(response, token, request)
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/me')
def me(request: Request):
    return {'authenticated': True, 'user': request.state.operator}


@router.post('/logout')
def logout(request: Request, response: Response):
    raw_token = request.cookies.get(COOKIE)
    if raw_token:
        with SessionLocal() as db:
            db.execute(delete(OperatorSession).where(OperatorSession.token_hash == hashlib.sha256(raw_token.encode('ascii', errors='ignore')).hexdigest()))
            db.commit()
    _remove_cookie(response)
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': False}


@router.post('/change-password')
def change_password(body: PasswordChange, request: Request, response: Response):
    if not valid_password(body.new_password):
        raise HTTPException(status_code=422, detail='Use a password of 12–128 characters.')
    with SessionLocal() as db:
        user = db.get(Operator, request.state.operator['id'])
        if not user or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status_code=403, detail='Current password is incorrect')
        user.password_hash = hash_password(body.new_password)
        db.execute(delete(OperatorSession).where(OperatorSession.user_id == user.id))
        db.commit()
    _remove_cookie(response)
    return {'success': True, 'message': 'Password changed. Please sign in again.'}


# Precomputed dummy hash with a fixed random-looking salt, to keep invalid
# usernames from bypassing the deliberately expensive KDF path.
_DUMMY_HASH = hash_password('not-an-actual-password-0', salt=bytes.fromhex('cb81213452dffa84340e52819a659776'))
