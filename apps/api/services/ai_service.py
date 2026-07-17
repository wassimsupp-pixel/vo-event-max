"""
services/ai_service.py — Unified AI gateway for every intelligent step
(auto-mapping, file analysis, poster recognition, quality summaries, email
agent, campaign generation).

Provider policy (first usable wins, automatic fallback on failure):
  1. NVIDIA NIM (env ``NVIDIA_API_KEY``, Mistral ``mistralai/mistral-nemotron``)
     — used FIRST for text reasoning (mapping, fusion, analysis). OpenAI-
     compatible endpoint. Text-only.
  2. OpenAI (env ``OPENAI_API_KEY``, gpt-4o-mini) — vision-capable; also the
     fallback for text.
  3. Google Gemini (env ``GEMINI_API_KEY``, gemini-1.5-flash) — final fallback.

An invalid key is detected once (401/403) and that provider is skipped for the
rest of the process — no added latency on later calls. Image prompts skip
NVIDIA (text-only) and go straight to a vision-capable provider.
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
_NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "mistralai/mistral-nemotron")
_nvidia_disabled = False

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_MODEL = "gpt-4o-mini"
_openai_disabled = False

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


def _openai_compatible_complete(url: str, key: str, model: str, prompt: str) -> tuple[Optional[str], bool]:
    """
    POST an OpenAI-style chat completion. Returns (text, invalid_key). Text-only.
    ``invalid_key`` is True on 401/403 so the caller can disable that provider.
    """
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=45.0,
        )
        if resp.status_code in (401, 403):
            return None, True
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"]["content"] or "").strip(), False
    except Exception as exc:
        logger.warning("%s call failed: %s", url.split("/")[2], exc)
        return None, False


def _nvidia_complete(prompt: str, image_bytes: Optional[bytes]) -> Optional[str]:
    global _nvidia_disabled
    key = _nvidia_key()
    if not key or image_bytes is not None:   # NVIDIA text model — no vision here
        return None
    text, invalid = _openai_compatible_complete(_NVIDIA_URL, key, _NVIDIA_MODEL, prompt)
    if invalid:
        logger.error("NVIDIA key rejected — skipping NVIDIA for the rest of this process.")
        _nvidia_disabled = True
    return text


def _openai_complete(prompt: str, image_bytes: Optional[bytes], mime_type: Optional[str]) -> Optional[str]:
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
            timeout=45.0,
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


def _gemini_complete(prompt: str, image_bytes: Optional[bytes], mime_type: Optional[str]) -> Optional[str]:
    if not GEMINI_AVAILABLE:
        return None
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        parts: list[Any] = [prompt]
        if image_bytes is not None:
            parts.append({"mime_type": mime_type or "image/png", "data": image_bytes})
        resp = model.generate_content(parts)
        return (resp.text or "").strip()
    except Exception as exc:
        logger.warning("Gemini call failed: %s", exc)
        return None


def ai_text(
    prompt: str,
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> Optional[str]:
    """
    Run the prompt (optionally with an image) through the best available
    provider. Returns the raw text answer, or None when no provider succeeds.
    """
    return (
        _nvidia_complete(prompt, image_bytes)
        or _openai_complete(prompt, image_bytes, mime_type)
        or _gemini_complete(prompt, image_bytes, mime_type)
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
) -> Optional[Any]:
    """ai_text + JSON extraction. Returns the parsed object, or None."""
    return strip_json(ai_text(prompt, image_bytes, mime_type))
