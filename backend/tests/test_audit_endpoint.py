"""
Integration tests for POST /audit endpoint.

Tests cover:
  - 200: valid JWT + valid PDF + valid airline_code → AuditResponse with all three components
  - 401: missing Authorization header
  - 401: invalid/expired JWT
  - 429: rate limit exceeded (includes reset_at in detail)
  - 422: PDF extraction failure
  - 422: no Fare Rules chunks found for airline_code
  - 422: malformed LLM response (parse error)
  - 502: LLM call failure / timeout
  - user_uploads NOT incremented on any error path
  - user_uploads IS incremented on success
"""

from __future__ import annotations

import io
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from models import (
    AuditResponse,
    Chunk,
    ExtractionError,
    LLMError,
    LLMResponse,
    QuotaStatus,
    UserClaims,
)


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

_VALID_CLAIMS = UserClaims(sub="auditor@company.com", exp=9999999999, iat=1000000000)

_VALID_CHUNKS = [
    Chunk(text="Fare rule clause 1: ...", airline_code="GA", relevance_score=0.95),
    Chunk(text="Fare rule clause 2: ...", airline_code="GA", relevance_score=0.88),
]

_VALID_LLM_RESPONSE = LLMResponse(
    verdict="VALID DISPUTE FOUND",
    analysis="## Analysis\n\nThe ADM references booking class Y...",
    dispute_draft="Dear Revenue Accounting Team,\n\nWe dispute this ADM...",
)

_QUOTA_ALLOWED = QuotaStatus(allowed=True, current_count=2, limit=5, reset_at=None)

_RESET_AT = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
_QUOTA_EXCEEDED = QuotaStatus(
    allowed=False,
    current_count=5,
    limit=5,
    reset_at=_RESET_AT,
)

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


def _patch_auth(claims: UserClaims | None = _VALID_CLAIMS):
    """Patch AuthService so verify_jwt returns *claims*."""
    mock_svc = MagicMock()
    mock_svc.verify_jwt.return_value = claims
    return patch("main.AuthService", return_value=mock_svc)


def _patch_rate_limiter(quota: QuotaStatus = _QUOTA_ALLOWED):
    """Patch RateLimiter with a given QuotaStatus."""
    mock_rl = MagicMock()
    mock_rl.check_quota.return_value = quota
    mock_rl.record_upload.return_value = None
    return patch("main.RateLimiter", return_value=mock_rl)


def _patch_extractor(result):
    """Patch PDFExtractor.extract_text to return *result*."""
    mock_ext = MagicMock()
    mock_ext.extract_text.return_value = result
    return patch("main.PDFExtractor", return_value=mock_ext)


def _patch_content_validator_adm(result: bool = True):
    """Patch ContentValidator.is_adm_document to return *result*."""
    return patch("main.ContentValidator.is_adm_document", return_value=result)


def _patch_content_validator_fare_rules(result: bool = True):
    """Patch ContentValidator.is_fare_rules_document to return *result*."""
    return patch("main.ContentValidator.is_fare_rules_document", return_value=result)


def _patch_retriever(chunks):
    """Patch VectorRetriever.retrieve_chunks to return *chunks*."""
    mock_ret = MagicMock()
    mock_ret.retrieve_chunks.return_value = chunks
    return patch("main.VectorRetriever", return_value=mock_ret)


def _patch_orchestrator(result):
    """Patch LLMOrchestrator.run_audit to return *result*."""
    mock_orch = MagicMock()
    mock_orch.run_audit.return_value = result
    return patch("main.LLMOrchestrator", return_value=mock_orch)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestAuditEndpointSuccess:
    """POST /audit — 200 success cases."""

    @pytest.mark.asyncio
    async def test_valid_request_returns_200_with_all_components(self, client):
        """A fully valid request returns 200 with verdict, analysis, and dispute_draft."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("ADM text content"),
            _patch_content_validator_adm(True),
            _patch_retriever(_VALID_CHUNKS),
            _patch_orchestrator(_VALID_LLM_RESPONSE),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["verdict"] == "VALID DISPUTE FOUND"
        assert body["analysis"] == _VALID_LLM_RESPONSE.analysis
        assert body["dispute_draft"] == _VALID_LLM_RESPONSE.dispute_draft

    @pytest.mark.asyncio
    async def test_record_upload_called_on_success(self, client):
        """record_upload must be called exactly once on a successful audit."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_ALLOWED
        mock_rl.record_upload.return_value = None

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever(_VALID_CHUNKS),
            _patch_orchestrator(_VALID_LLM_RESPONSE),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 200
        mock_rl.record_upload.assert_called_once_with("auditor@company.com")

    @pytest.mark.asyncio
    async def test_valid_adm_no_dispute_verdict(self, client):
        """Endpoint correctly returns VALID ADM / NO DISPUTE verdict."""
        no_dispute_response = LLMResponse(
            verdict="VALID ADM / NO DISPUTE",
            analysis="## Analysis\n\nThe ADM is valid.",
            dispute_draft="No dispute is warranted.",
        )
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever(_VALID_CHUNKS),
            _patch_orchestrator(no_dispute_response),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "SQ"},
            )

        assert response.status_code == 200
        assert response.json()["verdict"] == "VALID ADM / NO DISPUTE"


