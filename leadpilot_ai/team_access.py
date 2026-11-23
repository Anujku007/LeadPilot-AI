"""LeadPilot local RBAC: one admin, limited sales operators, explicit lead assignments.

Existing CRM and authentication tables are unchanged. Every Sales operator must
have an active role record; missing records are denied (fail closed).
"""
import re
from decimal import Decimal
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, ForeignKey, String, select, func, delete
from sqlalchemy.orm import Mapped, mapped_column
from .crm_store import Base, SessionLocal, engine, Conversation, LeadProfile, ChatMessage
from .auth_api import Operator, OperatorSession, hash_password, USER_PATTERN, valid_password

router = APIRouter(prefix='/api/team', tags=['Team and lead assignments'])

class TeamRole(Base):
    __tablename__ = 'lp_team_roles'
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('lp_auth_operators.id'), primary_key=True)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

class LeadAssignment(Base):
    __tablename__ = 'lp_lead_assignments'
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey('lp_conversations.id'), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey('lp_auth_operators.id'), nullable=False, index=True)

TeamRole.__table__.create(bind=engine, checkfirst=True)
LeadAssignment.__table__.create(bind=engine, checkfirst=True)

# One-time safe bootstrap: preserve the sole original local operator as admin.
# Other unclassified operators never gain privileges by default.
with SessionLocal() as db:
    operators = db.scalars(select(Operator).limit(2)).all()
    if len(operators) == 1 and db.get(TeamRole, operators[0].id) is None:
        db.add(TeamRole(user_id=operators[0].id, role='admin', active=True))
        db.commit()


def role_for_operator(db, uid):
    row = db.get(TeamRole, uid)
    if row is None:
        # Support first-time local admin setup after this module was imported.
        # Never infer admin when there is any existing role or multiple operators.
        count_roles = db.scalar(select(func.count()).select_from(TeamRole)) or 0
        count_ops = db.scalar(select(func.count()).select_from(Operator)) or 0
        if count_roles == 0 and count_ops == 1 and db.get(Operator, uid):
            row = TeamRole(user_id=uid, role='admin', active=True)
            db.add(row)
            db.commit()
    return row.role if row and row.active and row.role in ('admin', 'sales') else None


def require_admin(request):
    if request.state.operator.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Administrator access required')


def assigned(db, user_id, conversation_id):
    item = db.get(LeadAssignment, str(conversation_id))
    return item is not None and item.user_id == user_id


def ensure_scope(request: Request):
    op = request.state.operator
    if op['role'] == 'admin':
        return
    if op['role'] != 'sales':
        raise HTTPException(status_code=403, detail='Account is not authorized')
    if not request_is_scoped(request.url.path, request.method, op['id']):
        raise HTTPException(status_code=403, detail='You do not have access to this record')


CONV = re.compile(r'^/api/conversations/([0-9a-fA-F-]{36})(?:/([a-z0-9-]+))?$')
SALES = re.compile(r'^/api/sales/appointments/([0-9a-fA-F-]{36})/(complete|outcome|history)$')
VOICE = {'/api/voice/transcribe', '/api/voice/synthesize'}

def request_is_scoped(path, method, user_id):
    """Allowlist for sales staff, enforced before routing. All other APIs fail closed."""
    if method in ('OPTIONS',):
        return True
    if path in ('/api/auth/me','/api/auth/logout','/api/auth/change-password'):
        return (method == 'GET' and path.endswith('/me')) or (method == 'POST' and not path.endswith('/me'))
    if method == 'GET' and path in ('/api/team/my-leads','/api/team/my-pipeline','/api/appointments/availability'):
        return True
    if method == 'POST' and path in VOICE:
        return True
    m = CONV.fullmatch(path)
    if m:
        cid, action = m.groups()
        allowed = (method == 'GET' and action in (None,'pending-appointment','appointment-options')) or (
            method == 'POST' and action in ('chat','schedule-request','appointment-proposal','confirm-appointment'))
        if not allowed:
            return False
        with SessionLocal() as db:
            return assigned(db, user_id, cid)
    m = SALES.fullmatch(path)
    if m:
        aid, action = m.groups()
        if not ((method == 'GET' and action == 'history') or (method == 'POST' and action == 'complete') or (method == 'PATCH' and action == 'outcome')):
            return False
        from .appointment_booking import Appointment
        with SessionLocal() as db:
            appt = db.get(Appointment, aid)
            return bool(appt and assigned(db, user_id, appt.conversation_id))
    return False


class AddSalesUser(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=12, max_length=128)

class ChangeActive(BaseModel):
    active: bool

class AssignLead(BaseModel):
    user_id: str | None = None

class ResetPassword(BaseModel):
    new_password: str = Field(min_length=12, max_length=128)

@router.get('/operators')
def operators(request: Request):
    require_admin(request)
    with SessionLocal() as db:
        result = []
        for op, r in db.execute(select(Operator, TeamRole).join(TeamRole, TeamRole.user_id == Operator.id).order_by(Operator.username)):
            n = db.scalar(select(func.count()).select_from(LeadAssignment).where(LeadAssignment.user_id == op.id)) or 0
            result.append({'id':op.id,'username':op.username,'role':r.role,'active':r.active,'assigned_leads':n})
        return {'operators':result}

