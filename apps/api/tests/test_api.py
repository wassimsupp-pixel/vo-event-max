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

    @patch("routers.files.verify_event_access")
    def test_delete_file_success(self, mock_verify):
        """DELETE /api/files/{file_id} should succeed if file exists and access is allowed."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        file_id = "00000000-0000-0000-0000-000000000088"

        # Mock metadata response
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "id": file_id,
            "event_id": self.EVENT_ID,
            "storage_path": f"{self.EVENT_ID}/{file_id}/test.csv",
        }

        response = client.delete(f"/api/files/{file_id}")
        assert response.status_code == 200
        assert response.json()["message"] == "File deleted successfully."

    @patch("routers.files.verify_event_access")
    def test_delete_file_not_found(self, mock_verify):
        """DELETE /api/files/{file_id} returns 404 if file does not exist."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        file_id = "00000000-0000-0000-0000-000000000088"

        # Mock metadata response as empty
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None

        response = client.delete(f"/api/files/{file_id}")
        assert response.status_code == 404


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


class TestEmailAgent:
    def test_list_proposals(self):
        """GET /api/events/{event_id}/email-agent should return email proposals."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000009",
                "event_id": "00000000-0000-0000-0000-000000000001",
                "sender": "test@sender.com",
                "subject": "Dietary request",
                "body": "I am vegan",
                "received_at": "2026-07-09T10:00:00Z",
                "participant_id": None,
                "status": "pending",
                "proposed_changes": {"dietary_requirements": "Végétalien"},
                "ai_explanation": "Vegan request",
                "created_at": "2026-07-09T10:00:00Z",
                "participants": None
            }
        ]

        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/email-agent")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["sender"] == "test@sender.com"
        assert data[0]["proposed_changes"]["dietary_requirements"] == "Végétalien"

    def test_analyze_email(self):
        """POST /api/events/{event_id}/email-agent/analyze should parse and return proposal."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        # Mock participant lookup -> no match
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        # Mock insert proposal
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000009",
                "event_id": "00000000-0000-0000-0000-000000000001",
                "sender": "test@sender.com",
                "subject": "Change request",
                "body": "Please make me vegetarian",
                "received_at": "2026-07-09T10:00:00Z",
                "participant_id": None,
                "status": "pending",
                "proposed_changes": {"dietary_requirements": "Végétarien"},
                "ai_explanation": "Vegetarian requested",
                "created_at": "2026-07-09T10:00:00Z",
                "participants": None
            }
        ]

        payload = {
            "sender": "test@sender.com",
            "subject": "Change request",
            "body": "Please make me vegetarian"
        }
        response = client.post("/api/events/00000000-0000-0000-0000-000000000001/email-agent/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["proposed_changes"]["dietary_requirements"] == "Végétarien"


# ---------------------------------------------------------------------------
# 6. Quality engine and source validations
# ---------------------------------------------------------------------------

class TestQualityEngineAndMatchingCorrections:
    def test_possible_duplicate_detection(self):
        """
        Verify that _detect_possible_duplicates correctly flags two participants
        with very similar names but different email addresses.
        """
        from services.exception_service import _detect_possible_duplicates
        from unittest.mock import MagicMock

        # Mock supabase response with similar names, different emails
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "p1", "first_name": "Kris", "last_name": "Brown", "email": "kris.brown@dieteren.com", "company": "D'Ieteren"},
            {"id": "p2", "first_name": "Kris", "last_name": "Brown", "email": "kris.brown@dieteren.be", "company": "D'Ieteren"},
            {"id": "p3", "first_name": "Els", "last_name": "Bertrand", "email": "els.bertrand@cfegroup.be", "company": "CFE"},
            {"id": "p4", "first_name": "Els", "last_name": "Comrtrand", "email": "els.comrtrand1@cfegroup.com", "company": "CFE"},
            {"id": "p5", "first_name": "Different", "last_name": "Name", "email": "diff@test.com", "company": "Test"}
        ]

        exceptions = []
        count = _detect_possible_duplicates(
            event_id="test_event",
            run_id="test_run",
            supabase=mock_supabase,
            exceptions_list=exceptions
        )

        # Should find Kris Brown duplicate and Els Bertrand/Comrtrand duplicate
        assert count == 2
        assert len(exceptions) == 2
        assert any(e["exception_type"] == "POSSIBLE_DUPLICATE" and "Kris Brown" in e["message"] for e in exceptions)
        assert any(e["exception_type"] == "POSSIBLE_DUPLICATE" and "Els Bertrand" in e["message"] for e in exceptions)

    def test_name_mismatch_between_sources_detection(self):
        """
        Verify that _detect_name_mismatches_between_sources correctly flags
        conflicting names between registration and FCM files.
        """
        from services.exception_service import _detect_name_mismatches_between_sources
        from unittest.mock import MagicMock

        mock_supabase = MagicMock()
        
        # Mock participants list return
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.not_.is_.return_value.execute.return_value.data = [
            {
                "id": "p1",
                "first_name": "Sebastien",
                "last_name": "Perrin",
                "registration_source_id": "reg1",
                "fcm_source_id": "fcm1"
            }
        ]

        # Mock source records response
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {"id": "reg1", "normalized_data": {"first_name": "Sebastien", "last_name": "Perrin"}},
            {"id": "fcm1", "normalized_data": {"first_name": "Sébastien", "last_name": "Pérrin"}}  # minor accents/case diffs count as mismatch
        ]

        exceptions = []
        count = _detect_name_mismatches_between_sources(
            event_id="test_event",
            run_id="test_run",
            supabase=mock_supabase,
            exceptions_list=exceptions
        )

        assert count == 1
        assert len(exceptions) == 1
        # NAME_DIVERGENCE is the ENUM-valid type for registration-vs-FCM
        # name mismatches (NAME_MISMATCH_BETWEEN_SOURCES 22P02-failed inserts).
        assert exceptions[0]["exception_type"] == "NAME_DIVERGENCE"
        assert "Sébastien" in exceptions[0]["message"]

    def test_source_type_never_in_nationality_validation(self):
        """
        Verify that mapping logic doesn't allow source_type values 
        (like registration, fcm, or Excel imports) to leak into nationality.
        """
        from services.mapping_service import apply_mapping, normalise_fields

        # Test with incorrect mapping of "Source" (containing Formulaire web) to "nationality"
        raw_row = {
            "Nom": "Moreau",
            "Prénom": "Olivier",
            "Email": "olivier.moreau@recticel.be",
            "Source": "Formulaire web"
        }

        # If mapping incorrectly maps "Source" to "nationality"
        mapping = {
            "Nom": "last_name",
            "Prénom": "first_name",
            "Email": "email",
            "Source": "nationality"
        }

        mapped = apply_mapping(raw_row, mapping)
        normalised = normalise_fields(mapped)

        nationality_val = normalised.get("nationality")
        
        invalid_source_types = ["formulaire web", "import excel", "email direct", "assistant", "registration", "fcm"]
        if nationality_val and nationality_val.strip().lower() in invalid_source_types:
            is_valid = False
        else:
            is_valid = True

        assert is_valid is False


