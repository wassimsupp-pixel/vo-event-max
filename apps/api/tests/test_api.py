"""
tests/test_api.py — FastAPI integration tests using TestClient.

Tests use dependency overrides to mock Supabase and JWT verification so
no real credentials are needed in CI.

Test groups:
  - Health check
  - File upload validation (format, size, confirmation gate)
  - Column mapping confirmation gate
  - Participant access control (dietary field restriction)
  - Consolidation service unit tests (matching engine)
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Minimal environment setup (no real Supabase needed for unit tests)
# ---------------------------------------------------------------------------
import os
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

from main import app
from dependencies import get_current_user, get_supabase_client


# ---------------------------------------------------------------------------
# Fixtures and mocks
# ---------------------------------------------------------------------------

MOCK_ADMIN_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "org_id": "00000000-0000-0000-0000-000000000010",
    "email": "admin@test.com",
    "full_name": "Test Admin",
    "role": "admin",
    "preferred_language": "fr",
}

MOCK_VIEWER_USER = {
    "id": "00000000-0000-0000-0000-000000000002",
    "org_id": "00000000-0000-0000-0000-000000000010",
    "email": "viewer@test.com",
    "full_name": "Test Viewer",
    "role": "viewer",
    "preferred_language": "fr",
}


def _mock_supabase() -> MagicMock:
    """Return a MagicMock that mimics the Supabase client interface."""
    mock = MagicMock()
    # Default: all table queries return empty data
    mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None
    mock.table.return_value.select.return_value.execute.return_value.data = []
    return mock


def _admin_client() -> TestClient:
    """TestClient with admin user injected."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_ADMIN_USER
    app.dependency_overrides[get_supabase_client] = _mock_supabase
    return TestClient(app, raise_server_exceptions=False)


def _viewer_client() -> TestClient:
    """TestClient with viewer user injected."""
    app.dependency_overrides[get_current_user] = lambda: MOCK_VIEWER_USER
    app.dependency_overrides[get_supabase_client] = _mock_supabase
    return TestClient(app, raise_server_exceptions=False)


def _unauthenticated_client() -> TestClient:
    """TestClient with no dependency overrides (real auth attempted)."""
    app.dependency_overrides = {}
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_check_returns_200(self):
        """GET /health should return 200 with status=ok."""
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_body(self):
        """GET /health should return correct JSON body."""
        client = TestClient(app)
        body = response = client.get("/health").json()
        assert body["status"] == "ok"
        assert "version" in body

    def test_health_check_no_auth_required(self):
        """GET /health must be accessible without Authorization header."""
        client = _unauthenticated_client()
        response = client.get("/health")
        # Should NOT return 401 (no auth required for health)
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# 2. File upload — format validation
# ---------------------------------------------------------------------------

class TestFileUpload:
    EVENT_ID = "00000000-0000-0000-0000-000000000099"

    def _make_file(self, content: bytes, filename: str, content_type: str):
        return ("file", (filename, io.BytesIO(content), content_type))

    def test_upload_rejects_pdf(self):
        """
        POST /api/files/upload with a .pdf file must return 415 Unsupported Media Type.

        The API only accepts .xlsx, .xls, and .csv files.
        """
        client = _admin_client()
        response = client.post(
            "/api/files/upload",
            data={"event_id": self.EVENT_ID, "source_type": "registration"},
            files=[self._make_file(b"%PDF-1.4 test content", "participants.pdf", "application/pdf")],
        )
        assert response.status_code == 415, f"Expected 415, got {response.status_code}: {response.text}"

    def test_upload_rejects_docx(self):
        """
        POST /api/files/upload with a .docx file must return 415.
        """
        client = _admin_client()
        response = client.post(
            "/api/files/upload",
            data={"event_id": self.EVENT_ID, "source_type": "registration"},
            files=[self._make_file(b"PK fake docx", "report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")],
        )
        assert response.status_code == 415

    def test_upload_rejects_oversized_file(self):
        """
        POST /api/files/upload with a file > 50 MB must return 413 Request Entity Too Large.
        """
        client = _admin_client()
        large_content = b"a" * (51 * 1024 * 1024)  # 51 MB
        response = client.post(
            "/api/files/upload",
            data={"event_id": self.EVENT_ID, "source_type": "registration"},
            files=[self._make_file(large_content, "big.csv", "text/csv")],
        )
        assert response.status_code == 413

    def test_upload_rejects_txt(self):
        """
        POST /api/files/upload with a .txt file must return 415.
        """
        client = _admin_client()
        response = client.post(
            "/api/files/upload",
            data={"event_id": self.EVENT_ID, "source_type": "registration"},
            files=[self._make_file(b"plain text", "data.txt", "text/plain")],
        )
        assert response.status_code == 415


