import json
import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from .config import settings
from .db import SessionLocal, TravelerProfile, TripPlan
from .llm import complete_text, complete_with_tools, stream_chat
from .schemas import TravelerFacts, TripPlanData
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = (
    "You maintain a structured trip plan for a travel planning conversation. You'll be "
    "given the plan's current state (JSON, or null if none exists yet) and the "
    "conversation so far. Produce the complete, updated trip plan: keep everything that "
    "wasn't asked to change, and apply what the traveler just requested. If there's no "
    "current plan, build a new one from the conversation. Use ISO dates (YYYY-MM-DD) and "
    "number days sequentially starting at 1."
)

# Hand-written and flat rather than TripPlanData.model_json_schema(): empirically, the
# Pydantic-generated schema (with $defs/$ref indirection) sometimes led the model to wrap
# its answer as {"plan": {...}} instead of returning the fields directly. A flat schema
# with explicit "required" fields and the instruction below reliably avoided that.
PLAN_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "set_trip_plan",
        "description": (
            "Set the complete, updated structured trip plan. Call with the fields "
            "(destination, start_date, end_date, days) directly as top-level arguments "
            "— do not nest them under another key."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {"type": ["string", "null"]},
                "start_date": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD"},
                "end_date": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD"},
                "days": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day": {"type": "integer"},
                            "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                            "location": {"type": "string"},
                            "title": {"type": "string"},
                            "activities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "time": {"type": "string"},
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["time", "title"],
                                },
                            },
                        },
                        "required": ["day", "date", "location", "title"],
                    },
                },
            },
            "required": ["destination", "start_date", "end_date", "days"],
            "additionalProperties": False,
        },
    },
}

