"""Conversation display names: separate, operator-set data; existing CRM rows untouched."""
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from leadpilot_ai import dashboard_api
from leadpilot_ai.crm_store import Base, Conversation, ChatMessage


class LeadDisplayLabelTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session=sessionmaker(bind=self.engine)
        self.patch=patch.object(dashboard_api,'SessionLocal',self.session)
        self.patch.start()
        app=FastAPI();app.include_router(dashboard_api.router)
        self.client=TestClient(app)
        self.id=str(uuid4())
        with self.session() as db:
            db.add(Conversation(id=self.id))
            db.add(ChatMessage(conversation_id=self.id,role='user',content='Need CRM'))
            db.commit()

    def tearDown(self):
        self.patch.stop();self.engine.dispose()

    def get_name(self):
        rows=self.client.get('/api/dashboard/conversations').json()['conversations']
        return next(x['display_name'] for x in rows if x['id']==self.id)

    def test_rename_and_clear_persists_without_changing_messages(self):
        url=f'/api/dashboard/conversations/{self.id}/label'
        self.assertIsNone(self.get_name())
        response=self.client.patch(url,json={'display_name':'  Acme Sales  '})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.get_name(),'Acme Sales')
        with self.session() as db:
            self.assertEqual(db.query(ChatMessage).count(),1)
        self.assertEqual(self.client.patch(url,json={'display_name':''}).status_code,200)
        self.assertIsNone(self.get_name())

    def test_no_fake_leads_or_invalid_names(self):
        missing=self.client.patch(f'/api/dashboard/conversations/{uuid4()}/label',json={'display_name':'Never existed'})
        self.assertEqual(missing.status_code,404)
        bad=self.client.patch(f'/api/dashboard/conversations/{self.id}/label',json={'display_name':'a'*65})
        self.assertEqual(bad.status_code,422)
        bad=self.client.patch(f'/api/dashboard/conversations/{self.id}/label',json={'display_name':'Bad\nName'})
        self.assertEqual(bad.status_code,422)
        self.assertIsNone(self.get_name())

if __name__=='__main__':
    unittest.main()
