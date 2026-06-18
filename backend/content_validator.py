"""
ContentValidator — validates that extracted PDF content is relevant to
Fare Rules or ADM documents before proceeding with ingestion or audit.

This prevents users from uploading irrelevant documents (e.g. FAQ pages,
marketing materials, etc.) and provides a clear warning message.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ContentValidationError(Exception):
    """Raised when extracted PDF content does not match expected document type."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ContentValidator:
    """
    Validates that extracted PDF text contains relevant keywords for either
    Fare Rules or ADM (Agency Debit Memo) documents.

    Uses keyword-based matching with a minimum threshold. This is intentionally
    lightweight and fast — no LLM call is needed for this gate check.
    """

    # ------------------------------------------------------------------
    # Fare Rules keywords — terms commonly found in airline fare rule docs
    # ------------------------------------------------------------------
    FARE_RULES_KEYWORDS: list[str] = [
        "fare rule",
        "tariff",
        "rule",
        "fare basis",
        "booking class",
        "cabin",
        "cancellation",
        "change fee",
        "penalty",
        "no-show",
        "no show",
        "reissue",
        "refund",
        "endorsement",
        "endorse",
        "commission",
        "service fee",
        "surcharge",
        "tax",
        "baggage allowance",
        "eligibility",
        "travel restriction",
        "minimum stay",
        "maximum stay",
        "advance purchase",
        "blackout date",
        "seasonality",
        "stopover",
        "routing",
    ]

    # ------------------------------------------------------------------
    # ADM keywords — terms commonly found in Agency Debit Memo documents
    # ------------------------------------------------------------------
    ADM_KEYWORDS: list[str] = [
        "adm",
        "agency debit memo",
        "debit memo",
        "debit note",
        "bsp",
        "arc",
        "ticket number",
        "invoice",
        "debit",
        "commission deduction",
        "penalty",
        "agency debit",
        "memo number",
        "debit amount",
        "ticket stock",
        "airline",
        "agency",
        "debit",
        "audit",
        "billing",
        "transaction",
        "reporting period",
        "sales report",
    ]

    # Minimum number of keyword matches to consider the content valid
    MIN_KEYWORD_MATCHES = 3

    # ------------------------------------------------------------------
    # Validation methods
    # ------------------------------------------------------------------

    @classmethod
    def is_fare_rules_document(cls, text: str) -> bool:
        """
        Check whether *text* appears to be a Fare Rules document.

        Returns ``True`` if at least ``MIN_KEYWORD_MATCHES`` keywords from the
        Fare Rules list are found (case-insensitive).
        """
        if not text or not text.strip():
            return False

        text_lower = text.lower()
        matches = sum(1 for kw in cls.FARE_RULES_KEYWORDS if kw in text_lower)
        result = matches >= cls.MIN_KEYWORD_MATCHES

        logger.debug(
            "ContentValidator.is_fare_rules_document: %d keyword matches (threshold=%d) → %s",
            matches,
            cls.MIN_KEYWORD_MATCHES,
            "PASS" if result else "FAIL",
        )
        return result

    @classmethod
    def is_adm_document(cls, text: str) -> bool:
        """
        Check whether *text* appears to be an ADM (Agency Debit Memo) document.

        Returns ``True`` if at least ``MIN_KEYWORD_MATCHES`` keywords from the
        ADM list are found (case-insensitive).
        """
        if not text or not text.strip():
            return False

        text_lower = text.lower()
        matches = sum(1 for kw in cls.ADM_KEYWORDS if kw in text_lower)
        result = matches >= cls.MIN_KEYWORD_MATCHES

        logger.debug(
            "ContentValidator.is_adm_document: %d keyword matches (threshold=%d) → %s",
            matches,
            cls.MIN_KEYWORD_MATCHES,
            "PASS" if result else "FAIL",
        )
        return result