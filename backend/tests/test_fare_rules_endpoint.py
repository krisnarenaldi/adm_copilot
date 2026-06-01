"""
Unit tests for POST /fare-rules endpoint.

Tests cover:
  - 200: valid JWT + valid file + valid airline_code → success response
  - 401: missing Authorization header
  - 401: invalid/expired JWT
  - 422: empty airline_code
  - 422: ingestion pipeline raises an exception
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from models import UserClaims


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CLAIMS = UserClaims(sub="user@example.com", exp=9999999999, iat=1000000000)


def _auth_header(token: str = "valid.jwt.token") -> dict:
    return {"Authorization": f"Bearer {token}"}


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
        with self._patch_auth(), self._patch_pipeline():
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"Fare rule content"), "text/plain")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert "GA" in body["message"]

    @pytest.mark.asyncio
    async def test_missing_authorization_returns_401(self, client):
        with self._patch_auth(), self._patch_pipeline():
            response = await client.post(
                "/fare-rules",
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_401(self, client):
        with self._patch_auth(claims=None), self._patch_pipeline():
            response = await client.post(
                "/fare-rules",
                headers=_auth_header("bad.token"),
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_airline_code_returns_422(self, client):
        with self._patch_auth(), self._patch_pipeline():
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": ""},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_ingestion_exception_returns_422(self, client):
        with self._patch_auth(), self._patch_pipeline(return_value=(False, "Failed to process document: parse error")):
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_success_message_contains_airline_code(self, client):
        with self._patch_auth(), self._patch_pipeline(return_value=(True, "Fare rules for SQ ingested successfully")):
            response = await client.post(
                "/fare-rules",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": "SQ"},
            )
        assert response.status_code == 200
        assert "SQ" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_bearer_prefix_required(self, client):
        """Authorization header without 'Bearer ' prefix must return 401."""
        with self._patch_auth(), self._patch_pipeline():
            response = await client.post(
                "/fare-rules",
                headers={"Authorization": "valid.jwt.token"},  # missing "Bearer "
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 401
