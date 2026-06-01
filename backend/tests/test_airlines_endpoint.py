"""
Unit tests for GET /airlines endpoint.

Tests cover:
  - 200: returns a list of airline objects with code and name
  - 200: returns an empty list when no airlines exist
  - 200: endpoint is accessible without an Authorization header (public)
  - 502: Supabase query raises an exception
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_supabase_mock(rows: list[dict]) -> MagicMock:
    """Return a mock Supabase client whose airlines query returns *rows*."""
    mock_response = MagicMock()
    mock_response.data = rows

    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.execute.return_value = mock_response

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query

    return mock_db


# ---------------------------------------------------------------------------
# GET /airlines tests
# ---------------------------------------------------------------------------

class TestAirlinesEndpoint:
    """Tests for GET /airlines via the FastAPI test client."""

    @pytest.mark.asyncio
    async def test_returns_200_with_airline_list(self, client):
        """A populated airlines table returns a list of code/name objects."""
        rows = [
            {"code": "GA", "name": "Garuda Indonesia"},
            {"code": "SQ", "name": "Singapore Airlines"},
        ]
        mock_db = _make_supabase_mock(rows)

        with patch("main._get_supabase_client", return_value=mock_db):
            response = await client.get("/airlines")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert {"code": "GA", "name": "Garuda Indonesia"} in body
        assert {"code": "SQ", "name": "Singapore Airlines"} in body

    @pytest.mark.asyncio
    async def test_each_item_has_code_and_name(self, client):
        """Every item in the response must have exactly 'code' and 'name' keys."""
        rows = [
            {"code": "JT", "name": "Lion Air"},
            {"code": "QG", "name": "Citilink"},
        ]
        mock_db = _make_supabase_mock(rows)

        with patch("main._get_supabase_client", return_value=mock_db):
            response = await client.get("/airlines")

        assert response.status_code == 200
        for item in response.json():
            assert set(item.keys()) == {"code", "name"}

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_airlines(self, client):
        """An empty airlines table returns an empty JSON array."""
        mock_db = _make_supabase_mock([])

        with patch("main._get_supabase_client", return_value=mock_db):
            response = await client.get("/airlines")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_accessible_without_authorization_header(self, client):
        """GET /airlines must succeed with no Authorization header (public endpoint)."""
        mock_db = _make_supabase_mock([{"code": "GA", "name": "Garuda Indonesia"}])

        with patch("main._get_supabase_client", return_value=mock_db):
            response = await client.get("/airlines")  # no headers

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_supabase_error_returns_502(self, client):
        """If the Supabase query raises an exception, the endpoint returns 502."""
        with patch("main._get_supabase_client", side_effect=RuntimeError("DB unavailable")):
            response = await client.get("/airlines")

        assert response.status_code == 502
