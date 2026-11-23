"""Run isolated authentication checks against a temporary SQLite database.

No real LeadPilot SQLite file is read or modified.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
with tempfile.TemporaryDirectory(prefix='leadpilot-auth-tests-') as temp:
    os.environ['LEADPILOT_DATABASE_URL'] = 'sqlite:///' + (Path(temp) / 'auth_test.sqlite3').as_posix()
    from fastapi import FastAPI
    from leadpilot_ai.crm_store import engine
    from fastapi.testclient import TestClient
    from starlette.middleware.base import BaseHTTPMiddleware
    from sqlalchemy import select
    from leadpilot_ai.auth_api import (
        router, auth_middleware, create_operator, Operator, OperatorSession,
        SessionLocal, hash_password, verify_password, _failures,
    )
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)

    @app.get('/health')
    def health(): return {'alive': True}

    @app.get('/api/private')
    def private(): return {'protected': True}

    @app.post('/api/private')
    def private_post(): return {'written': True}

    checks = 0
    def check(condition, label):
        global checks
        assert condition, 'FAILED: ' + label
        checks += 1

    with TestClient(app) as client:
        check(client.get('/health').status_code == 200, 'public health')
        check(client.get('/api/private').status_code == 401, 'deny unauthenticated GET')
        check(client.post('/api/private').status_code == 401, 'deny unauthenticated POST')
        check(client.get('/docs').status_code == 401, 'deny docs without login')
        check(client.get('/api/auth/setup-status').json()['setup_complete'] is False, 'setup not ready')
        check(client.post('/api/auth/login', json={'username':'owner','password':'incorrect-secret'}).status_code == 401, 'incorrect login')
        check(verify_password('very-good-secret-123', hash_password('very-good-secret-123')), 'pbkdf2 password verification')
        create_operator('owner', 'very-good-secret-123')
        check(client.get('/api/auth/setup-status').json()['setup_complete'] is True, 'setup completed')
        try:
            create_operator('other', 'another-long-secret')
        except ValueError: pass
        else: raise AssertionError('second account not blocked')
        checks += 1
        result = client.post('/api/auth/login', json={'username':'owner','password':'very-good-secret-123'})
        check(result.status_code == 200, 'login')
        check('httponly' in result.headers['set-cookie'].lower() and 'samesite=strict' in result.headers['set-cookie'].lower(), 'cookie flags')
        check(client.get('/api/auth/me').json()['user']['username'] == 'owner', 'identity')
        check(client.get('/api/private').status_code == 200, 'authenticated GET')
        check(client.post('/api/private').status_code == 200, 'authenticated POST')
        check(client.post('/api/private',headers={'Origin':'https://evil.example'}).status_code == 403,'reject cross-site Origin')
        check(client.post('/api/private',headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403,'reject cross-site fetch metadata')
        check(client.post('/api/auth/change-password',json={'current_password':'wrong','new_password':'another-good-secret123'}).status_code == 403,'change password requires old password')
        cookie = client.cookies.get('leadpilot_session')
        check(client.post('/api/auth/logout').status_code == 200, 'logout')
        check(client.get('/api/private').status_code == 401, 'logout invalidates old token')
        client.cookies.set('leadpilot_session', cookie)
        check(client.get('/api/private').status_code == 401, 'revocation even if cookie replayed')
        client.cookies.clear()
        check(client.post('/api/auth/login',json={'username':'owner','password':'very-good-secret-123'}).status_code == 200,'relogin')
        check(client.post('/api/auth/change-password',json={'current_password':'very-good-secret-123','new_password':'another-good-secret123'}).status_code == 200,'password change')
        check(client.get('/api/private').status_code == 401,'password change revokes sessions')
        check(client.post('/api/auth/login',json={'username':'owner','password':'very-good-secret-123'}).status_code == 401,'old password invalid')
        check(client.post('/api/auth/login',json={'username':'owner','password':'another-good-secret123'}).status_code == 200,'new password works')
        with SessionLocal() as db:
            sess = db.scalar(select(OperatorSession))
            sess.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            db.commit()
        check(client.get('/api/private').status_code == 401,'expired sessions cannot access data')
        with SessionLocal() as db:
            check(db.scalar(select(Operator)) is not None,'operator persisted')
        check(create_operator('owner','reset-password-secure1',reset=True).startswith('Password reset'),'local admin reset')
    # Windows cannot remove an open SQLite file. Dispose pooled connections
    # while the temporary directory still exists, before its cleanup begins.
    engine.dispose()
    print(f'PASS: {checks} isolated authentication checks (temporary SQLite only)')
