import json
import logging
import threading
import uuid
from datetime import datetime, timezone

# StreamingResponse omogućuje da odgovor šaljemo postupno, kako se generira.
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

# SQLAlchemy koristimo za komunikaciju s PostgreSQL bazom.
from sqlalchemy import text
from sqlalchemy.orm import Session

# Routes poziva agente
from .agents import (
    generate_conversation_title,
    run_advisor_agent,
    update_traveler_profile,
)

# Database modeli i funkcije za otvaranje DB sesije.
from .db import (
    Conversation,
    Message,
    SessionLocal,
    SystemPrompt,
    TravelerProfile,
    TripPlan,
    get_db,
)

# Pydantic sheme definiraju oblik podataka koje API prima i vraća.
from .schemas import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    MessageIn,
    SystemPromptIn,
    SystemPromptOut,
    TripPlanData,
    TripPlanOut,
)


# Logger koristimo za bilježenje grešaka na backendu
logger = logging.getLogger(__name__)


# Glavni router za sve endpointove vezane uz razgovore
router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# Odvojeni router za dohvat i uređivanje system prompta
system_prompt_router = APIRouter(
    prefix="/api/system-prompt",
    tags=["system-prompt"]
)


@router.get("", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    # Dohvaca sve razgovore za sidebar
    # Pinned razgovori idu prvi, a zatim se sortiraju po zadnjoj aktivnosti
    return db.query(Conversation).order_by(
        Conversation.pinned.desc(),
        Conversation.updated_at.desc()
    ).all()


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db)
):
    # Stvara novi razgovor
    # Ako naslov nije zadan, privremeno koristi "New conversation"
    conversation = Conversation(
        title=payload.title or "New conversation"
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    # Dohvaca jedan konkretan razgovor iz baze
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    return conversation


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    db: Session = Depends(get_db)
):
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    # Pinning nije nova aktivnost u razgovoru
    # Zato direktno mijenjamo samo pinned vrijednost i ne zelimo da se zbog toga promijeni updated_at
    db.execute(
        text(
            "UPDATE conversations "
            "SET pinned = :pinned "
            "WHERE id = :id"
        ),
        {
            "pinned": payload.pinned,
            "id": str(conversation_id)
        },
    )

    db.commit()
    db.refresh(conversation)

    return conversation


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    # Brise razgovor iz baze
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    db.delete(conversation)
    db.commit()


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    db: Session = Depends(get_db)
):
    # GLAVNI CHAT ENDPOINT.
    #
    # Ovdje se:
    # 1. sprema userova poruka
    # 2. dohvaća kontekst za Advisora
    # 3. pokreće Advisor Agent
    # 4. streama njegov odgovor prema frontendu
    # 5. sprema zavrsni odgovor u bazu
    # 6. azurira traveler profile

    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    # Provjeravamo je li ovo prva poruka jer samo tada generiramo naslov razgovora
    is_first_message = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .count() == 0
    )

    # Userovu poruku prvo spremamo u bazu
    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=payload.content
        )
    )

    # Azuriramo vrijeme zadnje aktivnosti razgovora
    conversation.updated_at = datetime.now(timezone.utc)

    db.commit()

    # Dohvacamo trenutno spremljeni system prompt
    system_prompt = db.get(SystemPrompt, 1).content

    # Modelu eksplicitno dajemo danasnji datum,
    today = datetime.now(timezone.utc).date().isoformat()

    system_prompt = (
        f"{system_prompt}\n\n"
        f"Today's date is {today}."
    )

    # Dohvacamo traveler profile iz baze (ovo je samo deterministicki dohvat memorije, nije pozivanje Profile Agenta)
    profile = db.get(TravelerProfile, 1)

    if profile and profile.summary:
        system_prompt = (
            f"{system_prompt}\n\n"
            f"What you already know about this traveler:\n"
            f"{profile.summary}"
        )

    # Dohvacamo cijelu povijest trenutnog razgovora kako bi Advisor imao kontekst prethodnih poruka
    history = [
        {
            "role": message.role,
            "content": message.content
        }
        for message in db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ]


    def event_stream():
        # Ovdje skupljamo pojedinacne dijelove odgovora
        # Kasnije ih spajamo u jedan kompletan assistant message koji spremamo u bazu
        chunks: list[str] = []

        # naslov se generira paralelno s odgovorom
        title_box: dict[str, str] = {}
        title_thread: threading.Thread | None = None
        title_sent = False


        if is_first_message:
            # Naslov generiramo u zasebnom threadu kako njegovo generiranje ne bi usporilo prvi odgovor korisniku
            def _run_title() -> None:
                title_box["value"] = generate_conversation_title(
                    payload.content
                )

            title_thread = threading.Thread(
                target=_run_title,
                daemon=True
            )
            title_thread.start()


        def _save_and_format_title(title: str) -> str:
            # Otvaramo zasebnu DB sesiju za spremanje naslova.
            with SessionLocal() as title_db:
                title_db.get(
                    Conversation,
                    conversation_id
                ).title = title

                title_db.commit()

            # Naslov saljemo frontendu kao SSE event.
            return (
                f"data: "
                f"{json.dumps({'title': title})}\n\n"
            )


        try:
            # Advisor Agent generira odgovor
            for event in run_advisor_agent(
                system_prompt,
                history,
                conversation_id
            ):

                if event["type"] == "text":
        
                    chunks.append(event["text"])

                    # streaming preko Server-Sent Events
                    yield (
                        f"data: "
                        f"{json.dumps({'delta': event['text']})}\n\n"
                    )


                elif event["type"] == "tool_call":
                    # Frontend može pomocu ovog eventa prikazati npr. "Searching the web..." dok alat radi
                    yield (
                        f"data: "
                        f"{json.dumps({'tool': event['name']})}\n\n"
                    )


                # Ako je naslov vec gotov tijekom streaminga odmah ga saljemo frontendu
                if not title_sent and "value" in title_box:
                    title_sent = True

                    yield _save_and_format_title(
                        title_box["value"]
                    )


        except Exception:
    
            logger.exception(
                "Advisor agent failed for conversation %s",
                conversation_id
            )

            if title_thread and not title_sent:
                title_thread.join()

                yield _save_and_format_title(
                    title_box["value"]
                )

            yield (
                f"data: "
                f"{json.dumps({'error': 'The advisor is unavailable right now.'})}"
                f"\n\n"
            )

            return


        if title_thread and not title_sent:
            # Ako je odgovor zavrsio prije naslova, moramo pricekati da se generiranje naslova zavrsi
            title_thread.join()

            yield _save_and_format_title(
                title_box["value"]
            )

        full_text = "".join(chunks)

        with SessionLocal() as stream_db:
            stream_db.add(
                Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_text
                )
            )

            stream_db.commit()

        update_traveler_profile(payload.content)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )


