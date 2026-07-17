"""
routers/reports.py — Reporting and aggregation endpoints.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import ReportSummaryResponse, HotelNightsReportItem
from services import master_list_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/events/{event_id}/reports/analysis",
    summary="Data-quality analysis + recommendations over the master list",
)
async def get_report_analysis(
    event_id: str,
    ai_summary: bool = False,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    """
    Intelligent data-quality analysis (feedback §15): weighted quality score,
    per-dimension breakdown, region/category distributions, missing-info counts,
    and prioritized recommendations, computed from the consolidated master list.
    The AI narrative is generated only with ``?ai_summary=true`` (the dashboard
    omits it to stay fast).
    """
    await verify_event_access(event_id, current_user, supabase)
    return master_list_service.build_analysis(supabase, event_id, include_ai_summary=ai_summary)


@router.get(
    "/events/{event_id}/reports/summary",
    response_model=ReportSummaryResponse,
    summary="Get aggregated statistics report for an event",
)
async def get_report_summary(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ReportSummaryResponse:
    """
    Returns counts for total registered, missing flight, missing hotel, and missing transfers.
    """
    await verify_event_access(event_id, current_user, supabase)

    # Fetch total participants count
    part_res = (
        supabase.table("participants")
        .select("id, has_flight, has_hotel, has_transfer")
        .eq("event_id", event_id)
        .execute()
    )

    total = len(part_res.data)
    missing_flight = sum(1 for p in part_res.data if not p["has_flight"])
    missing_hotel = sum(1 for p in part_res.data if not p["has_hotel"])
    missing_transfer = sum(1 for p in part_res.data if not p["has_transfer"])

    return ReportSummaryResponse(
        total_registered=total,
        missing_flight=missing_flight,
        missing_hotel=missing_hotel,
        missing_transfer=missing_transfer,
    )


@router.get(
    "/events/{event_id}/reports/hotel-nights",
    response_model=list[HotelNightsReportItem],
    summary="Get hotel night occupancy numbers by date",
)
async def get_hotel_nights_report(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[HotelNightsReportItem]:
    """
    Returns night-by-night room counts across all hotels for an event.
    """
    await verify_event_access(event_id, current_user, supabase)

    # Fetch hotels
    hotels_res = supabase.table("hotels").select("id").eq("event_id", event_id).execute()
    hotel_ids = [h["id"] for h in hotels_res.data]

    if not hotel_ids:
        return []

    # Fetch all nights for those hotels
    nights_res = (
        supabase.table("hotel_nights")
        .select("night_date")
        .in_("hotel_id", hotel_ids)
        .eq("status", "confirmed")
        .execute()
    )

    # Count occurrences per date
    counts = Counter(row["night_date"] for row in nights_res.data)

    results = []
    for night_date_str, count in sorted(counts.items()):
        results.append(
            HotelNightsReportItem(
                night_date=date.fromisoformat(night_date_str),
                count=count,
            )
        )

    return results
