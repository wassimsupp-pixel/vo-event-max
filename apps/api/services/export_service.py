"""
services/export_service.py — Excel workbook generator for consolidation exports.

Generates a multi-sheet ``.xlsx`` workbook using openpyxl with:
  Sheet 1 — Master List     : all participants, colour-coded by completeness
  Sheet 2 — Exceptions      : all unresolved exceptions from the run
  Sheet 3 — Summary         : run statistics and metadata
  Sheet 4 — Change Log      : last 500 change entries for the event
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from supabase import Client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------
BRAND_PURPLE   = "806CAF"   # Header background
HEADER_FONT    = "FFFFFF"   # Header text colour
ROW_COMPLETE   = "E3F5EA"   # Green  — participant is complete
ROW_INCOMPLETE = "FEECDF"   # Orange — participant is incomplete
ROW_CONFLICT   = "FBE2E1"   # Red    — participant has data conflicts

SEV_CRITICAL   = "FBE2E1"
SEV_WARNING    = "FEECDF"
SEV_INFO       = "EAF4FB"


def _header_fill() -> PatternFill:
    return PatternFill(start_color=BRAND_PURPLE, end_color=BRAND_PURPLE, fill_type="solid")


def _header_font() -> Font:
    return Font(bold=True, color=HEADER_FONT)


def _row_fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _thin_border() -> Border:
    thin = Side(style="thin", color="CCCCCC")
    return Border(left=thin, right=thin, top=thin, bottom=thin)


def _auto_width(ws, min_width: int = 10, max_width: int = 50) -> None:
    """Adjust column widths based on cell content."""
    for col in ws.columns:
        max_len = max_width
        col_letter = get_column_letter(col[0].column)
        col_max = min_width
        for cell in col:
            try:
                cell_len = len(str(cell.value)) if cell.value is not None else 0
                col_max = max(col_max, cell_len)
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(col_max + 2, max_width)


def _write_header_row(ws, headers: list[str]) -> None:
    """Write a styled header row."""
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill   = _header_fill()
        cell.font   = _header_font()
        cell.border = _thin_border()
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 20


# ---------------------------------------------------------------------------
# Sheet 1 — Master List
# ---------------------------------------------------------------------------

def _build_master_list_sheet(ws, participants: list[dict], conflict_ids: set[str]) -> None:
    """Populate the Master List sheet."""
    ws.title = "Master List"
    ws.freeze_panes = "A2"

    headers = [
        "Last Name", "First Name", "Email", "Company", "Phone", "Nationality",
        "Dietary Requirements", "Has Flight", "Has Hotel", "Has Transfer",
        "Has Activities", "Status", "Verification Note",
    ]
    _write_header_row(ws, headers)

    for row_idx, p in enumerate(participants, start=2):
        values = [
            p.get("last_name"),
            p.get("first_name"),
            p.get("email"),
            p.get("company"),
            p.get("phone"),
            p.get("nationality"),
            p.get("dietary_requirements"),   # will be None for non-admin/pm — set at query level
            "✓" if p.get("has_flight")      else "✗",
            "✓" if p.get("has_hotel")       else "✗",
            "✓" if p.get("has_transfer")    else "✗",
            "✓" if p.get("has_activities")  else "✗",
            p.get("completeness_status", "incomplete"),
            p.get("verification_note"),
        ]

        # Determine row colour
        p_id = str(p.get("id", ""))
        raw_status = p.get("completeness_status", "incomplete")
        if p_id in conflict_ids:
            fill_hex = ROW_CONFLICT
        elif raw_status == "complete":
            fill_hex = ROW_COMPLETE
        else:
            fill_hex = ROW_INCOMPLETE

        fill = _row_fill(fill_hex)
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill   = fill
            cell.border = _thin_border()
            cell.alignment = Alignment(vertical="center")

    _auto_width(ws)


# ---------------------------------------------------------------------------
# Sheet 2 — Exceptions
# ---------------------------------------------------------------------------

def _build_exceptions_sheet(ws, exceptions: list[dict]) -> None:
    """Populate the Exceptions sheet with unresolved exceptions."""
    ws.title = "Exceptions"
    ws.freeze_panes = "A2"

    headers = ["Type", "Severity", "Participant Name", "Message", "Context"]
    _write_header_row(ws, headers)

    # Severity → colour map
    sev_color = {"critical": SEV_CRITICAL, "warning": SEV_WARNING, "info": SEV_INFO}

    for row_idx, exc in enumerate(exceptions, start=2):
        severity = exc.get("severity", "warning")
        context  = exc.get("context_data")
        ctx_str  = str(context) if context else ""

        # Try to build participant name from context
        p_name = (context or {}).get("participant_name", "—") if context else "—"

        values = [
            exc.get("exception_type"),
            severity,
            p_name,
            exc.get("message"),
            ctx_str,
        ]
        fill = _row_fill(sev_color.get(severity, SEV_WARNING))
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill   = fill
            cell.border = _thin_border()
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    _auto_width(ws, max_width=80)


# ---------------------------------------------------------------------------
# Sheet 3 — Summary
# ---------------------------------------------------------------------------

def _build_summary_sheet(ws, run: dict, user_id: str) -> None:
    """Populate the Summary sheet with run statistics."""
    ws.title = "Summary"

    stats: dict = run.get("stats") or {}
    rows = [
        ("Run ID",               run.get("id")),
        ("Event ID",             run.get("event_id")),
        ("Triggered By",         user_id),
        ("Status",               run.get("status")),
        ("Started At",           run.get("started_at")),
        ("Completed At",         run.get("completed_at")),
        ("Generated At",         datetime.now(timezone.utc).isoformat()),
        ("", ""),  # spacer
        ("— Statistics —",       ""),
        ("Total Source Records", stats.get("total_source_records", 0)),
        ("Matched (Certain)",    stats.get("matched_certain", 0)),
        ("Matched (Probable)",   stats.get("matched_probable", 0)),
        ("To Verify",            stats.get("to_verify", 0)),
        ("Not Found",            stats.get("not_found", 0)),
        ("Participants Created", stats.get("participants_created", 0)),
        ("Participants Updated", stats.get("participants_updated", 0)),
        ("Exceptions Count",     stats.get("exceptions_count", 0)),
    ]

    # Header row
    ws.cell(row=1, column=1, value="Key").font   = _header_font()
    ws.cell(row=1, column=1).fill = _header_fill()
    ws.cell(row=1, column=2, value="Value").font = _header_font()
    ws.cell(row=1, column=2).fill = _header_fill()

    for row_idx, (key, value) in enumerate(rows, start=2):
        ws.cell(row=row_idx, column=1, value=key).font  = Font(bold=True)
        ws.cell(row=row_idx, column=2, value=str(value) if value is not None else "")

    _auto_width(ws, min_width=20)


# ---------------------------------------------------------------------------
# Sheet 4 — Change Log
# ---------------------------------------------------------------------------

def _build_change_log_sheet(ws, changes: list[dict]) -> None:
    """Populate the Change Log sheet (last 500 entries)."""
    ws.title = "Change Log"
    ws.freeze_panes = "A2"

    headers = ["Changed At", "User ID", "Entity Type", "Entity ID", "Field", "Old Value", "New Value", "Reason"]
    _write_header_row(ws, headers)

    for row_idx, ch in enumerate(changes, start=2):
        values = [
            ch.get("changed_at"),
            ch.get("user_id"),
            ch.get("entity_type"),
            str(ch.get("entity_id", "")),
            ch.get("field_name"),
            ch.get("old_value"),
            ch.get("new_value"),
            ch.get("change_reason"),
        ]
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = _thin_border()
            cell.alignment = Alignment(vertical="center")

    _auto_width(ws)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

async def generate_excel(
    event_id: str,
    run_id: str,
    user_id: str,
    supabase: Client,
) -> bytes:
    """
    Generate a multi-sheet Excel workbook for a completed consolidation run.

    Parameters
    ----------
    event_id:  UUID of the event.
    run_id:    UUID of the consolidation_run.
    user_id:   UUID of the user requesting the export.
    supabase:  Supabase client.

    Returns
    -------
    Raw ``.xlsx`` bytes, ready to be uploaded to Supabase Storage.
    """
    # --- Load all data ---

    # Run metadata
    run_resp = (
        supabase.table("consolidation_runs")
        .select("*")
        .eq("id", run_id)
        .single()
        .execute()
    )
    run: dict = run_resp.data or {}

    # Participants (all, with dietary_requirements — this export runs server-side
    # as an admin operation; the router enforces who can trigger exports)
    p_resp = (
        supabase.table("participants")
        .select(
            "id, first_name, last_name, email, company, phone, nationality, "
            "dietary_requirements, has_flight, has_hotel, has_transfer, has_activities, "
            "completeness_status, verification_note"
        )
        .eq("event_id", event_id)
        .order("last_name")
        .execute()
    )
    participants: list[dict] = p_resp.data or []

    # Identify participants with DATA_CONFLICT exceptions
    conflict_resp = (
        supabase.table("exceptions")
        .select("participant_id")
        .eq("event_id", event_id)
        .eq("exception_type", "DATA_CONFLICT")
        .eq("resolved", False)
        .execute()
    )
    conflict_ids: set[str] = {
        str(r["participant_id"])
        for r in (conflict_resp.data or [])
        if r.get("participant_id")
    }

    # Unresolved exceptions for this run
    exc_resp = (
        supabase.table("exceptions")
        .select("*")
        .eq("run_id", run_id)
        .eq("resolved", False)
        .order("severity")
        .execute()
    )
    exceptions: list[dict] = exc_resp.data or []

    # Change log (last 500 entries for this event)
    cl_resp = (
        supabase.table("change_log")
        .select("*")
        .eq("event_id", event_id)
        .order("changed_at", desc=True)
        .limit(500)
        .execute()
    )
    changes: list[dict] = list(reversed(cl_resp.data or []))  # chronological order

    # --- Build workbook ---
    wb = Workbook()

    # Sheet 1: Master List
    ws1 = wb.active
    _build_master_list_sheet(ws1, participants, conflict_ids)

    # Sheet 2: Exceptions
    ws2 = wb.create_sheet()
    _build_exceptions_sheet(ws2, exceptions)

    # Sheet 3: Summary
    ws3 = wb.create_sheet()
    _build_summary_sheet(ws3, run, user_id)

    # Sheet 4: Change Log
    ws4 = wb.create_sheet()
    _build_change_log_sheet(ws4, changes)

    # Serialise to bytes
    import io
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
