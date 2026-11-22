import tempfile
import unittest
from pathlib import Path

from leadpilot_ai.twilio_gather_store import (
    GatherSessionStore
)

CALL = "CA" + "2" * 32


class PersistentGatherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.path = Path(self.temp.name) / "sessions.sqlite3"
        self.store = GatherSessionStore(self.path)

    def ready(self):
        self.assertEqual(
            self.store.claim_start(CALL)["status"],
            "new"
        )
        self.store.complete_start(
            CALL, "crm-123", "<Response>Welcome</Response>"
        )

    def test_start_survives_restart(self):
        self.ready()
        reopened = GatherSessionStore(self.path)
        result = reopened.claim_start(CALL)

        self.assertEqual(result["status"], "cached")
        self.assertEqual(
            result["conversation_id"], "crm-123"
        )

    def test_pending_start_fails_closed(self):
        self.store.claim_start(CALL)
        reopened = GatherSessionStore(self.path)

        self.assertEqual(
            reopened.claim_start(CALL)["status"],
            "pending"
        )

    def test_cached_retry_survives_restart(self):
        self.ready()
        self.store.claim_turn(CALL, 0, "Hello")
        self.store.complete_turn(
            CALL, 0, "Hello",
            "<Response>Hi</Response>",
            turns=1, empty=0
        )

        reopened = GatherSessionStore(self.path)
        result = reopened.claim_turn(CALL, 0, "Hello")

        self.assertEqual(result["status"], "cached")
        self.assertEqual(
            result["twiml"], "<Response>Hi</Response>"
        )

    def test_changed_retry_rejected(self):
        self.ready()
        self.store.claim_turn(CALL, 0, "Hello")
        self.store.complete_turn(
            CALL, 0, "Hello", "Reply", 1, 0
        )

        self.assertEqual(
            self.store.claim_turn(
                CALL, 0, "Different"
            )["status"],
            "conflict"
        )

    def test_pending_turn_fails_closed(self):
        self.ready()
        self.store.claim_turn(CALL, 0, "Hello")

        reopened = GatherSessionStore(self.path)

        self.assertEqual(
            reopened.claim_turn(
                CALL, 0, "Hello"
            )["status"],
            "pending"
        )

    def test_out_of_order_rejected(self):
        self.ready()

        self.assertEqual(
            self.store.claim_turn(
                CALL, 2, "Hello"
            )["status"],
            "conflict"
        )

    def test_same_words_next_step_allowed(self):
        self.ready()
        self.store.claim_turn(CALL, 0, "Yes")
        self.store.complete_turn(
            CALL, 0, "Yes", "Reply one", 1, 0
        )

        result = self.store.claim_turn(CALL, 1, "Yes")
        self.assertEqual(result["status"], "new")

    def test_closed_session_replay(self):
        self.ready()
        self.store.claim_turn(CALL, 0, "Goodbye")
        self.store.complete_turn(
            CALL, 0, "Goodbye", "Final reply",
            1, 0, closed=True
        )

        reopened = GatherSessionStore(self.path)

        self.assertEqual(
            reopened.claim_turn(
                CALL, 0, "Goodbye"
            )["status"],
            "cached"
        )

        self.assertEqual(
            reopened.claim_turn(
                CALL, 1, "Hello"
            )["status"],
            "conflict"
        )


if __name__ == "__main__":
    unittest.main()
