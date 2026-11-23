"""Read-only Copilot endpoints; uses an isolated in-memory SQLite database."""
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from leadpilot_ai import dashboard_api
from leadpilot_ai.crm_store import Base, Conversation, ChatMessage, LeadProfile
from leadpilot_ai.appointment_booking import Appointment


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)
        self.patch = patch.object(dashboard_api, "SessionLocal", self.session)
        self.patch.start()
        app = FastAPI()
        app.include_router(dashboard_api.router)
        self.client = TestClient(app)
        self.conversation_id = str(uuid4())

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()

    def test_empty_state(self):
        self.assertEqual(self.client.get("/api/dashboard/summary").json()["total_leads"], 0)
        self.assertEqual(self.client.get("/api/dashboard/conversations").json()["conversations"], [])
        self.assertIsNone(self.client.get("/api/dashboard/summary").json()["calls_today"])

    def test_real_counts_and_conversation_preview(self):
        with self.session() as db:
            db.add(Conversation(id=self.conversation_id, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
            db.add(LeadProfile(conversation_id=self.conversation_id, budget="confirmed", authority="decision_maker", need="clear", timeline="within_30_days", score=100, category="Hot"))
            db.add(ChatMessage(conversation_id=self.conversation_id, role="user", content="I need a sales CRM"))
            db.add(ChatMessage(conversation_id=self.conversation_id, role="assistant", content="Do you have an allocated budget?"))
            db.commit()
        summary = self.client.get("/api/dashboard/summary").json()
        self.assertEqual(summary["total_conversations"], 1)
        self.assertEqual(summary["total_leads"], 1)
        self.assertEqual(summary["hot_leads"], 1)
        self.assertEqual(summary["qualified_leads"], 1)
        item = self.client.get("/api/dashboard/conversations").json()["conversations"][0]
        self.assertEqual(item["lead"]["score"], 100)
        self.assertEqual(item["last_message"]["role"], "assistant")
        self.assertEqual(item["last_message"]["content"], "Do you have an allocated budget?")

    def test_appointment_count(self):
        with self.session() as db:
            db.add(Conversation(id=self.conversation_id))
            db.add(Appointment(request_id=str(uuid4()), conversation_id=self.conversation_id,
                calendar_event_id="lp-test-example", start_at="2027-05-05T10:00:00+05:30", end_at="2027-05-05T10:30:00+05:30"))
            db.commit()
        self.assertEqual(self.client.get("/api/dashboard/summary").json()["appointments_booked"], 1)
        self.assertEqual(len(self.client.get("/api/dashboard/appointments").json()["appointments"]), 1)

    def test_limit_validation(self):
        self.assertEqual(self.client.get("/api/dashboard/conversations?limit=201").status_code, 422)
        self.assertEqual(self.client.get("/api/dashboard/appointments?limit=0").status_code, 422)


if __name__ == "__main__":
    unittest.main()