@router.post('/operators', status_code=201)
def add_sales_user(body: AddSalesUser, request: Request):
    require_admin(request)
    username = body.username.strip().lower()
    if not USER_PATTERN.fullmatch(username) or not valid_password(body.password):
        raise HTTPException(status_code=422, detail='Use a 3–50 character username (no spaces), and a password of at least 12 characters')
    with SessionLocal() as db:
        if db.scalar(select(Operator.id).where(Operator.username == username)):
            raise HTTPException(status_code=409, detail='Username is already in use')
        uid = str(uuid4())
        db.add(Operator(id=uid, username=username, password_hash=hash_password(body.password)))
        db.add(TeamRole(user_id=uid, role='sales', active=True))
        db.commit()
        return {'id':uid,'username':username,'role':'sales','active':True}

@router.patch('/operators/{user_id}/active')
def update_user_status(user_id: str, body: ChangeActive, request: Request):
    require_admin(request)
    if user_id == request.state.operator['id']:
        raise HTTPException(status_code=409, detail='Cannot deactivate your own administrator account')
    with SessionLocal() as db:
        row = db.get(TeamRole, user_id)
        if not row or row.role != 'sales':
            raise HTTPException(status_code=404, detail='Sales operator not found')
        row.active = body.active
        if not body.active:
            db.execute(delete(OperatorSession).where(OperatorSession.user_id == user_id))
        db.commit()
        return {'success':True,'active':body.active}

@router.post('/operators/{user_id}/reset-password')
def reset_sales_password(user_id: str, body: ResetPassword, request: Request):
    require_admin(request)
    with SessionLocal() as db:
        row = db.get(TeamRole, user_id)
        op = db.get(Operator, user_id)
        if not row or row.role != 'sales' or not op:
            raise HTTPException(status_code=404, detail='Sales operator not found')
        op.password_hash = hash_password(body.new_password)
        db.execute(delete(OperatorSession).where(OperatorSession.user_id == user_id))
        db.commit()
        return {'success':True,'message':'Password changed and previous sessions revoked'}

@router.get('/leads')
def all_leads(request: Request):
    require_admin(request)
    with SessionLocal() as db:
        rows=[]
        for c in db.scalars(select(Conversation).order_by(Conversation.updated_at.desc()).limit(500)):
            a=db.get(LeadAssignment,c.id)
            lp=db.get(LeadProfile,c.id)
            rows.append({'id':c.id,'assigned_to':a.user_id if a else None,'score':lp.score if lp else None,'category':lp.category if lp else 'New','updated_at':c.updated_at.isoformat() if c.updated_at else None})
        return {'leads':rows}

@router.put('/leads/{conversation_id}/assign')
def assign_lead(conversation_id: str, body: AssignLead, request: Request):
    require_admin(request)
    with SessionLocal() as db:
        if not db.get(Conversation, conversation_id):
            raise HTTPException(status_code=404, detail='Conversation not found')
        current=db.get(LeadAssignment,conversation_id)
        if body.user_id is None:
            if current: db.delete(current)
        else:
            user=db.get(TeamRole,body.user_id)
            if not user or user.role!='sales' or not user.active:
                raise HTTPException(status_code=422, detail='Choose an active salesperson')
            if current: current.user_id=body.user_id
            else: db.add(LeadAssignment(conversation_id=conversation_id,user_id=body.user_id))
        db.commit()
        return {'success':True,'conversation_id':conversation_id,'assigned_to':body.user_id}

@router.get('/my-leads')
def my_leads(request: Request):
    op=request.state.operator
    with SessionLocal() as db:
        ids=db.scalars(select(LeadAssignment.conversation_id).where(LeadAssignment.user_id==op['id'])).all()
        result=[]
        for cid in ids:
            c=db.get(Conversation,cid)
            if not c:continue
            lp=db.get(LeadProfile,cid)
            last=db.scalar(select(ChatMessage).where(ChatMessage.conversation_id==cid).order_by(ChatMessage.id.desc()).limit(1))
            result.append({'id':cid,'lead':{'score':lp.score,'category':lp.category,'budget':lp.budget,'authority':lp.authority,'need':lp.need,'timeline':lp.timeline} if lp else None,
                           'last_message':last.content[:300] if last else None,'updated_at':c.updated_at.isoformat() if c.updated_at else None})
        return {'leads':result}

@router.get('/my-pipeline')
def my_pipeline(request: Request):
    with SessionLocal() as db:
        ids=set(db.scalars(select(LeadAssignment.conversation_id).where(LeadAssignment.user_id==request.state.operator['id'])).all())
    from .sales_pipeline_api import get_pipeline
    all_rows=get_pipeline()['appointments']
    rows=[r for r in all_rows if r['conversation_id'] in ids]
    owners={}
    for r in rows:
        if r.get('opportunity_owner_request_id'):
            owners[r['conversation_id']]=(r.get('opportunity_outcome'),r.get('opportunity_deal_value'))
    return {'appointments':rows,'summary':{'appointments':len(rows),'opportunities':len({r['conversation_id'] for r in rows}),
      'completed':sum(r['meeting_status']=='Meeting Completed' for r in rows),
      'won':sum(v[0]=='Won' for v in owners.values()),'lost':sum(v[0]=='Lost' for v in owners.values()),
      'won_deal_value_inr':str(sum((Decimal(v[1]) for v in owners.values() if v[0]=='Won' and v[1]),Decimal('0.00')))}}
