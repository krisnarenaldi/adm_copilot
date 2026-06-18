"""
Unit tests for POST /fare-rules endpoint.

Tests cover:
  - 200: valid JWT + valid PDF + valid airline_code → success response
  - 401: missing Authorization header
  - 401: invalid/expired JWT
  - 422: empty airline_code
  - 422: non-PDF content type rejected
  - 422: PDF but not a Fare Rules document (content validation)
  - 422: ingestion pipeline raises an exception
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from models import ExtractionError, UserClaims


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CLAIMS = UserClaims(sub="user@example.com", exp=9999999999, iat=1000000000)

_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
)


def _auth_header(token: str = "valid.jwt.token") -> dict:
    return {"Authorization": f"Bearer {token}"}


def _patch_extractor(result="Some fare rule text."):
    """Patch PDFExtractor.extract_text to return *result*."""
    mock_ext = MagicMock()
    mock_ext.extract_text.return_value = result
    return patch("main.PDFExtractor", return_value=mock_ext)


def _patch_content_validator_fare_rules(result: bool = True):
    """Patch ContentValidator.is_fare_rules_document to return *result*."""
    return patch("main.ContentValidator.is_fare_rules_document", return_value=result)


# ---------------------------------------------------------------------------
# POST /fare-rules tests
# ---------------------------------------------------------------------------

class TestFareRulesEndpoint:
    """Integration tests for POST /fare-rules via the FastAPI test client."""

    def _patch_auth(self, claims: UserClaims | None = _VALID_CLAIMS):
        """Patch AuthService so verify_jwt returns *claims*."""
        mock_svc = MagicMock()
        mock_svc.verify_jwt.return_value = claims
        return patch("main.AuthService", return_value=mock_svc)

    def _patch_pipeline(self, side_effect=None, return_value=(True, "Fare rules for GA ingested successfully")):
        """Patch IngestionPipeline.ingest_document."""
        mock_pipeline = MagicMock()
        if side_effect:
            mock_pipeline.ingest_document.side_effect = side_effect
        else:
            mock_pipeline.ingest_document.return_value = return_value
        return patch("main.IngestionPipeline", return_value=mock_pipeline)

    @pytest.mark.asyncio
    async def test_success_returns_200(self, client):
        with self._patch_auth(), _patch_extractor(), _patch_content_validator_fare_rules(True), self._patch_pipeline():
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("fare_rules.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert "GA" in body["message"]

    @pytest.mark.asyncio
    async def test_missing_authorization_returns_401(self, client):
        response = await client.post(
            "/fare-rules",
            files={"file": ("fare_rules.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
            data={"airline_code": "GA"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_401(self, client):
        with self._patch_auth(claims=None):
            response = await client.post(
                "/fare-rules",
                headers=_auth_header("bad.token"),
                files={"file": ("fare_rules.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_airline_code_returns_422(self, client):
        with self._patch_auth():
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("fare_rules.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": ""},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_pdf_content_type_returns_422(self, client):
        """A file with a non-PDF content type must be rejected."""
        with self._patch_auth():
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"Some text"), "text/plain")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422
        assert "Only PDF files" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_not_fare_rules_content_returns_422(self, client):
        """PDF that doesn't contain Fare Rules keywords must be rejected."""
        with self._patch_auth(), _patch_extractor("This is a FAQ about travel policies."), _patch_content_validator_fare_rules(False):
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("faq.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422
        assert "does not appear to be a Fare Rules" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_ingestion_exception_returns_422(self, client):
        with self._patch_auth(), _patch_extractor(), _patch_content_validator_fare_rules(True), self._patch_pipeline(return_value=(False, "Failed to process document: parse error")):
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("fare_rules.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_success_message_contains_airline_code(self, client):
        with self._patch_auth(), _patch_extractor(), _patch_content_validator_fare_rules(True), self._patch_pipeline(return_value=(True, "Fare rules for SQ ingested successfully")):
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("fare_rules.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "SQ"},
            )
        assert response.status_code == 200
        assert "SQ" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_bearer_prefix_required(self, client):
        """Authorization header without 'Bearer ' prefix must return 401."""
        with self._patch_auth():
            response = await client.post(
                "/fare-rules",
                headers={"Authorization": "valid.jwt.token"},  # missing "Bearer "
                files={"file": ("fare_rules.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 401