UPDATE_TRIP_PLAN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_trip_plan",
        "description": (
            "Create or update the traveler's structured trip plan (destination, dates, "
            "day-by-day itinerary) to reflect the conversation so far. Call this whenever "
            "the traveler asks you to create a trip plan or change an existing one — "
            "including applying a specific change you just suggested (e.g. rearranging the "
            "itinerary based on weather) once the traveler agrees to it. Never call it for "
            "general travel questions that don't touch the plan, and don't call it just to "
            "float an idea the traveler hasn't asked for or agreed to yet."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

GET_TRIP_PLAN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_trip_plan",
        "description": (
            "Get the traveler's current structured trip plan — destination, dates, and the "
            "full day-by-day itinerary with activities. Call this before suggesting or "
            "making changes to the plan, and whenever the traveler asks what's planned for "
            "a specific day (e.g. 'what should I do tomorrow?'). The plan may have been "
            "edited (including manually, outside this conversation) since it was last "
            "discussed here, so check it rather than relying on what you remember."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


def run_advisor_agent(system_prompt: str, history: list[dict], conversation_id: uuid.UUID) -> Iterator[dict]:
    """The travel advisor agent: streams reply/tool-call events given the conversation so far.

    Has access to live-data tools (exchange rates, weather, web search) and, separately,
    a trip-plan tool — it decides on its own when a message needs one instead of guessing,
    and normal travel questions should trigger neither.
    """

    def handle_update_trip_plan(**_ignored) -> dict:
        return update_trip_plan(conversation_id, history)

    def handle_get_trip_plan(**_ignored) -> dict:
        return get_trip_plan_for_conversation(conversation_id)

    tools = [*TOOL_SCHEMAS, UPDATE_TRIP_PLAN_SCHEMA, GET_TRIP_PLAN_SCHEMA]
    handlers = {
        **TOOL_HANDLERS,
        "update_trip_plan": handle_update_trip_plan,
        "get_trip_plan": handle_get_trip_plan,
    }

    yield from stream_chat(
        model=settings.advisor_model,
        system=system_prompt,
        messages=history,
        tools=tools,
        tool_handlers=handlers,
    )


def run_plan_agent(conversation_messages: list[dict], current_plan: dict | None) -> dict:
    """The trip-plan agent: a separate agent from the advisor. Produces the complete,
    structured trip plan from the conversation and the plan's current state (if any),
    via a forced structured tool call."""
    today = datetime.now(timezone.utc).date().isoformat()
    system = (
        f"{PLAN_SYSTEM_PROMPT}\n\nToday's date is {today}.\n\n"
        f"Current plan (JSON, null if none exists yet):\n{json.dumps(current_plan)}"
    )
    messages = [{"role": "system", "content": system}, *conversation_messages]

    response = complete_with_tools(
        model=settings.advisor_model,
        messages=messages,
        tools=[PLAN_TOOL_SCHEMA],
        tool_choice={"type": "function", "function": {"name": "set_trip_plan"}},
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)


def _unwrap_single_key_payload(raw: dict, expected_keys: set[str]) -> dict:
    """Last-resort safety net: if the model still nests its answer under a single wrapper
    key (e.g. {"plan": {...}}) despite the schema/instructions, unwrap it."""
    if expected_keys & raw.keys():
        return raw
    if len(raw) == 1:
        nested = next(iter(raw.values()))
        if isinstance(nested, dict):
            return nested
    return raw


def _trip_plan_to_dict(plan: TripPlan) -> dict:
    return {
        "destination": plan.destination,
        "start_date": plan.start_date.isoformat() if plan.start_date else None,
        "end_date": plan.end_date.isoformat() if plan.end_date else None,
        "days": plan.days,
    }


def get_trip_plan_for_conversation(conversation_id: uuid.UUID) -> dict:
    """Reads the current trip plan for a conversation. Used as the advisor agent's
    `get_trip_plan` tool handler, e.g. to check the itinerary and check it against the
    weather before suggesting or applying changes."""
    with SessionLocal() as db:
        plan = db.get(TripPlan, conversation_id)
        if plan is None:
            return {"error": "No trip plan exists yet for this conversation."}
        return _trip_plan_to_dict(plan)


def update_trip_plan(conversation_id: uuid.UUID, conversation_messages: list[dict]) -> dict:
    """Orchestrates the plan agent: reads the current plan, runs the agent, validates and
    persists the result. Used as the advisor agent's `update_trip_plan` tool handler."""
    with SessionLocal() as db:
        existing = db.get(TripPlan, conversation_id)
        current_plan = _trip_plan_to_dict(existing) if existing else None

        try:
            raw_plan = run_plan_agent(conversation_messages, current_plan)
            expected = {"destination", "start_date", "end_date", "days"}
            plan = TripPlanData.model_validate(_unwrap_single_key_payload(raw_plan, expected))
        except Exception:
            logger.exception("Plan agent failed for conversation %s", conversation_id)
            return {"error": "Could not update the trip plan right now."}

        status = "updated"
        if existing is None:
            existing = TripPlan(conversation_id=conversation_id)
            db.add(existing)
            status = "created"

        existing.destination = plan.destination
        existing.start_date = plan.start_date
        existing.end_date = plan.end_date
        existing.days = [day.model_dump(mode="json") for day in plan.days]
        existing.version = (existing.version or 0) + 1
        db.commit()

        return {"status": status, "destination": plan.destination, "day_count": len(plan.days)}


PROFILE_SYSTEM_PROMPT = (
    "You maintain a long-term traveler profile shared across all of this traveler's "
    "conversations. You'll be given the profile's current state (facts + summary) and "
    "the traveler's latest message. Extract ONLY durable, reusable travel preferences "
    "that would be useful in future trips — e.g. budget level, preferred travel style or "
    "pace, liked or disliked destinations, flight/seating preferences, dietary needs, "
    "accommodation preferences. Do NOT record one-off details specific to a single trip "
    "being planned right now (like specific dates or a specific itinerary) — that belongs "
    "in a trip plan, not here. "
    "Never record sensitive information under any circumstances — passwords, payment or "
    "card details, passport numbers, or API keys/credentials — if any appear in the "
    "message, ignore them entirely and do not mention them in facts or summary. "
    "Merge new information with the current facts: keep everything still valid, add or "
    "update what's new, and only remove something if the traveler contradicted it. If "
    "nothing relevant was mentioned, return the current facts and summary unchanged. "
    "Output flat facts (a short category name mapped to a short free-text description) "
    "and a short natural-language summary synthesizing them."
)

# Flat schema, same reasoning as PLAN_TOOL_SCHEMA above: avoids the model wrapping its
# answer under an extra key.
PROFILE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "set_traveler_profile",
        "description": (
            "Set the complete, updated traveler profile. Call with the fields (facts, "
            "summary) directly as top-level arguments — do not nest them under another key."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Flat map of preference category to a short free-text description.",
                },
                "summary": {
                    "type": "string",
                    "description": "Short natural-language paragraph synthesizing the facts.",
                },
            },
            "required": ["facts", "summary"],
            "additionalProperties": False,
        },
    },
}