# ---------------------------------------------------------------------------
# 3. Column mapping — confirmation gate
# ---------------------------------------------------------------------------

class TestColumnMapping:
    FILE_ID = "00000000-0000-0000-0000-000000000088"

    def test_column_mapping_requires_confirmation_true(self):
        """
        POST /api/files/{file_id}/map-columns with confirmed=false must be rejected.

        The ``confirmed`` field is a hard gate: the frontend must set it to
        ``true`` only after a human has reviewed the mapping.
        """
        client = _admin_client()
        payload = {
            "mapping": {"Nom": "last_name", "Prénom": "first_name"},
            "confirmed": False,
        }
        response = client.post(
            f"/api/files/{self.FILE_ID}/map-columns",
            json=payload,
        )
        # Pydantic validator raises 422 when confirmed is False
        assert response.status_code in (400, 422), (
            f"Expected 400 or 422, got {response.status_code}: {response.text}"
        )

    def test_column_mapping_rejects_missing_confirmed_field(self):
        """
        POST /api/files/{file_id}/map-columns without the ``confirmed`` field must return 422.
        """
        client = _admin_client()
        payload = {
            "mapping": {"Nom": "last_name"},
            # 'confirmed' field absent
        }
        response = client.post(
            f"/api/files/{self.FILE_ID}/map-columns",
            json=payload,
        )
        assert response.status_code == 422

    def test_column_mapping_schema_validates_confirmed_false(self):
        """
        Unit test: ColumnMappingRequest Pydantic model should raise ValueError for confirmed=False.
        """
        from models.schemas import ColumnMappingRequest
        import pydantic

        with pytest.raises((pydantic.ValidationError, ValueError)):
            ColumnMappingRequest(
                mapping={"A": "last_name"},
                confirmed=False,
            )

    def test_column_mapping_schema_accepts_confirmed_true(self):
        """
        Unit test: ColumnMappingRequest should succeed with confirmed=True.
        """
        from models.schemas import ColumnMappingRequest

        req = ColumnMappingRequest(
            mapping={"Nom": "last_name", "Prénom": "first_name"},
            confirmed=True,
        )
        assert req.confirmed is True
        assert req.mapping["Nom"] == "last_name"


# ---------------------------------------------------------------------------
# 4. Participant access — dietary field restriction
# ---------------------------------------------------------------------------

class TestParticipantDietaryRestriction:
    def test_dietary_stripped_from_schemas_for_viewer(self):
        """
        Unit test: ParticipantResponse for a viewer role should have dietary=None
        after the router strips it (simulated by the _strip_dietary helper).
        """
        from routers.participants import _strip_dietary

        participant = {
            "id": "00000000-0000-0000-0000-000000000001",
            "dietary_requirements": "Halal",
            "first_name": "Alice",
            "last_name": "Martin",
        }
        stripped = _strip_dietary(participant, "viewer")
        assert stripped.get("dietary_requirements") is None

    def test_dietary_retained_for_admin(self):
        """
        Unit test: Admin role should retain the dietary_requirements field.
        """
        from routers.participants import _strip_dietary

        participant = {
            "id": "00000000-0000-0000-0000-000000000001",
            "dietary_requirements": "Vegan",
        }
        retained = _strip_dietary(participant, "admin")
        assert retained.get("dietary_requirements") == "Vegan"

    def test_dietary_retained_for_pm(self):
        """
        Unit test: PM role should retain the dietary_requirements field.
        """
        from routers.participants import _strip_dietary

        participant = {"dietary_requirements": "Gluten-free"}
        retained = _strip_dietary(participant, "pm")
        assert retained.get("dietary_requirements") == "Gluten-free"

    def test_dietary_stripped_for_client(self):
        """Client role should NOT see dietary_requirements."""
        from routers.participants import _strip_dietary

        participant = {"dietary_requirements": "Kosher"}
        stripped = _strip_dietary(participant, "client")
        assert stripped.get("dietary_requirements") is None


# ---------------------------------------------------------------------------
# 5. Matching engine unit tests
# ---------------------------------------------------------------------------