# ---------------------------------------------------------------------------
# Authentication failures (401)
# ---------------------------------------------------------------------------

class TestAuditEndpointAuth:
    """POST /audit — 401 authentication error cases."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header_returns_401(self, client):
        """No Authorization header → 401."""
        response = await client.post(
            "/audit",
            files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
            data={"airline_code": "GA"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authorization_without_bearer_prefix_returns_401(self, client):
        """Authorization header without 'Bearer ' prefix → 401."""
        response = await client.post(
            "/audit",
            headers={"Authorization": "valid.jwt.token"},
            files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
            data={"airline_code": "GA"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_401(self, client):
        """Invalid/expired JWT → 401."""
        with _patch_auth(claims=None):
            response = await client.post(
                "/audit",
                headers=_auth_header("bad.token"),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_does_not_execute_pipeline(self, client):
        """When JWT is invalid, no pipeline step (rate limit, extraction, etc.) executes."""
        mock_rl = MagicMock()
        mock_ext = MagicMock()

        with (
            _patch_auth(claims=None),
            patch("main.RateLimiter", return_value=mock_rl),
            patch("main.PDFExtractor", return_value=mock_ext),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header("bad.token"),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 401
        mock_rl.check_quota.assert_not_called()
        mock_ext.extract_text.assert_not_called()


# ---------------------------------------------------------------------------
# Rate limit exceeded (429)
# ---------------------------------------------------------------------------

class TestAuditEndpointRateLimit:
    """POST /audit — 429 rate limit cases."""

    @pytest.mark.asyncio
    async def test_quota_exceeded_returns_429(self, client):
        """When quota is exceeded, endpoint returns 429."""
        with (
            _patch_auth(),
            _patch_rate_limiter(quota=_QUOTA_EXCEEDED),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_quota_exceeded_response_contains_reset_at(self, client):
        """429 response detail must include the reset timestamp."""
        with (
            _patch_auth(),
            _patch_rate_limiter(quota=_QUOTA_EXCEEDED),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 429
        detail = response.json()["detail"]
        assert "2025-06-01T12:00:00Z" in detail

    @pytest.mark.asyncio
    async def test_quota_exceeded_does_not_increment_counter(self, client):
        """record_upload must NOT be called when quota is exceeded."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_EXCEEDED

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 429
        mock_rl.record_upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_quota_exceeded_does_not_execute_pipeline(self, client):
        """When quota is exceeded, PDF extraction and LLM are not called."""
        mock_ext = MagicMock()
        mock_orch = MagicMock()

        with (
            _patch_auth(),
            _patch_rate_limiter(quota=_QUOTA_EXCEEDED),
            patch("main.PDFExtractor", return_value=mock_ext),
            patch("main.LLMOrchestrator", return_value=mock_orch),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 429
        mock_ext.extract_text.assert_not_called()
        mock_orch.run_audit.assert_not_called()


# ---------------------------------------------------------------------------
# PDF extraction failure (422)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Non-PDF file rejection (422)
# ---------------------------------------------------------------------------

class TestAuditEndpointNonPDF:
    """POST /audit — 422 non-PDF file rejection cases."""

    @pytest.mark.asyncio
    async def test_non_pdf_content_type_returns_422(self, client):
        """A file with content type other than application/pdf → 422."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"Some text content"), "text/plain")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Only PDF files" in detail

    @pytest.mark.asyncio
    async def test_non_pdf_does_not_execute_extraction(self, client):
        """When file is not PDF, extraction and later steps are skipped."""
        mock_ext = MagicMock()

        with (
            _patch_auth(),
            _patch_rate_limiter(),
            patch("main.PDFExtractor", return_value=mock_ext),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 422
        mock_ext.extract_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_pdf_does_not_increment_counter(self, client):
        """record_upload must NOT be called when file is not PDF."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_ALLOWED

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("rules.txt", io.BytesIO(b"content"), "text/plain")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 422
        mock_rl.record_upload.assert_not_called()


# ---------------------------------------------------------------------------
# Content validation failure — not an ADM document (422)
# ---------------------------------------------------------------------------

class TestAuditEndpointContentValidation:
    """POST /audit — 422 content validation failure cases."""

    @pytest.mark.asyncio
    async def test_not_adm_content_returns_422(self, client):
        """When extracted text does not appear to be an ADM → 422."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("This is an FAQ about travel policies."),
            _patch_content_validator_adm(False),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "does not appear to be an ADM" in detail

    @pytest.mark.asyncio
    async def test_not_adm_content_skips_retrieval(self, client):
        """When content validation fails, retrieval and later steps are skipped."""
        mock_ret = MagicMock()

        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("This is an FAQ about travel policies."),
            _patch_content_validator_adm(False),
            patch("main.VectorRetriever", return_value=mock_ret),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 422
        mock_ret.retrieve_chunks.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_adm_content_does_not_increment_counter(self, client):
        """record_upload must NOT be called when content validation fails."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_ALLOWED

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
            _patch_extractor("FAQ document about travel"),
            _patch_content_validator_adm(False),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 422
        mock_rl.record_upload.assert_not_called()


class TestAuditEndpointExtractionFailure:
    """POST /audit — 422 PDF extraction failure cases."""

    @pytest.mark.asyncio
    async def test_extraction_failure_returns_422(self, client):
        """ExtractionError from PDFExtractor → 422."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor(ExtractionError("Corrupt PDF file.")),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(b"not a pdf"), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_extraction_failure_detail_is_descriptive(self, client):
        """422 detail message must describe the extraction failure."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor(ExtractionError("Corrupt PDF file.")),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(b"not a pdf"), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422
        assert "extraction" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_extraction_failure_does_not_increment_counter(self, client):
        """record_upload must NOT be called when extraction fails."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_ALLOWED

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
            _patch_extractor(ExtractionError("Corrupt PDF.")),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(b"bad"), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 422
        mock_rl.record_upload.assert_not_called()


# ---------------------------------------------------------------------------
# No Fare Rules found (422)
# ---------------------------------------------------------------------------

class TestAuditEndpointNoFareRules:
    """POST /audit — 422 no Fare Rules available cases."""

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_422(self, client):
        """Empty chunk list from VectorRetriever → 422."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever([]),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "XX"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_chunks_detail_mentions_airline(self, client):
        """422 detail must mention the airline_code when no rules are found."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever([]),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "XX"},
            )
        assert response.status_code == 422
        assert "XX" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_empty_chunks_does_not_increment_counter(self, client):
        """record_upload must NOT be called when no chunks are found."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_ALLOWED

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever([]),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "XX"},
            )

        assert response.status_code == 422
        mock_rl.record_upload.assert_not_called()


