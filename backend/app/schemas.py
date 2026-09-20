import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    pinned: bool
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationUpdate(BaseModel):
    pinned: bool


class MessageIn(BaseModel):
    content: str


class Activity(BaseModel):
    time: str
    title: str
    description: str = ""


class Day(BaseModel):
    day: int
    date: date
    location: str
    title: str
    activities: list[Activity] = []


class TripPlanData(BaseModel):
    """The plan agent's structured output. Fields are required (though nullable) — not
    defaulted — so that a malformed tool response (e.g. nested under an unexpected key)
    fails validation loudly instead of silently producing an empty plan."""

    destination: str | None
    start_date: date | None
    end_date: date | None
    days: list[Day]


class TripPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    destination: str | None
    start_date: date | None
    end_date: date | None
    days: list[Day]
    version: int
    updated_at: datetime


class TravelerFacts(BaseModel):
    """The profile agent's structured output: a flat map of preference category to a
    short free-text description, plus a synthesized prose summary."""

    facts: dict[str, str]
    summary: str


class SystemPromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    content: str
    updated_at: datetime


class SystemPromptIn(BaseModel):
    content: str