class TestMatchingEngine:
    """Unit tests for the consolidation matching engine (no Supabase needed)."""

    def _reg(self, first: str, last: str, email: str, source_id: str = "reg-1") -> Any:
        from services.consolidation_service import ParticipantRecord
        return ParticipantRecord(source_id, {
            "first_name": first, "last_name": last, "email": email
        })

    def _fcm(self, first: str, last: str, email: str, source_id: str = "fcm-1") -> Any:
        from services.consolidation_service import ParticipantRecord
        return ParticipantRecord(source_id, {
            "first_name": first, "last_name": last, "email": email
        })

    def test_exact_email_match_is_certain(self):
        """Matching FCM → registration via exact email should be CERTAIN."""
        from services.consolidation_service import match_sources

        reg  = self._reg("Alice", "Martin", "alice@example.com", "reg-1")
        fcm  = self._fcm("Alice", "Martin", "alice@example.com", "fcm-1")
        results = match_sources([reg], [fcm])

        assert len(results) == 1
        assert results[0].decision == "certain"
        assert results[0].score == 100.0

    def test_name_match_without_email_is_probable(self):
        """
        High name similarity without email should be at least PROBABLE.
        (Score ≥ 75 but < 95 threshold when no email available on FCM side.)
        """
        from services.consolidation_service import match_sources

        reg  = self._reg("Alice", "Martin", "alice@example.com", "reg-1")
        fcm  = self._fcm("Alice", "Martin", "",                 "fcm-1")  # no email in FCM
        results = match_sources([reg], [fcm])

        assert len(results) == 1
        assert results[0].decision in ("certain", "probable")

    def test_no_match_returns_not_found(self):
        """Completely different names without email overlap → NOT_FOUND."""
        from services.consolidation_service import match_sources

        reg  = self._reg("Alice", "Martin", "alice@example.com", "reg-1")
        fcm  = self._fcm("Zoltan", "Kovacs", "zoltan@example.com", "fcm-1")
        results = match_sources([reg], [fcm])

        assert len(results) == 1
        assert results[0].decision in ("not_found", "to_verify")

    def test_merge_skips_locked_fields(self):
        """
        merge_participant_fields must not overwrite fields that are locked.
        """
        from services.consolidation_service import merge_participant_fields

        existing = {"id": "p1", "first_name": "Alice", "company": "OriginalCo"}
        new_data  = {"first_name": "Alyce",  "company": "NewCo"}
        locked    = {"company": True}  # company is locked

        merged = merge_participant_fields(existing, new_data, locked)
        # company must not be overwritten
        assert merged["company"] == "OriginalCo"
        # first_name (not locked) should be updated
        assert merged["first_name"] == "Alyce"

    def test_merge_does_not_overwrite_with_empty(self):
        """
        merge_participant_fields must not overwrite a value with None or empty string.
        """
        from services.consolidation_service import merge_participant_fields

        existing = {"company": "ExistingCo", "phone": "+32 2 000 0000"}
        new_data  = {"company": None, "phone": ""}
        locked    = {}

        merged = merge_participant_fields(existing, new_data, locked)
        assert merged["company"] == "ExistingCo"
        assert merged["phone"] == "+32 2 000 0000"


# ---------------------------------------------------------------------------
# 6. Normalisation unit tests
# ---------------------------------------------------------------------------

class TestNormalisation:
    def test_email_lowercased(self):
        """Emails must be lowercased during normalisation."""
        from services.mapping_service import normalise_fields
        result = normalise_fields({"email": "Alice.MARTIN@Example.COM"})
        assert result["email"] == "alice.martin@example.com"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace must be stripped from all string fields."""
        from services.mapping_service import normalise_fields
        result = normalise_fields({"first_name": "  Alice  ", "last_name": " Martin "})
        assert result["first_name"] == "Alice"
        assert result["last_name"] == "Martin"

    def test_empty_string_becomes_none(self):
        """Empty strings after strip must become None."""
        from services.mapping_service import normalise_fields
        result = normalise_fields({"phone": "   "})
        assert result["phone"] is None

    def test_date_parsed_to_iso8601(self):
        """European date format dd/mm/yyyy must be converted to yyyy-mm-dd."""
        from services.mapping_service import normalise_fields
        result = normalise_fields({"departure_date": "15/06/2025"})
        assert result["departure_date"] == "2025-06-15"

    def test_apply_mapping_drops_unmapped_columns(self):
        """apply_mapping must discard source columns not in the mapping."""
        from services.mapping_service import apply_mapping
        raw = {"Nom": "Martin", "Prénom": "Alice", "Irrelevant": "xyz"}
        mapping = {"Nom": "last_name", "Prénom": "first_name"}
        result = apply_mapping(raw, mapping)
        assert "last_name"  in result
        assert "first_name" in result
        assert "Irrelevant" not in result
        assert "Nom" not in result
        assert "Prénom" not in result


# ---------------------------------------------------------------------------
# 7. Phase 2 integration tests
# ---------------------------------------------------------------------------

class TestFlights:
    @patch("routers.flights.verify_event_access")
    def test_list_flights(self, mock_verify):
        """GET /api/events/{event_id}/flights should return list of flights."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000005",
                "event_id": "00000000-0000-0000-0000-000000000001",
                "flight_number": "SN3715",
                "departure_airport": "BRU",
                "arrival_airport": "BCN",
                "departure_time": "2025-11-10T10:00:00Z",
                "arrival_time": "2025-11-10T12:00:00Z",
                "status": "confirmed",
                "created_at": "2026-07-08T12:00:00Z",
                "participants": {"first_name": "John", "last_name": "Doe"}
            }
        ]
        
        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/flights")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["flight_number"] == "SN3715"
        assert data[0]["participant_name"] == "John Doe"


