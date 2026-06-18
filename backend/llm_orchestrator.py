"""
LLMOrchestrator — builds a structured prompt and calls Gemma via LangChain,
then parses the response into { verdict, analysis, dispute_draft }.

Design requirements:
  - run_audit(adm_text, fare_rules_chunks) → LLMResponse | LLMError
  - Build structured prompt containing complete ADM text and all chunk texts
    (no truncation).
  - Call Gemma via langchain_google_genai.ChatGoogleGenerativeAI.
  - Parse response into { verdict, analysis, dispute_draft }.
  - Return LLMError on timeout or call failure.
  - Return LLMError (parse error) if response is malformed.
"""

from __future__ import annotations

import os
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from models import Chunk, LLMError, LLMResponse

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are an expert travel auditor. Analyze the following ADM document against the provided Fare Rules.

## ADM Document
{adm_text}

## Relevant Fare Rules (Airline: {airline_code})
{fare_rules_chunks}

## Instructions
1. Determine if the ADM is disputable based on the Fare Rules.
2. Output your response in the following exact format:

VERDICT: <VALID DISPUTE FOUND | VALID ADM / NO DISPUTE>

ANALYSIS:
<Structured markdown analysis referencing specific policy clauses, dates, booking classes, or penalty amounts>

DISPUTE DRAFT:
<Formal business-English email arguing the case for dispute, or a brief note if no dispute is warranted>"""

# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

_VERDICT_PATTERN = re.compile(
    r"VERDICT:\s*(VALID DISPUTE FOUND|VALID ADM / NO DISPUTE)",
    re.IGNORECASE,
)

# Section markers used for splitting the response into named sections.
_SECTION_PATTERN = re.compile(
    r"^(VERDICT|ANALYSIS|DISPUTE DRAFT):\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _parse_llm_response(raw: str) -> LLMResponse | LLMError:
    """
    Parse the raw LLM output into an LLMResponse.

    Splits the response on section headers (VERDICT:, ANALYSIS:, DISPUTE DRAFT:)
    so each section's content is unambiguous regardless of blank lines.

    Returns LLMError if any required section is missing or empty.
    """
    # --- Extract verdict via dedicated pattern (handles inline value) ---
    verdict_match = _VERDICT_PATTERN.search(raw)
    if not verdict_match:
        return LLMError(
            "Malformed AI response: missing or unrecognised VERDICT section."
        )

    verdict_raw = verdict_match.group(1).strip().upper()
    if verdict_raw == "VALID DISPUTE FOUND":
        verdict = "VALID DISPUTE FOUND"
    elif verdict_raw in ("VALID ADM / NO DISPUTE", "VALID ADM/NO DISPUTE"):
        verdict = "VALID ADM / NO DISPUTE"
    else:
        return LLMError(
            f"Malformed AI response: unrecognised verdict value '{verdict_raw}'."
        )

    # --- Split into sections by finding all section header positions ---
    sections: dict[str, str] = {}
    matches = list(_SECTION_PATTERN.finditer(raw))
    for i, m in enumerate(matches):
        key = m.group(1).upper().strip()
        # Content starts after the header; ends at the next header (or end of string)
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[key] = raw[content_start:content_end].strip()

    # --- Validate ANALYSIS ---
    if "ANALYSIS" not in sections:
        return LLMError("Malformed AI response: missing ANALYSIS section.")
    analysis = sections["ANALYSIS"]
    if not analysis:
        return LLMError("Malformed AI response: ANALYSIS section is empty.")

    # --- Validate DISPUTE DRAFT ---
    if "DISPUTE DRAFT" not in sections:
        return LLMError("Malformed AI response: missing DISPUTE DRAFT section.")
    dispute_draft = sections["DISPUTE DRAFT"]
    if not dispute_draft:
        return LLMError("Malformed AI response: DISPUTE DRAFT section is empty.")

    return LLMResponse(
        verdict=verdict,  # type: ignore[arg-type]
        analysis=analysis,
        dispute_draft=dispute_draft,
    )


# ---------------------------------------------------------------------------
# LLMOrchestrator
# ---------------------------------------------------------------------------


class LLMOrchestrator:
    """
    Orchestrates the LLM audit call.

    Parameters
    ----------
    model_name:
        OpenAI model identifier (default: ``"gpt-4o"``).
    temperature:
        Sampling temperature (default: ``0.2`` for deterministic audit output).
    timeout:
        Request timeout in seconds (default: ``60``).
    api_key:
        OpenAI API key.  If *None*, read from the ``OPENAI_API_KEY``
        environment variable.
    base_url:
        OpenAI-compatible base URL. If *None*, read from the ``OPENAI_BASE_URL``
        environment variable. Falls back to OpenAI's default if neither is set.
    """

    def __init__(
        self,
        model_name: str = "gpt-3.5-turbo",
        temperature: float = 0.2,
        timeout: int = 60,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("LLMLITE_KEY", "")
        resolved_base_url = base_url or os.environ.get("LLMLITE_BASE_URL", None)
        self._llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            request_timeout=timeout,
            api_key=resolved_key,
            base_url=resolved_base_url,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_audit(
        self,
        adm_text: str,
        fare_rules_chunks: list[Chunk],
    ) -> LLMResponse | LLMError:
        """
        Build a structured prompt, call the LLM, and parse the response.

        Parameters
        ----------
        adm_text:
            Full extracted text of the ADM document.
        fare_rules_chunks:
            Relevant Fare Rules chunks retrieved from the vector store.

        Returns
        -------
        LLMResponse
            Parsed audit result on success.
        LLMError
            On LLM call failure, timeout, or malformed response.
        """
        prompt = self._build_prompt(adm_text, fare_rules_chunks)

        try:
            response = self._llm.invoke([HumanMessage(content=prompt)])
            raw_text: str = response.content  # type: ignore[assignment]
        except TimeoutError as exc:
            return LLMError(
                f"AI service timed out: {exc}"
            )
        except Exception as exc:
            return LLMError(
                f"AI service call failed: {exc}"
            )

        return _parse_llm_response(raw_text)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(adm_text: str, fare_rules_chunks: list[Chunk]) -> str:
        """
        Assemble the structured prompt.

        All chunk texts are included verbatim — no truncation.
        The airline_code is taken from the first chunk (all chunks share the
        same airline_code after the retriever's metadata filter).
        """
        airline_code = fare_rules_chunks[0].airline_code if fare_rules_chunks else "UNKNOWN"

        chunks_text = "\n\n---\n\n".join(
            f"[Chunk {i + 1}]\n{chunk.text}"
            for i, chunk in enumerate(fare_rules_chunks)
        )

        return _PROMPT_TEMPLATE.format(
            adm_text=adm_text,
            airline_code=airline_code,
            fare_rules_chunks=chunks_text,
        )
