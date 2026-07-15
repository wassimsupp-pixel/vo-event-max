# -*- coding: utf-8 -*-
"""
campaign_service.py
===================
Bulk personalized email to all participants of an event: either a written
template with {placeholders} substituted per participant, or an AI-generated
message adapted to each participant's data. Delivery goes through the connected
mailbox (mail_connection_service). Each message is tracked in `communications`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional
from uuid import UUID

from supabase import Client

from services import master_list_service, mail_connection_service

logger = logging.getLogger(__name__)

GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    if os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        GEMINI_AVAILABLE = True
except ImportError:
    pass

# Placeholders offered to the user for template mode
PLACEHOLDERS = [
    "first_name", "last_name", "full_name", "email", "company",
    "region", "country", "attendee_category", "job_title", "event_name",
]


def _event_name(supabase: Client, event_id: str) -> str:
    try:
        res = supabase.table("events").select("name").eq("id", event_id).maybe_single().execute()
        return (res.data or {}).get("name") or ""
    except Exception:
        return ""


def _placeholders(row: dict[str, Any], event_name: str) -> dict[str, str]:
    fn = (row.get("first_name") or "").strip()
    ln = (row.get("last_name") or "").strip()
    return {
        "first_name": fn,
        "last_name": ln,
        "full_name": f"{fn} {ln}".strip(),
        "email": row.get("email") or "",
        "company": row.get("company") or "",
        "region": row.get("region") or "",
        "country": row.get("country") or "",
        "attendee_category": row.get("attendee_category") or "",
        "job_title": row.get("job_title") or "",
        "event_name": event_name,
    }


def _apply_template(template: str, ph: dict[str, str]) -> str:
    out = template or ""
    for k, v in ph.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _ai_personalize(instructions: str, ph: dict[str, str]) -> tuple[str, str]:
    """AI-generate a personalized subject+body for one participant."""
    if not GEMINI_AVAILABLE:
        # Fallback: a minimal templated message from the instructions
        subject = f"{ph.get('event_name') or 'Information'}"
        body = f"Bonjour {ph.get('first_name', '')},\n\n{instructions}\n\nCordialement,\nL'équipe organisation"
        return subject, body
    prompt = f"""
    Rédige un e-mail personnalisé et professionnel en français pour un participant à un événement.
    Consigne de l'organisateur : {instructions}

    Données du participant (utilise-les pour personnaliser, n'invente RIEN d'autre) :
    {json.dumps(ph, ensure_ascii=False)}

    Réponds STRICTEMENT en JSON : {{"subject": "...", "body": "..."}}
    """
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        parsed = json.loads(text)
        return parsed.get("subject") or (ph.get("event_name") or "Information"), parsed.get("body") or ""
    except Exception as exc:
        logger.warning("AI personalize failed, using fallback: %s", exc)
        return f"{ph.get('event_name') or 'Information'}", f"Bonjour {ph.get('first_name', '')},\n\n{instructions}\n\nCordialement,"


def _render(mode: str, subject: str, body: str, instructions: str, ph: dict[str, str]) -> tuple[str, str]:
    if mode == "ai":
        return _ai_personalize(instructions, ph)
    return _apply_template(subject, ph), _apply_template(body, ph)


def preview(supabase: Client, event_id: str, mode: str, subject: str, body: str, instructions: str, sample: int = 3) -> dict[str, Any]:
    """Return a few personalized examples + the recipient count."""
    rows = master_list_service.build_master_rows(supabase, event_id)
    recipients = [r for r in rows if (r.get("email") or "").strip()]
    event_name = _event_name(supabase, event_id)
    samples = []
    for r in recipients[:sample]:
        ph = _placeholders(r, event_name)
        subj, bod = _render(mode, subject, body, instructions, ph)
        samples.append({"to": r["email"], "name": ph["full_name"], "subject": subj, "body": bod})
    return {"recipient_count": len(recipients), "without_email": len(rows) - len(recipients), "samples": samples}


async def run_campaign(
    supabase: Client,
    event_id: str,
    mode: str,
    subject: str,
    body: str,
    instructions: str,
    do_send: bool,
    user_id: str,
) -> dict[str, Any]:
    """
    Generate a personalized message per participant, store it in `communications`,
    and (if do_send) send it via the connected mailbox.
    """
    rows = master_list_service.build_master_rows(supabase, event_id)
    event_name = _event_name(supabase, event_id)
    provider = mail_connection_service.connected_provider(event_id) if do_send else None

    generated = sent = skipped = errors = 0
    payloads: list[dict[str, Any]] = []

    for row in rows:
        to = (row.get("email") or "").strip()
        if not to:
            skipped += 1
            continue
        ph = _placeholders(row, event_name)
        subj, bod = _render(mode, subject, body, instructions, ph)

        status = "ready"
        sent_at = None
        if do_send and provider:
            try:
                await asyncio.to_thread(mail_connection_service.send_email, provider, event_id, to, subj, bod)
                status = "sent"
                sent_at = "now()"
                sent += 1
            except Exception as exc:
                logger.warning("Failed to send campaign email to %s: %s", to, exc)
                errors += 1
                status = "ready"

        payloads.append({
            "event_id": event_id,
            "participant_id": row["id"],
            "type": "campaign",
            "channel": "email",
            "subject": subj,
            "body": bod,
            "status": status,
            "sent_at": sent_at,
            "created_by": user_id,
        })
        generated += 1

    # Persist all messages (best-effort — table may not be migrated yet)
    try:
        for i in range(0, len(payloads), 100):
            supabase.table("communications").insert(payloads[i:i + 100]).execute()
    except Exception as exc:
        logger.warning("Could not persist campaign communications (run migration 002?): %s", exc)

    return {
        "generated": generated,
        "sent": sent,
        "skipped_no_email": skipped,
        "errors": errors,
        "provider": provider,
        "delivered": bool(do_send and provider),
    }