def run_profile_agent(latest_user_message: str, current_facts: dict, current_summary: str) -> dict:
    """The traveler-profile agent: a separate agent from the advisor and the plan agent.
    Extracts durable preferences from the latest message, merged with the profile's
    current state, via a forced structured tool call."""
    system = (
        f"{PROFILE_SYSTEM_PROMPT}\n\n"
        f"Current facts (JSON): {json.dumps(current_facts)}\n"
        f"Current summary: {current_summary or '(none yet)'}"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Traveler's latest message: {latest_user_message}"},
    ]

    response = complete_with_tools(
        model=settings.advisor_model,
        messages=messages,
        tools=[PROFILE_TOOL_SCHEMA],
        tool_choice={"type": "function", "function": {"name": "set_traveler_profile"}},
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)


def update_traveler_profile(latest_user_message: str) -> None:
    """Runs the profile agent and persists the result. Called after every user message
    (not gated by the advisor's own decisions, unlike the trip plan) so casual preference
    mentions aren't missed. Best-effort: failures are logged and swallowed so they never
    break the chat response."""
    with SessionLocal() as db:
        profile = db.get(TravelerProfile, 1)
        current_facts = profile.facts if profile else {}
        current_summary = profile.summary if profile else ""

        try:
            raw = run_profile_agent(latest_user_message, current_facts, current_summary)
            updated = TravelerFacts.model_validate(_unwrap_single_key_payload(raw, {"facts", "summary"}))
        except Exception:
            logger.exception("Profile agent failed")
            return

        if profile is None:
            profile = TravelerProfile(id=1)
            db.add(profile)

        profile.facts = updated.facts
        profile.summary = updated.summary
        db.commit()


TITLE_SYSTEM_PROMPT = (
    "You generate short titles for travel-planning conversations. Given the traveler's "
    "first message, respond with ONLY a natural, concise title of 2-5 words that captures "
    "the topic — title case, no quotes, no ending punctuation. Examples: "
    "'plan me a 2 day trip to london' -> London 2-Day Trip; "
    "'what are the best beaches in portugal' -> Portugal Beaches; "
    "'is japan expensive' -> Japan Travel Costs."
)


def _fallback_title(content: str, max_length: int = 60) -> str:
    """Used only if title generation fails — a plain truncation of the message itself."""
    text = " ".join(content.split()).strip()
    if not text:
        return "New conversation"
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return f"{truncated}…"


def generate_conversation_title(first_message: str) -> str:
    """Turns a traveler's first message into a short, natural conversation title. Falls
    back to a plain truncation if the model call fails, so a title is always produced."""
    try:
        title = complete_text(settings.advisor_model, TITLE_SYSTEM_PROMPT, first_message)
        title = title.strip().strip('"').strip("'").strip()
        if not title:
            raise ValueError("empty title")
        return _fallback_title(title, max_length=60) if len(title) > 60 else title
    except Exception:
        logger.exception("Title generation failed")
        return _fallback_title(first_message)
