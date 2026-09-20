import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.sql import func

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(default="New conversation")
    pinned: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    trip_plan: Mapped["TripPlan | None"] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", uselist=False
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role in ('user', 'assistant')", name="messages_role_check"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str]
    content: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class TripPlan(Base):
    __tablename__ = "trip_plans"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    destination: Mapped[str | None]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    days: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="trip_plan")


class TravelerProfile(Base):
    """Single row (id=1) — no auth/multi-user, so one running profile for the traveler."""

    __tablename__ = "traveler_profile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    facts: Mapped[dict] = mapped_column(JSONB, default=dict)
    summary: Mapped[str] = mapped_column(default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SystemPrompt(Base):
    """Single row (id=1) holding the advisor's editable system prompt."""

    __tablename__ = "system_prompt"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    content: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


DEFAULT_SYSTEM_PROMPT = (
    "You are a knowledgeable, friendly travel advisor. You help travelers plan trips, "
    "choose destinations, and answer travel-related questions. Stay in this role for "
    "the entire conversation. When a question depends on live information you can't "
    "know for certain (exchange rates, current weather, visa requirements), say so and "
    "use your tools to look it up rather than guessing."
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _seed_defaults()


def _seed_defaults() -> None:
    with SessionLocal() as session:
        if session.get(SystemPrompt, 1) is None:
            session.add(SystemPrompt(id=1, content=DEFAULT_SYSTEM_PROMPT))
        if session.get(TravelerProfile, 1) is None:
            session.add(TravelerProfile(id=1))
        session.commit()
