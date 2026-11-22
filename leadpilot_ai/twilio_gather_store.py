import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class GatherSessionStore:
    """Durable Twilio call state with fail-closed processing."""

    def __init__(self, db_path, ttl_seconds=900):
        self.path = Path(db_path)
        self.ttl = ttl_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)

        db = self._connect()
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS gather_sessions (
                    call_sid TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    conversation_id TEXT,
                    start_twiml TEXT,
                    next_step INTEGER NOT NULL DEFAULT 0,
                    turns INTEGER NOT NULL DEFAULT 0,
                    empty_turns INTEGER NOT NULL DEFAULT 0,
                    closed INTEGER NOT NULL DEFAULT 0,
                    updated REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS gather_responses (
                    call_sid TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    speech_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    twiml TEXT,
                    PRIMARY KEY(call_sid, step),
                    FOREIGN KEY(call_sid)
                        REFERENCES gather_sessions(call_sid)
                        ON DELETE CASCADE
                );
            """)
        finally:
            db.close()

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _transaction(self):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _expire(self, db):
        cutoff = time.time() - self.ttl
        db.execute(
            "DELETE FROM gather_sessions WHERE updated < ?",
            (cutoff,)
        )

    @staticmethod
    def _digest(speech):
        return hashlib.sha256(
            speech.encode("utf-8")
        ).hexdigest()

    def claim_start(self, call_sid):
        with self._transaction() as db:
            self._expire(db)

            row = db.execute(
                "SELECT * FROM gather_sessions "
                "WHERE call_sid = ?",
                (call_sid,)
            ).fetchone()

            if row:
                if row["status"] == "ready":
                    return {
                        "status": "cached",
                        "conversation_id": row["conversation_id"],
                        "twiml": row["start_twiml"]
                    }

                return {"status": "pending"}

            db.execute(
                "INSERT INTO gather_sessions "
                "(call_sid, status, updated) "
                "VALUES (?, 'starting', ?)",
                (call_sid, time.time())
            )

            return {"status": "new"}

    def complete_start(
        self, call_sid, conversation_id, twiml
    ):
        with self._transaction() as db:
            result = db.execute(
                "UPDATE gather_sessions SET "
                "status='ready', conversation_id=?, "
                "start_twiml=?, updated=? "
                "WHERE call_sid=? AND status='starting'",
                (
                    conversation_id,
                    twiml,
                    time.time(),
                    call_sid
                )
            )

            if result.rowcount != 1:
                raise RuntimeError(
                    "Start claim missing or already completed"
                )

    def claim_turn(self, call_sid, step, speech):
        digest = self._digest(speech)

        with self._transaction() as db:
            self._expire(db)

            session = db.execute(
                "SELECT * FROM gather_sessions "
                "WHERE call_sid=?",
                (call_sid,)
            ).fetchone()

            if session is None:
                return {"status": "missing"}

            response = db.execute(
                "SELECT * FROM gather_responses "
                "WHERE call_sid=? AND step=?",
                (call_sid, step)
            ).fetchone()

            if response:
                if response["speech_hash"] != digest:
                    return {"status": "conflict"}

                if response["status"] == "done":
                    return {
                        "status": "cached",
                        "twiml": response["twiml"]
                    }

                # An interrupted in-flight request is not
                # automatically repeated against the CRM.
                return {"status": "pending"}

            if session["status"] != "ready":
                return {"status": "pending"}

            if (
                session["closed"]
                or session["next_step"] != step
            ):
                return {"status": "conflict"}

            db.execute(
                "INSERT INTO gather_responses "
                "(call_sid, step, speech_hash, status) "
                "VALUES (?, ?, ?, 'processing')",
                (call_sid, step, digest)
            )

            return {
                "status": "new",
                "conversation_id": session["conversation_id"],
                "turns": session["turns"],
                "empty": session["empty_turns"]
            }

    def complete_turn(
        self, call_sid, step, speech, twiml,
        turns, empty, closed=False
    ):
        with self._transaction() as db:
            updated = db.execute(
                "UPDATE gather_responses "
                "SET status='done', twiml=? "
                "WHERE call_sid=? AND step=? "
                "AND speech_hash=? AND status='processing'",
                (
                    twiml,
                    call_sid,
                    step,
                    self._digest(speech)
                )
            )

            if updated.rowcount != 1:
                raise RuntimeError(
                    "Turn claim missing or already completed"
                )

            session = db.execute(
                "UPDATE gather_sessions SET "
                "next_step=?, turns=?, empty_turns=?, "
                "closed=?, updated=? "
                "WHERE call_sid=? AND status='ready' "
                "AND next_step=? AND closed=0",
                (
                    step + 1,
                    turns,
                    empty,
                    int(closed),
                    time.time(),
                    call_sid,
                    step
                )
            )

            if session.rowcount != 1:
                raise RuntimeError(
                    "Session changed during processing"
                )
