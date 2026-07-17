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


def _prepare_image(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """
    Turn any uploaded poster into a vision-ready PNG/JPEG:
      - a PDF is rasterised (first page) so vision models can read it;
      - a large photo is downscaled + re-encoded so it stays under the NVIDIA
        inline limit and is analysed fast.
    Returns (bytes, mime_type). On any failure the original bytes are returned.
    """
    is_pdf = mime_type == "application/pdf" or data[:5] == b"%PDF-"
    if is_pdf:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=data, filetype="pdf")
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=150)
            return pix.tobytes("png"), "image/png"
        except Exception as exc:
            logger.warning("PDF rasterisation failed (%s); passing PDF through.", exc)
            return data, mime_type
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((1568, 1568))     # fits vision-model limits, keeps text legible
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.warning("Image downscale failed (%s); passing original through.", exc)
        return data, mime_type


def analyze_poster(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Return structured event info extracted from a poster image or PDF."""
    from services import ai_service

    if not ai_service.ai_available():
        return {"error": "AI vision non configurée (clé NVIDIA_API_KEY ou GEMINI_API_KEY manquante).", "fields": {}}

    img_bytes, img_mime = _prepare_image(image_bytes, mime_type)
    try:
        fields = ai_service.ai_json(_PROMPT, image_bytes=img_bytes, mime_type=img_mime)
        if not isinstance(fields, dict):
            raise ValueError("no JSON in AI answer")
        return {"fields": fields}
    except Exception as exc:
        logger.error("Poster analysis failed: %s", exc)
        return {"error": "Échec de l'analyse de l'affiche.", "fields": {}}