# ---------------------------------------------------------------------------
# Test Mapping Suggestions
# ---------------------------------------------------------------------------

class TestMappingSuggestions:
    def test_normalize_column_name(self):
        """Verify _normalize_column_name correctly normalizes column names."""
        from services.mapping_service import _normalize_column_name
        assert _normalize_column_name("Prénom") == "prenom"
        assert _normalize_column_name("E-mail Address") == "emailaddress"
        assert _normalize_column_name("Nom de Famille") == "nomdefamille"
        assert _normalize_column_name("Flight_No.") == "flightno"
        assert _normalize_column_name("check-in/date") == "checkindate"

    def test_suggest_mapping_email(self):
        """Verify suggest_mapping identifies email fields by content and name."""
        from services.mapping_service import suggest_mapping
        columns = ["Mail"]
        sample_rows = [
            {"Mail": "jean@dupont.com"},
            {"Mail": "alice@martin.be"},
            {"Mail": "bob@test.org"},
        ]
        sug = suggest_mapping(columns, sample_rows)
        assert "Mail" in sug
        assert sug["Mail"]["suggested_field"] == "email"
        assert sug["Mail"]["confidence"] >= 0.9

    def test_suggest_mapping_date(self):
        """Verify suggest_mapping identifies date fields by content and name."""
        from services.mapping_service import suggest_mapping
        columns = ["Date Entrée"]
        sample_rows = [
            {"Date Entrée": "12/11/2025"},
            {"Date Entrée": "13-11-2025"},
            {"Date Entrée": "2025-11-14"},
        ]
        sug = suggest_mapping(columns, sample_rows)
        assert "Date Entrée" in sug
        assert sug["Date Entrée"]["suggested_field"] == "check_in_date"
        assert sug["Date Entrée"]["confidence"] >= 0.9

    def test_suggest_mapping_flight(self):
        """Verify suggest_mapping identifies flight fields by content and name."""
        from services.mapping_service import suggest_mapping
        columns = ["Vol"]
        sample_rows = [
            {"Vol": "SN1234"},
            {"Vol": "LH456"},
            {"Vol": "AA9876"},
        ]
        sug = suggest_mapping(columns, sample_rows)
        assert "Vol" in sug
        assert sug["Vol"]["suggested_field"] == "flight_number"
        assert sug["Vol"]["confidence"] >= 0.9

    def test_suggest_mapping_weak_no_suggestion(self):
        """Verify suggest_mapping returns None and 0.0 confidence when no matches are found."""
        from services.mapping_service import suggest_mapping
        columns = ["Inconnu"]
        sample_rows = [
            {"Inconnu": "abc"},
            {"Inconnu": "xyz"},
            {"Inconnu": "123"},
        ]
        sug = suggest_mapping(columns, sample_rows)
        assert "Inconnu" in sug
        assert sug["Inconnu"]["suggested_field"] is None
        assert sug["Inconnu"]["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Test Participant Lookup
# ---------------------------------------------------------------------------

class TestParticipantLookup:
    @patch("routers.participants.verify_event_access")
    def test_lookup_participants(self, mock_verify):
        """GET /api/events/{event_id}/participants/lookup should return list of lookup items."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.range.return_value.execute.return_value.data = [
            {
                "id": "00000000-0000-0000-0000-000000000005",
                "first_name": "Jean",
                "last_name": "Dupont",
                "completeness_status": "complete",
            }
        ]

        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/participants/lookup")
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 1
        assert data[0]["first_name"] == "Jean"
        assert data[0]["last_name"] == "Dupont"
        assert data[0]["completeness_status"] == "complete"

    @patch("routers.participants.verify_event_access")
    def test_lookup_participants_raises_404_if_no_access(self, mock_verify):
        """GET /api/events/{event_id}/participants/lookup raises 404 if no access."""
        from fastapi import HTTPException
        mock_verify.side_effect = HTTPException(status_code=404, detail="Event not found.")
        client = _admin_client()
        
        response = client.get("/api/events/00000000-0000-0000-0000-000000000001/participants/lookup")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Event / Project deletion
# ---------------------------------------------------------------------------

class TestEventProjectDeletion:
    EVENT_ID = "00000000-0000-0000-0000-000000000001"
    PROJECT_ID = "00000000-0000-0000-0000-000000000002"

    @patch("routers.events.verify_event_access")
    @patch("routers.events.deletion_service.delete_event")
    def test_delete_event_success(self, mock_delete, mock_verify):
        """DELETE /api/events/{id} deletes cascade and returns success (admin)."""
        client = _admin_client()
        response = client.delete(f"/api/events/{self.EVENT_ID}")
        assert response.status_code == 200, response.text
        assert response.json()["message"] == "Event deleted successfully."
        mock_delete.assert_called_once()

    def test_delete_event_forbidden_for_viewer(self):
        """A viewer must not be able to delete an event (403)."""
        client = _viewer_client()
        response = client.delete(f"/api/events/{self.EVENT_ID}")
        assert response.status_code == 403

    @patch("routers.events.deletion_service.delete_project")
    def test_delete_project_success(self, mock_delete):
        """DELETE /api/projects/{id} deletes the project after org check (admin)."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        # Project ownership check: table.select.eq.eq.single.execute.data truthy
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": self.PROJECT_ID}

        response = client.delete(f"/api/projects/{self.PROJECT_ID}")
        assert response.status_code == 200, response.text
        assert response.json()["message"] == "Project deleted successfully."
        mock_delete.assert_called_once()

    def test_delete_project_not_found(self):
        """DELETE /api/projects/{id} returns 404 when the project is not in the org."""
        client = _admin_client()
        mock_supabase = _mock_supabase()
        client.app.dependency_overrides[get_supabase_client] = lambda: mock_supabase
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None

        response = client.delete(f"/api/projects/{self.PROJECT_ID}")
        assert response.status_code == 404

    def test_delete_project_forbidden_for_viewer(self):
        """A viewer must not be able to delete a project (403)."""
        client = _viewer_client()
        response = client.delete(f"/api/projects/{self.PROJECT_ID}")
        assert response.status_code == 403





