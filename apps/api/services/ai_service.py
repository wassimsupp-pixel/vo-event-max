"""
services/ai_service.py — Unified AI gateway for every intelligent step
(auto-mapping, file analysis, poster recognition, quality summaries, email
agent, campaign generation).

Provider policy (first usable wins, automatic fallback on failure):
  1. NVIDIA NIM (env ``NVIDIA_API_KEY``) — used FIRST. Text reasoning (mapping,
     fusion, analysis) via ``meta/llama-3.3-70b-instruct``; photo/PDF vision
     (event posters) via ``meta/llama-3.2-90b-vision-instruct``.
     OpenAI-compatible endpoint.
  2. OpenAI (env ``OPENAI_API_KEY``, gpt-4o-mini) — vision-capable fallback.
  3. Google Gemini (env ``GEMINI_API_KEY``, gemini-2.5-flash) — final fallback,
     handles images and PDFs natively.

An invalid key is detected once (401/403) and that provider is skipped for the
rest of the process — no added latency on later calls. A slow or too-large
image on NVIDIA simply falls back to the next vision provider.

Model overrides: ``NVIDIA_MODEL`` (text), ``NVIDIA_VISION_MODEL`` (vision).
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# Text model for mapping / fusion / analysis. Llama 3.3 70B is far stronger than
# mistral-nemotron on structured extraction yet stays fast (~16s) and reliable
# on JSON — the 675B/397B flagships time out, so they're unusable in the
# upload-time mapping path. Override with NVIDIA_MODEL.
_NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
# Vision model for event photo/PDF analysis (Pixtral is not available on the
# integrate endpoint; Llama 3.2 90B Vision is and is confirmed working).
_NVIDIA_VISION_MODEL = os.getenv("NVIDIA_VISION_MODEL", "meta/llama-3.2-90b-vision-instruct")
_nvidia_disabled = False

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_MODEL = "gpt-4o-mini"
_openai_disabled = False

_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    if os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        GEMINI_AVAILABLE = True
except ImportError:
    pass


def _nvidia_key() -> Optional[str]:
    if _nvidia_disabled:
        return None
    return (os.getenv("NVIDIA_API_KEY") or "").strip() or None


def _openai_key() -> Optional[str]:
    if _openai_disabled:
        return None
    return (os.getenv("OPENAI_API_KEY") or "").strip() or None


def ai_available() -> bool:
    """True when at least one AI provider is usable."""
    return bool(_nvidia_key()) or bool(_openai_key()) or GEMINI_AVAILABLE


def _nvidia_complete(prompt: str, image_bytes: Optional[bytes], mime_type: Optional[str], timeout_s: Optional[float] = None) -> Optional[str]:
    """
    NVIDIA NIM chat completion (OpenAI-compatible). Text uses the Mistral text
    model; an image uses the vision model with a longer timeout. Returns None on
    any failure so the gateway falls back to the next provider.
    """
    global _nvidia_disabled
    key = _nvidia_key()
    if not key:
        return None

    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode()
        content: Any = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type or 'image/png'};base64,{b64}"}},
        ]
        model = _NVIDIA_VISION_MODEL
        timeout = timeout_s or 120.0
    else:
        content = prompt
        model = _NVIDIA_MODEL
        timeout = timeout_s or 45.0

    try:
        resp = httpx.post(
            _NVIDIA_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0,
            },
            timeout=timeout,
        )
        if resp.status_code in (401, 403):
            logger.error("NVIDIA key rejected — skipping NVIDIA for the rest of this process.")
            _nvidia_disabled = True
            return None
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        logger.warning("NVIDIA call failed (%s) — trying next provider.", exc)
        return None


def _openai_complete(prompt: str, image_bytes: Optional[bytes], mime_type: Optional[str], timeout_s: Optional[float] = None) -> Optional[str]:
    global _openai_disabled
    key = _openai_key()
    if not key:
        return None
    content: Any = prompt
    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode()
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type or 'image/png'};base64,{b64}"}},
        ]
    try:
        resp = httpx.post(
            _OPENAI_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": _OPENAI_MODEL,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0,
            },
            timeout=timeout_s or 45.0,
        )
        if resp.status_code in (401, 403):
            logger.error("OpenAI key rejected (%s) — falling back to Gemini for this process.", resp.status_code)
            _openai_disabled = True
            return None
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        logger.warning("OpenAI call failed (%s) — trying Gemini fallback.", exc)
        return None


def _gemini_complete(prompt: str, image_bytes: Optional[bytes], mime_type: Optional[str], timeout_s: Optional[float] = None) -> Optional[str]:
    if not GEMINI_AVAILABLE:
        return None
    try:
        model = genai.GenerativeModel(_GEMINI_MODEL)
        parts: list[Any] = [prompt]
        if image_bytes is not None:
            parts.append({"mime_type": mime_type or "image/png", "data": image_bytes})
        opts = {"timeout": timeout_s} if timeout_s else None
        resp = model.generate_content(parts, request_options=opts) if opts else model.generate_content(parts)
        return (resp.text or "").strip()
    except Exception as exc:
        logger.warning("Gemini call failed: %s", exc)
        return None


def ai_text(
    prompt: str,
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> Optional[str]:
    """
    Run the prompt (optionally with an image) through the best available
    provider. Returns the raw text answer, or None when no provider succeeds.
    ``timeout_s`` bounds each provider call — pass a short value on interactive
    paths so a slow model never blocks the UI.
    """
    return (
        _nvidia_complete(prompt, image_bytes, mime_type, timeout_s)
        or _openai_complete(prompt, image_bytes, mime_type, timeout_s)
        or _gemini_complete(prompt, image_bytes, mime_type, timeout_s)
    )


def strip_json(text: Optional[str]) -> Optional[Any]:
    """Extract and parse the JSON object/array from an LLM answer."""
    if not text:
        return None
    t = text.strip()
    if "```json" in t:
        t = t.split("```json")[1].split("```")[0].strip()
    elif "```" in t:
        t = t.split("```")[1].split("```")[0].strip()
    start = min((i for i in (t.find("{"), t.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    end = max(t.rfind("}"), t.rfind("]"))
    if end <= start:
        return None
    try:
        return json.loads(t[start:end + 1])
    except ValueError:
        return None


def ai_json(
    prompt: str,
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> Optional[Any]:
    """ai_text + JSON extraction. Returns the parsed object, or None."""
    return strip_json(ai_text(prompt, image_bytes, mime_type, timeout_s))
