import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, String, Integer,
    DateTime, ForeignKey, Text
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import (
    DeclarativeBase, Mapped,
    mapped_column, sessionmaker
)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_DB = "sqlite:///" + (
    ROOT / "leadpilot_data.sqlite3"
).as_posix()

DATABASE_URL = os.getenv(
    "LEADPILOT_DATABASE_URL", DEFAULT_DB
)

# Local development uses SQLite; the cloud uses Neon PostgreSQL.
# Explicitly select psycopg 3 when Neon supplies a postgresql:// URL.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
else:
    # Vercel functions are ephemeral and Neon already runs a transaction pooler.
    # Keep no SQLAlchemy connections resident between requests or deployments.
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None}
        if DATABASE_URL.startswith("postgresql+psycopg://") else {},
    )

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False
)


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "lp_conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ChatMessage(Base):
    __tablename__ = "lp_messages"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lp_conversations.id")
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)


class LeadProfile(Base):
    __tablename__ = "lp_leads"

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lp_conversations.id"),
        primary_key=True
    )

    budget: Mapped[str] = mapped_column(
        String(30), default="unknown"
    )
    authority: Mapped[str] = mapped_column(
        String(30), default="unknown"
    )
    need: Mapped[str] = mapped_column(
        String(30), default="unknown"
    )
    timeline: Mapped[str] = mapped_column(
        String(30), default="unknown"
    )
    score: Mapped[int] = mapped_column(
        Integer, default=0
    )
    category: Mapped[str] = mapped_column(
        String(20), default="Incomplete"
    )


Base.metadata.create_all(bind=engine)