class TestHotels:
    @patch("routers.hotels.verify_event_access")
    def test_list_hotels(self, mock_verify):
        """GET /api/events/{event_id}/hotels should return list of hotels."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000006",
                "event_id": "00000000-0000-0000-0000-000000000001",
                "name": "Hotel Arts Barcelona",
                "city": "Barcelona",
                "created_at": "2026-07-08T12:00:00Z"
            }
        ]
        
        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/hotels")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Hotel Arts Barcelona"


class TestTransfers:
    @patch("routers.transfers.verify_event_access")
    def test_list_transfers(self, mock_verify):
        """GET /api/events/{event_id}/transfers should return list of transfers."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000007",
                "event_id": "00000000-0000-0000-0000-000000000001",
                "participant_id": "00000000-0000-0000-0000-000000000002",
                "transfer_type": "arrival",
                "pickup_location": "BCN Airport T1",
                "dropoff_location": "Hotel Arts BCN",
                "pickup_time": "2025-11-10T12:30:00Z",
                "status": "scheduled",
                "created_at": "2026-07-08T12:00:00Z",
                "participants": {"first_name": "Jane", "last_name": "Smith"},
                "flights": {"flight_number": "SN3715"}
            }
        ]
        
        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/transfers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pickup_location"] == "BCN Airport T1"
        assert data[0]["participant_name"] == "Jane Smith"
        assert data[0]["flight_number"] == "SN3715"


class TestActivities:
    @patch("routers.activities.verify_event_access")
    def test_list_activities(self, mock_verify):
        """GET /api/events/{event_id}/activities should return activities list."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000008",
                "event_id": "00000000-0000-0000-0000-000000000001",
                "name": "Barcelona Gothic Quarter Walk",
                "created_at": "2026-07-08T12:00:00Z"
            }
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.count = 5
        
        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/activities")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Barcelona Gothic Quarter Walk"
        assert data[0]["registrations_count"] == 5


class TestReports:
    @patch("routers.reports.verify_event_access")
    def test_get_report_summary(self, mock_verify):
        """GET /api/events/{event_id}/reports/summary should return report aggregate counts."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "p1", "has_flight": True, "has_hotel": False, "has_transfer": True},
            {"id": "p2", "has_flight": False, "has_hotel": True, "has_transfer": False},
        ]

        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/reports/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_registered"] == 2
        assert data["missing_flight"] == 1
        assert data["missing_hotel"] == 1
        assert data["missing_transfer"] == 1


class TestGlobalParticipants:
    def test_get_participant_history(self):
        """GET /api/participants/history should return cross-event presence history for a participant."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        mock_supabase.table.return_value.select.return_value.ilike.return_value.eq.return_value.execute.return_value.data = [
            {
                "email": "alice@test.com",
                "first_name": "Alice",
                "last_name": "Martin",
                "dietary_requirements": "Vegetarian",
                "events": {
                    "name": "Barcelona Kick-off 2025",
                    "start_date": "2025-11-10",
                }
            }
        ]

        response = client.get("/api/global-participants/history?email=alice@test.com")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == "alice@test.com"
        assert data[0]["history"][0]["event_name"] == "Barcelona Kick-off 2025"
        assert data[0]["history"][0]["dietary_requirements"] == "Vegetarian"


class TestEvents:
    @patch("routers.events.require_role")
    def test_create_event(self, mock_role):
        """POST /api/events should insert and return new event."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": "p1"}
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "project_id": "00000000-0000-0000-0000-000000000002",
                "name": "New Blank Event",
                "created_at": "2026-07-09T10:00:00Z",
                "updated_at": "2026-07-09T10:00:00Z",
            }
        ]

        payload = {
            "project_id": "00000000-0000-0000-0000-000000000002",
            "name": "New Blank Event"
        }
        response = client.post("/api/events", json=payload)
        assert response.status_code == 201
        assert response.json()["name"] == "New Blank Event"

    def test_list_events(self):
        """GET /api/events should return list of organization events."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "project_id": "00000000-0000-0000-0000-000000000002",
                "name": "Event One",
                "created_at": "2026-07-09T10:00:00Z",
                "updated_at": "2026-07-09T10:00:00Z",
            }
        ]

        response = client.get("/api/events")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Event One"



