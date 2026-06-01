"""
Shared pytest fixtures for the ADM Copilot backend test suite.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client wired directly to the FastAPI app (no network)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
