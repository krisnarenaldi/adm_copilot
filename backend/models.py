"""
Shared Pydantic data models and exception types for ADM Copilot.

These models are used across the backend services (AuthService, RateLimiter,
PDFExtractor, VectorRetriever, LLMOrchestrator) and the FastAPI route handlers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# JWT / Auth models
# ---------------------------------------------------------------------------


class UserClaims(BaseModel):
    """Decoded claims from a verified JWT."""

    sub: str  # user email
    exp: int  # Unix timestamp — token expiry
    iat: int  # Unix timestamp — token issued-at


class LoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class RegisterRequest(BaseModel):
    """Payload for POST /auth/register."""

    agent_travel_name: str
    email: EmailStr
    password: str

    @field_validator("agent_travel_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("agent_travel_name must not be empty.")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class RegisterResponse(BaseModel):
    """Successful response from POST /auth/register."""

    message: str = "Registration successful."
    email: str


class LoginResponse(BaseModel):
    """Successful response from POST /auth/login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # seconds


class LockoutStatus(BaseModel):
    """Result of a lockout check for a given email address."""

    is_locked: bool
    failed_attempts: int
    locked_until: datetime | None  # None when not locked


# ---------------------------------------------------------------------------
# Rate-limiting models
# ---------------------------------------------------------------------------


class QuotaStatus(BaseModel):
    """Current upload quota state for a user."""

    allowed: bool
    current_count: int
    limit: int
    reset_at: datetime | None  # earliest upload in window + 24 h; None when no uploads yet


# ---------------------------------------------------------------------------
# Vector store / retrieval models
# ---------------------------------------------------------------------------


class Chunk(BaseModel):
    """A single Fare Rules text chunk returned by the VectorRetriever."""

    text: str
    airline_code: str
    relevance_score: float


# ---------------------------------------------------------------------------
# LLM / audit models
# ---------------------------------------------------------------------------


class LLMResponse(BaseModel):
    """Parsed output from the LLMOrchestrator."""

    verdict: Literal["VALID DISPUTE FOUND", "VALID ADM / NO DISPUTE"]
    analysis: str       # markdown string
    dispute_draft: str  # plain-text email


class AuditResponse(BaseModel):
    """HTTP 200 response body for POST /audit."""

    verdict: Literal["VALID DISPUTE FOUND", "VALID ADM / NO DISPUTE"]
    analysis: str
    dispute_draft: str


# ---------------------------------------------------------------------------
# Airline models
# ---------------------------------------------------------------------------


class Airline(BaseModel):
    """A single airline entry returned by GET /airlines."""

    code: str
    name: str


# ---------------------------------------------------------------------------
# Fare-rules ingestion response
# ---------------------------------------------------------------------------


class IngestionResponse(BaseModel):
    """HTTP 200 response body for POST /fare-rules."""

    status: str = "success"
    message: str


# ---------------------------------------------------------------------------
# Application-level exceptions
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Raised when authentication fails (invalid credentials, expired token, etc.)."""

    def __init__(self, message: str = "Invalid credentials.") -> None:
        super().__init__(message)
        self.message = message


class RegistrationError(Exception):
    """Raised when registration fails (duplicate email, invalid domain, etc.)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LockoutError(Exception):
    """Raised when an account is locked due to too many failed login attempts."""

    def __init__(self, locked_until: datetime) -> None:
        super().__init__(f"Account locked until {locked_until.isoformat()}Z.")
        self.locked_until = locked_until


class ExtractionError(Exception):
    """Raised when PyMuPDF fails to extract text from a PDF."""

    def __init__(self, message: str = "Failed to extract text from the uploaded PDF.") -> None:
        super().__init__(message)
        self.message = message


class LLMError(Exception):
    """Raised when the LLM call fails, times out, or returns a malformed response."""

    def __init__(self, message: str = "The AI service is temporarily unavailable.") -> None:
        super().__init__(message)
        self.message = message


class ParseError(Exception):
    """Raised when the LLM response cannot be parsed into the three required components."""

    def __init__(self, message: str = "The AI response was malformed and could not be parsed.") -> None:
        super().__init__(message)
        self.message = message


class NoFareRulesError(Exception):
    """Raised when the VectorRetriever finds no chunks for the requested airline_code."""

    def __init__(self, airline_code: str) -> None:
        super().__init__(f"No Fare Rules are available for airline '{airline_code}'.")
        self.airline_code = airline_code
        self.message = str(self)


class QuotaExceededError(Exception):
    """Raised when a user has reached their upload quota for the current 24-hour window."""

    def __init__(self, reset_at: datetime) -> None:
        super().__init__(f"Upload quota exceeded. Quota resets at {reset_at.isoformat()}Z.")
        self.reset_at = reset_at
        self.message = str(self)
