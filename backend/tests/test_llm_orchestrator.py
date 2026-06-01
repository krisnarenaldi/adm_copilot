"""
Unit tests for LLMOrchestrator.

Tests cover:
  _build_prompt:
    - Contains complete ADM text (no truncation)
    - Contains all chunk texts (no truncation)
    - Contains airline_code from chunks
    - Empty chunks list → uses UNKNOWN as airline_code

  _parse_llm_response (via llm_orchestrator._parse_llm_response):
    - Well-formed response → LLMResponse with correct fields
    - Missing VERDICT → LLMError
    - Unrecognised verdict value → LLMError
    - Missing ANALYSIS → LLMError
    - Empty ANALYSIS → LLMError
    - Missing DISPUTE DRAFT → LLMError
    - Empty DISPUTE DRAFT → LLMError

  run_audit:
    - LLM call failure → LLMError
    - LLM timeout → LLMError
    - Well-formed LLM response → LLMResponse
    - Malformed LLM response → LLMError
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models import Chunk, LLMError, LLMResponse
from llm_orchestrator import LLMOrchestrator, _parse_llm_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(text: str = "Fare rule text.", airline_code: str = "GA") -> Chunk:
    return Chunk(text=text, airline_code=airline_code, relevance_score=0.9)


def _well_formed_response(
    verdict: str = "VALID DISPUTE FOUND",
    analysis: str = "## Analysis\n\nThe booking class Y was violated per clause 3.2.",
    dispute_draft: str = "Dear Revenue Accounting Team,\n\nWe dispute this ADM.",
) -> str:
    return (
        f"VERDICT: {verdict}\n\n"
        f"ANALYSIS:\n{analysis}\n\n"
        f"DISPUTE DRAFT:\n{dispute_draft}"
    )


# ---------------------------------------------------------------------------
# _parse_llm_response — pure parser tests
# ---------------------------------------------------------------------------

class TestParseLLMResponse:
    def test_well_formed_dispute_found(self):
        raw = _well_formed_response("VALID DISPUTE FOUND")
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMResponse)
        assert result.verdict == "VALID DISPUTE FOUND"
        assert result.analysis
        assert result.dispute_draft

    def test_well_formed_no_dispute(self):
        raw = _well_formed_response("VALID ADM / NO DISPUTE")
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMResponse)
        assert result.verdict == "VALID ADM / NO DISPUTE"

    def test_missing_verdict_returns_llm_error(self):
        raw = "ANALYSIS:\nSome analysis.\n\nDISPUTE DRAFT:\nSome draft."
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMError)

    def test_unrecognised_verdict_returns_llm_error(self):
        raw = _well_formed_response("MAYBE DISPUTE")
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMError)

    def test_missing_analysis_returns_llm_error(self):
        raw = "VERDICT: VALID DISPUTE FOUND\n\nDISPUTE DRAFT:\nSome draft."
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMError)

    def test_empty_analysis_returns_llm_error(self):
        raw = "VERDICT: VALID DISPUTE FOUND\n\nANALYSIS:\n\nDISPUTE DRAFT:\nSome draft."
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMError)

    def test_missing_dispute_draft_returns_llm_error(self):
        raw = "VERDICT: VALID DISPUTE FOUND\n\nANALYSIS:\nSome analysis."
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMError)

    def test_empty_dispute_draft_returns_llm_error(self):
        raw = "VERDICT: VALID DISPUTE FOUND\n\nANALYSIS:\nSome analysis.\n\nDISPUTE DRAFT:\n"
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMError)

    def test_analysis_content_preserved(self):
        analysis = "## Policy Analysis\n\nClause 3.2 states penalty of USD 150 for booking class Y."
        raw = _well_formed_response(analysis=analysis)
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMResponse)
        assert "Clause 3.2" in result.analysis
        assert "USD 150" in result.analysis

    def test_dispute_draft_content_preserved(self):
        draft = "Dear Revenue Accounting,\n\nWe formally dispute ADM #12345 dated 2024-01-15."
        raw = _well_formed_response(dispute_draft=draft)
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMResponse)
        assert "ADM #12345" in result.dispute_draft

    def test_case_insensitive_verdict(self):
        raw = "VERDICT: valid dispute found\n\nANALYSIS:\nSome analysis.\n\nDISPUTE DRAFT:\nSome draft."
        result = _parse_llm_response(raw)
        assert isinstance(result, LLMResponse)
        assert result.verdict == "VALID DISPUTE FOUND"


# ---------------------------------------------------------------------------
# LLMOrchestrator._build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def _make_orchestrator(self) -> LLMOrchestrator:
        # Bypass real LLM init by patching ChatGoogleGenerativeAI
        with patch("llm_orchestrator.ChatGoogleGenerativeAI"):
            return LLMOrchestrator(api_key="fake-key")

    def test_prompt_contains_adm_text(self):
        orch = self._make_orchestrator()
        adm_text = "ADM reference: XYZ-2024-001. Penalty: USD 500."
        chunks = [_make_chunk()]
        prompt = orch._build_prompt(adm_text, chunks)
        assert adm_text in prompt

    def test_prompt_contains_all_chunk_texts(self):
        orch = self._make_orchestrator()
        chunks = [
            _make_chunk("Chunk A content", "GA"),
            _make_chunk("Chunk B content", "GA"),
            _make_chunk("Chunk C content", "GA"),
        ]
        prompt = orch._build_prompt("ADM text", chunks)
        assert "Chunk A content" in prompt
        assert "Chunk B content" in prompt
        assert "Chunk C content" in prompt

    def test_prompt_contains_airline_code(self):
        orch = self._make_orchestrator()
        chunks = [_make_chunk(airline_code="SQ")]
        prompt = orch._build_prompt("ADM text", chunks)
        assert "SQ" in prompt

    def test_prompt_empty_chunks_uses_unknown(self):
        orch = self._make_orchestrator()
        prompt = orch._build_prompt("ADM text", [])
        assert "UNKNOWN" in prompt

    def test_no_truncation_of_long_adm_text(self):
        orch = self._make_orchestrator()
        long_adm = "ADM content. " * 500  # ~6500 chars
        chunks = [_make_chunk()]
        prompt = orch._build_prompt(long_adm, chunks)
        assert long_adm in prompt

    def test_no_truncation_of_long_chunk_text(self):
        orch = self._make_orchestrator()
        long_chunk_text = "Fare rule detail. " * 200  # ~3600 chars
        chunks = [_make_chunk(text=long_chunk_text)]
        prompt = orch._build_prompt("ADM text", chunks)
        assert long_chunk_text in prompt


# ---------------------------------------------------------------------------
# LLMOrchestrator.run_audit — integration with mocked LLM
# ---------------------------------------------------------------------------

class TestRunAudit:
    def _make_orchestrator(self) -> LLMOrchestrator:
        with patch("llm_orchestrator.ChatGoogleGenerativeAI"):
            return LLMOrchestrator(api_key="fake-key")

    def test_successful_call_returns_llm_response(self):
        orch = self._make_orchestrator()
        raw = _well_formed_response()
        mock_response = MagicMock()
        mock_response.content = raw
        orch._llm.invoke = MagicMock(return_value=mock_response)

        result = orch.run_audit("ADM text", [_make_chunk()])
        assert isinstance(result, LLMResponse)

    def test_llm_exception_returns_llm_error(self):
        orch = self._make_orchestrator()
        orch._llm.invoke = MagicMock(side_effect=RuntimeError("Connection refused"))

        result = orch.run_audit("ADM text", [_make_chunk()])
        assert isinstance(result, LLMError)

    def test_llm_timeout_returns_llm_error(self):
        orch = self._make_orchestrator()
        orch._llm.invoke = MagicMock(side_effect=TimeoutError("Request timed out"))

        result = orch.run_audit("ADM text", [_make_chunk()])
        assert isinstance(result, LLMError)

    def test_malformed_response_returns_llm_error(self):
        orch = self._make_orchestrator()
        mock_response = MagicMock()
        mock_response.content = "This is not a structured response at all."
        orch._llm.invoke = MagicMock(return_value=mock_response)

        result = orch.run_audit("ADM text", [_make_chunk()])
        assert isinstance(result, LLMError)

    def test_verdict_dispute_found_parsed_correctly(self):
        orch = self._make_orchestrator()
        raw = _well_formed_response("VALID DISPUTE FOUND")
        mock_response = MagicMock()
        mock_response.content = raw
        orch._llm.invoke = MagicMock(return_value=mock_response)

        result = orch.run_audit("ADM text", [_make_chunk()])
        assert isinstance(result, LLMResponse)
        assert result.verdict == "VALID DISPUTE FOUND"

    def test_verdict_no_dispute_parsed_correctly(self):
        orch = self._make_orchestrator()
        raw = _well_formed_response("VALID ADM / NO DISPUTE")
        mock_response = MagicMock()
        mock_response.content = raw
        orch._llm.invoke = MagicMock(return_value=mock_response)

        result = orch.run_audit("ADM text", [_make_chunk()])
        assert isinstance(result, LLMResponse)
        assert result.verdict == "VALID ADM / NO DISPUTE"

    def test_llm_error_has_message(self):
        orch = self._make_orchestrator()
        orch._llm.invoke = MagicMock(side_effect=Exception("Service down"))

        result = orch.run_audit("ADM text", [_make_chunk()])
        assert isinstance(result, LLMError)
        assert result.message