# ---------------------------------------------------------------------------
# LLM failure (502)
# ---------------------------------------------------------------------------

class TestAuditEndpointLLMFailure:
    """POST /audit — 502 LLM call failure cases."""

    @pytest.mark.asyncio
    async def test_llm_call_failure_returns_502(self, client):
        """LLMError from a call/timeout failure → 502."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever(_VALID_CHUNKS),
            _patch_orchestrator(LLMError("AI service call failed: connection timeout")),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_llm_failure_does_not_increment_counter(self, client):
        """record_upload must NOT be called when LLM call fails."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_ALLOWED

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever(_VALID_CHUNKS),
            _patch_orchestrator(LLMError("AI service call failed: timeout")),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 502
        mock_rl.record_upload.assert_not_called()


# ---------------------------------------------------------------------------
# Malformed LLM response (422)
# ---------------------------------------------------------------------------

class TestAuditEndpointMalformedLLM:
    """POST /audit — 422 malformed LLM response cases."""

    @pytest.mark.asyncio
    async def test_malformed_llm_response_returns_422(self, client):
        """LLMError with 'Malformed' in message → 422."""
        with (
            _patch_auth(),
            _patch_rate_limiter(),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever(_VALID_CHUNKS),
            _patch_orchestrator(
                LLMError("Malformed AI response: missing ANALYSIS section.")
            ),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_malformed_llm_response_does_not_increment_counter(self, client):
        """record_upload must NOT be called when LLM response is malformed."""
        mock_rl = MagicMock()
        mock_rl.check_quota.return_value = _QUOTA_ALLOWED

        with (
            _patch_auth(),
            patch("main.RateLimiter", return_value=mock_rl),
            _patch_extractor("ADM text"),
            _patch_content_validator_adm(True),
            _patch_retriever(_VALID_CHUNKS),
            _patch_orchestrator(
                LLMError("Malformed AI response: missing DISPUTE DRAFT section.")
            ),
        ):
            response = await client.post(
                "/audit",
                headers=_auth_header(),
                files={"file": ("adm.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
                data={"airline_code": "GA"},
            )

        assert response.status_code == 422
        mock_rl.record_upload.assert_not_called()
