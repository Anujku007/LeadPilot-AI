"""End-to-end role/access checks using an isolated SQLite database and HTTP client."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from leadpilot_ai.auth_api import router as auth, auth_middleware, create_operator, SessionLocal
from leadpilot_ai.crm_store import Conversation
from leadpilot_ai.team_access import router as team, TeamRole, LeadAssignment
from sqlalchemy import select
create_operator('owner','safe-long-admin-password')
app=FastAPI(); app.include_router(auth);app.include_router(team);app.add_middleware(BaseHTTPMiddleware,dispatch=auth_middleware)
@app.get('/api/conversations/{cid}')
def get_conversation(cid:str):return {'id':cid}
@app.post('/api/conversations/{cid}/chat')
def chat(cid:str):return {'id':cid}
@app.get('/api/dashboard/summary')
def dashboard():return {'private':'yes'}
ids=[str(uuid4()),str(uuid4())]
with SessionLocal() as db:
  for cid in ids:db.add(Conversation(id=cid))
  db.commit()
with TestClient(app) as admin:
  assert admin.get('/api/team/operators').status_code==401
  assert admin.post('/api/auth/login',json={'username':'owner','password':'safe-long-admin-password'}).status_code==200
  assert admin.get('/api/auth/me').json()['user']['role']=='admin'
  res=admin.post('/api/team/operators',json={'username':'repone','password':'salesperson-long-pass'})
  assert res.status_code==201,res.text
  uid=res.json()['id']
  assert admin.post('/api/team/operators',json={'username':'repone','password':'salesperson-long-pass'}).status_code==409
  assert admin.put(f'/api/team/leads/{ids[0]}/assign',json={'user_id':uid}).status_code==200
  assert admin.get('/api/team/leads').status_code==200
  assert admin.get('/api/dashboard/summary').status_code==200
with TestClient(app) as staff:
  assert staff.post('/api/auth/login',json={'username':'repone','password':'salesperson-long-pass'}).status_code==200
  assert staff.get('/api/auth/me').json()['user']['role']=='sales'
  assert staff.get('/api/team/my-leads').json()['leads'][0]['id']==ids[0]
  assert staff.get('/api/conversations/'+ids[0]).status_code==200
  assert staff.post('/api/conversations/'+ids[0]+'/chat').status_code==200
  assert staff.get('/api/conversations/'+ids[1]).status_code==403
  assert staff.post('/api/conversations/'+ids[1]+'/chat').status_code==403
  assert staff.get('/api/dashboard/summary').status_code==403
  assert staff.get('/api/team/operators').status_code==403
  assert staff.get('/api/team/leads').status_code==403
  assert staff.post('/api/conversations/start').status_code==403
  assert staff.get('/api/appointments/availability').status_code!=403
  with TestClient(app) as admin:
    assert admin.post('/api/auth/login',json={'username':'owner','password':'safe-long-admin-password'}).status_code==200
    assert admin.patch('/api/team/operators/'+uid+'/active',json={'active':False}).status_code==200
  assert staff.get('/api/auth/me').status_code==401
  assert staff.get('/api/team/my-leads').status_code==401
  assert staff.post('/api/auth/login',json={'username':'repone','password':'salesperson-long-pass'}).status_code==401
with TestClient(app) as admin:
  assert admin.post('/api/auth/login',json={'username':'owner','password':'safe-long-admin-password'}).status_code==200
  assert admin.patch('/api/team/operators/'+uid+'/active',json={'active':True}).status_code==200
  assert admin.post('/api/team/operators/'+uid+'/reset-password',json={'new_password':'new-long-sales-pass'}).status_code==200
with TestClient(app) as staff:
  assert staff.post('/api/auth/login',json={'username':'repone','password':'new-long-sales-pass'}).status_code==200
  assert staff.get('/api/team/my-leads').status_code==200
print('PASS: team roles, lead scope, account controls and session revocation')
from leadpilot_ai.crm_store import engine
engine.dispose()
'''

class TeamAccessTests(unittest.TestCase):
    def test_isolated_authorization(self):
        with tempfile.TemporaryDirectory(prefix='leadpilot-team-') as temp:
            env=os.environ.copy()
            env['LEADPILOT_DATABASE_URL']='sqlite:///'+(Path(temp)/'team.sqlite3').as_posix()
            proc=subprocess.run([sys.executable,'-c',CODE],cwd=ROOT,env=env,text=True,capture_output=True,timeout=70)
            self.assertEqual(proc.returncode,0,proc.stdout+'\n'+proc.stderr)
            self.assertIn('PASS: team roles',proc.stdout)

if __name__=='__main__':unittest.main()
