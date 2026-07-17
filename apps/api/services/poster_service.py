# -*- coding: utf-8 -*-
"""
poster_service.py
=================
Extract structured event information (title, location, date, time, capacity …)
from an uploaded event poster/flyer image using Gemini Vision.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    if os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        GEMINI_AVAILABLE = True
except ImportError:
    pass

_PROMPT = """
Tu analyses une affiche / un poster d'événement. Extrais les informations présentes
en JSON strict, avec ces champs (mets null si l'information n'est pas visible —
n'invente RIEN) :
{
  "title": "nom / titre de l'événement ou de l'activité",
  "location": "lieu / adresse",
  "date": "date (format lisible)",
  "time": "horaire(s)",
  "capacity": "capacité / nombre de places (nombre si possible)",
  "description": "courte description",
  "other": "autres infos utiles (prix, contact, conditions…)"
}
Réponds UNIQUEMENT avec le JSON.
"""


def analyze_poster(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Return structured event info extracted from a poster image."""
    from services import ai_service

    if not ai_service.ai_available():
        return {"error": "AI vision non configurée (clé OPENAI_API_KEY ou GEMINI_API_KEY manquante).", "fields": {}}

    try:
        fields = ai_service.ai_json(_PROMPT, image_bytes=image_bytes, mime_type=mime_type)
        if not isinstance(fields, dict):
            raise ValueError("no JSON in AI answer")
        return {"fields": fields}
    except Exception as exc:
        logger.error("Poster analysis failed: %s", exc)
        return {"error": "Échec de l'analyse de l'affiche.", "fields": {}}