@router.get(
    "/{conversation_id}/trip-plan",
    response_model=TripPlanOut
)
def get_trip_plan(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    # Dohvaca strukturirani trip plan za odredeni razgovor
    conversation = db.get(Conversation, conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    plan = db.get(TripPlan, conversation_id)

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="No trip plan yet"
        )

    return plan


@router.patch(
    "/{conversation_id}/trip-plan",
    response_model=TripPlanOut
)
def update_trip_plan_manually(
    conversation_id: uuid.UUID,
    payload: TripPlanData,
    db: Session = Depends(get_db)
):
    # Ovaj endpoint služi za rucno uređivanje trip plana

    conversation = db.get(
        Conversation,
        conversation_id
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    plan = db.get(
        TripPlan,
        conversation_id
    )

    if plan is None:
        plan = TripPlan(
            conversation_id=conversation_id
        )

        db.add(plan)


    plan.destination = payload.destination
    plan.start_date = payload.start_date
    plan.end_date = payload.end_date

    plan.days = [
        day.model_dump(mode="json")
        for day in payload.days
    ]

    plan.version = (plan.version or 0) + 1

    db.commit()
    db.refresh(plan)

    return plan


@system_prompt_router.get(
    "",
    response_model=SystemPromptOut
)
def get_system_prompt(
    db: Session = Depends(get_db)
):
    return db.get(SystemPrompt, 1)


@system_prompt_router.put(
    "",
    response_model=SystemPromptOut
)
def update_system_prompt(
    payload: SystemPromptIn,
    db: Session = Depends(get_db)
):

    prompt = db.get(
        SystemPrompt,
        1
    )

    prompt.content = payload.content

    db.commit()
    db.refresh(prompt)

    return prompt