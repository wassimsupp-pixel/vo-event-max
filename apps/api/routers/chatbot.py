"""
routers/chatbot.py — Project-scoped conversational assistant (Feedback V1 §7).

Routes:
  GET  /api/events/{event_id}/chat/suggestions  Starter questions for the UI
  POST /api/events/{event_id}/chat              Ask a question about this event

Scope is enforced twice over: ``verify_event_access`` gates who may ask, and
services/chatbot_service only ever queries the event named in the path — the
assistant has no way to reach another event's data, which is exactly what the
brief asks for ("connecté uniquement à la mémoire de l'événement sélectionné").
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import ChatAnswer, ChatQuestion, ChatSuggestions
from services import chatbot_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/events/{event_id}/chat/suggestions",
    response_model=ChatSuggestions,
    summary="Starter questions and stated capabilities for the assistant",
)
async def get_suggestions(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ChatSuggestions:
    await verify_event_access(event_id, current_user, supabase)
    return ChatSuggestions(
        questions=chatbot_service.SUGGESTED_QUESTIONS,
        capabilities=chatbot_service.CAPABILITIES_FR,
    )


@router.post(
    "/events/{event_id}/chat",
    response_model=ChatAnswer,
    summary="Ask a question about this event's consolidated data",
)
async def ask(
    event_id: str,
    body: ChatQuestion,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ChatAnswer:
    await verify_event_access(event_id, current_user, supabase)
    result = chatbot_service.answer_question(
        question=body.question,
        event_id=event_id,
        supabase=supabase,
        user_role=current_user.get("role", "viewer"),
        history=[t.model_dump() for t in body.history],
    )
    logger.info(
        "Chat event=%s user=%s intent=%s answered=%s",
        event_id, current_user["id"], result.get("intent"), result.get("answered"),
    )
    return ChatAnswer(**result)
