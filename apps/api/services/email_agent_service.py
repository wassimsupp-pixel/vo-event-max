# -*- coding: utf-8 -*-
"""
email_agent_service.py
======================
AI service to parse, route, and extract participant request updates from raw email texts.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)

# Try importing Gemini, but degrade gracefully
GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    if os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        GEMINI_AVAILABLE = True
except ImportError:
    pass


class EmailAgentService:
    """Service handling parsing, listing, and applying AI email updates."""

    def __init__(self, supabase_client: Client):
        self.sb = supabase_client

    async def list_proposals(self, event_id: UUID) -> list[dict[str, Any]]:
        """List all email proposals for an event with participant names."""
        try:
            res = self.sb.table("email_proposals") \
                .select("*, participants(first_name, last_name)") \
                .eq("event_id", str(event_id)) \
                .order("created_at", desc=True) \
                .execute()
            
            proposals = []
            for row in res.data:
                part = row.get("participants")
                row["participant_name"] = f"{part['first_name']} {part['last_name']}" if part else None
                proposals.append(row)
            return proposals
        except Exception as e:
            logger.error("Failed to list email proposals: %s", e)
            return []

    async def get_proposal(self, proposal_id: UUID) -> Optional[dict[str, Any]]:
        """Get a specific proposal details."""
        try:
            res = self.sb.table("email_proposals") \
                .select("*, participants(first_name, last_name)") \
                .eq("id", str(proposal_id)) \
                .execute()
            if not res.data:
                return None
            row = res.data[0]
            part = row.get("participants")
            row["participant_name"] = f"{part['first_name']} {part['last_name']}" if part else None
            return row
        except Exception as e:
            logger.error("Failed to get proposal %s: %s", proposal_id, e)
            return None

    async def analyze_email(self, event_id: UUID, sender: str, subject: str, body: str) -> dict[str, Any]:
        """
        Analyze a raw email.
        1. Identify the participant (by matching sender email or name).
        2. Perform AI structural parsing of the change requests.
        3. Store proposal in the DB.
        """
        participant_id: Optional[str] = None
        participant_name: Optional[str] = None

        # Step 1: Lookup participant by email
        try:
            res = self.sb.table("participants") \
                .select("id, first_name, last_name") \
                .eq("event_id", str(event_id)) \
                .eq("email", sender.strip().lower()) \
                .execute()
            
            if res.data:
                participant_id = res.data[0]["id"]
                participant_name = f"{res.data[0]['first_name']} {res.data[0]['last_name']}"
            else:
                # Try simple fuzzy search by extracting name tokens from sender (e.g. "sophie.martin@...")
                sender_local = sender.split("@")[0].replace(".", " ").replace("-", " ")
                res_all = self.sb.table("participants") \
                    .select("id, first_name, last_name") \
                    .eq("event_id", str(event_id)) \
                    .execute()
                
                for p in res_all.data:
                    name_str = f"{p['first_name']} {p['last_name']}".lower()
                    if p["first_name"].lower() in sender_local or p["last_name"].lower() in sender_local:
                        participant_id = p["id"]
                        participant_name = f"{p['first_name']} {p['last_name']}"
                        break
        except Exception as e:
            logger.warning("Participant lookup failed: %s", e)

        # Step 2: Extract details
        proposed_changes: dict[str, Any] = {}
        ai_explanation = ""

        prompt = f"""
        Analyze the following email from a conference participant.
        Subject: {subject}
        Body: {body}

        Extract any request for changing participant records. Allowed fields:
        - first_name
        - last_name
        - email
        - company
        - phone
        - nationality
        - dietary_requirements (regime alimentaire)

        Return a JSON object with two fields:
        1. "changes": a dictionary of updated fields (keys: standard names above, values: extracted updates).
        2. "explanation": a short text explaining why the change was proposed and what it represents.

        If no changes can be extracted or mapped, return empty changes.
        """

        if GEMINI_AVAILABLE:
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(prompt)
                text = response.text.strip()
                # Clean markdown blocks if returned
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                
                parsed = json.loads(text)
                proposed_changes = parsed.get("changes", {})
                ai_explanation = parsed.get("explanation", "Parsed via Gemini AI.")
            except Exception as e:
                logger.error("Gemini processing failed, using fallback: %s", e)
                proposed_changes, ai_explanation = self._rule_based_fallback(subject, body)
        else:
            proposed_changes, ai_explanation = self._rule_based_fallback(subject, body)

        # Step 3: Insert into database
        try:
            proposal_row = {
                "event_id": str(event_id),
                "sender": sender,
                "subject": subject,
                "body": body,
                "participant_id": participant_id,
                "status": "pending",
                "proposed_changes": proposed_changes,
                "ai_explanation": ai_explanation
            }
            
            res_ins = self.sb.table("email_proposals").insert(proposal_row).execute()
            new_proposal = res_ins.data[0]
            new_proposal["participant_name"] = participant_name
            return new_proposal
        except Exception as e:
            logger.error("Failed to insert proposal: %s", e)
            # Return transient result for testing/sandbox
            return {
                "id": "00000000-0000-0000-0000-000000000000",
                "event_id": str(event_id),
                "sender": sender,
                "subject": subject,
                "body": body,
                "participant_id": participant_id,
                "status": "pending",
                "proposed_changes": proposed_changes,
                "ai_explanation": ai_explanation,
                "participant_name": participant_name
            }

    async def apply_proposal(self, proposal_id: UUID, user_id: UUID) -> bool:
        """Apply the proposed changes to the participant and lock the fields."""
        proposal = await self.get_proposal(proposal_id)
        if not proposal or proposal["status"] != "pending" or not proposal["participant_id"]:
            return False

        participant_id = proposal["participant_id"]
        changes = proposal["proposed_changes"]

        if not changes:
            return False

        try:
            # 1. Fetch current participant
            part_res = self.sb.table("participants").select("*").eq("id", str(participant_id)).execute()
            if not part_res.data:
                return False
            part = part_res.data[0]
            locked_fields = set(part.get("locked_fields", []))

            # 2. Apply updates and merge locks
            update_payload: dict[str, Any] = {}
            for field, val in changes.items():
                # Even if locked, AI update overrides since it was manually approved
                update_payload[field] = val
                locked_fields.add(field)

            update_payload["locked_fields"] = list(locked_fields)
            update_payload["updated_at"] = "now()"

            self.sb.table("participants").update(update_payload).eq("id", str(participant_id)).execute()

            # 3. Update proposal status
            self.sb.table("email_proposals").update({"status": "applied"}).eq("id", str(proposal_id)).execute()

            # 4. Log audit changes
            for field, val in changes.items():
                old_val = part.get(field, "")
                audit_log = {
                    "event_id": proposal["event_id"],
                    "user_id": str(user_id),
                    "entity": "participant",
                    "field": field,
                    "old_value": str(old_val),
                    "new_value": str(val)
                }
                self.sb.table("change_log").insert(audit_log).execute()

            return True
        except Exception as e:
            logger.error("Failed to apply proposal: %s", e)
            return False

    async def reject_proposal(self, proposal_id: UUID) -> bool:
        """Reject the proposed email change proposal."""
        try:
            self.sb.table("email_proposals").update({"status": "rejected"}).eq("id", str(proposal_id)).execute()
            return True
        except Exception as e:
            logger.error("Failed to reject proposal: %s", e)
            return False

    def _rule_based_fallback(self, subject: str, body: str) -> tuple[dict[str, Any], str]:
        """Simple regex/string match rules when LLM is unavailable."""
        changes: dict[str, Any] = {}
        body_lower = body.lower()

        # Dietary requirements checks
        if "gluten" in body_lower:
            changes["dietary_requirements"] = "Sans gluten"
        elif "vegan" in body_lower or "végétalien" in body_lower:
            changes["dietary_requirements"] = "Végétalien"
        elif "vegetar" in body_lower or "végétar" in body_lower:
            changes["dietary_requirements"] = "Végétarien"
        elif "halal" in body_lower:
            changes["dietary_requirements"] = "Halal"
        elif "kosher" in body_lower or "cascher" in body_lower:
            changes["dietary_requirements"] = "Cascher"

        # Phone checks
        if "tél" in body_lower or "phone" in body_lower:
            import re
            phones = re.findall(r"\+?[0-9][0-9\s.\-\(\)]{7,15}[0-9]", body)
            if phones:
                changes["phone"] = phones[0].strip()

        # Company checks
        if "société" in body_lower or "company" in body_lower or "compagnie" in body_lower:
            lines = body.split("\n")
            for line in lines:
                if "société" in line.lower() or "company" in line.lower():
                    parts = line.split(":")
                    if len(parts) > 1:
                        changes["company"] = parts[1].strip()
                        break

        explanation = "Extrait via l'analyseur déterministe local." if changes else "Aucune demande de modification détectée."
        return changes, explanation
