"""
RateLimiter — per-user upload quota enforcement for ADM Copilot.

Responsibilities:
  - check_quota(user_email) → QuotaStatus
  - record_upload(user_email) → None

Environment variables:
  - MAX_UPLOADS_PER_DAY  integer 1–100 inclusive; defaults to 5 for absent /
                         non-integer / out-of-range values.
  - SUPABASE_URL         (or NEXT_PUBLIC_SUPABASE_URL as fallback)
  - SUPABASE_KEY         (or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY as fallback)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

from supabase import create_client, Client

from models import QuotaStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_UPLOADS = 5
_MIN_UPLOADS = 1
_MAX_UPLOADS = 100


def _get_supabase_client() -> Client:
    """Build a Supabase client from environment variables."""
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    key = (
        os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "")
    )
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials not configured. "
            "Set SUPABASE_URL and SUPABASE_KEY environment variables."
        )
    return create_client(url, key)


def _parse_max_uploads() -> int:
    """
    Read MAX_UPLOADS_PER_DAY from the environment.

    Returns an integer in [1, 100].  Falls back to 5 for any of:
      - variable absent
      - non-integer string
      - value outside [1, 100]
    """
    raw = os.getenv("MAX_UPLOADS_PER_DAY")
    if raw is None:
        return _DEFAULT_MAX_UPLOADS
    try:
        value = int(raw)
    except (ValueError, TypeError):
        return _DEFAULT_MAX_UPLOADS
    if value < _MIN_UPLOADS or value > _MAX_UPLOADS:
        return _DEFAULT_MAX_UPLOADS
    return value


class RateLimiter:
    """Enforces per-user upload quotas using the Supabase `user_uploads` table."""

    def __init__(self, supabase_client: Client | None = None) -> None:
        self._db: Client = supabase_client or _get_supabase_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_quota(self, user_email: str) -> QuotaStatus:
        """
        Return the current quota state for *user_email*.

        Counts rows in `user_uploads` where:
          user_email = $1 AND last_upload_date >= now() - interval '24 hours'

        Fields:
          allowed       — True when current_count < limit
          current_count — number of uploads in the rolling 24-hour window
          limit         — value of MAX_UPLOADS_PER_DAY (default 5)
          reset_at      — earliest upload in window + 24 h; None if no uploads
        """
        limit = _parse_max_uploads()

        window_start = (
            datetime.now(timezone.utc) - timedelta(hours=24)
        ).isoformat()

        # Count uploads in the rolling window
        count_response = (
            self._db.table("user_uploads")
            .select("id", count="exact")
            .eq("user_email", user_email)
            .gte("last_upload_date", window_start)
            .execute()
        )
        # Prefer the explicit count field; fall back to len(data) for test mocks
        _raw_count = count_response.count
        current_count = int(_raw_count) if _raw_count is not None else len(count_response.data or [])

        # Determine reset_at from the earliest upload in the window
        reset_at: datetime | None = None
        if current_count > 0:
            earliest_response = (
                self._db.table("user_uploads")
                .select("last_upload_date")
                .eq("user_email", user_email)
                .gte("last_upload_date", window_start)
                .order("last_upload_date", desc=False)
                .limit(1)
                .execute()
            )
            earliest_rows = earliest_response.data or []
            if earliest_rows:
                earliest_str = earliest_rows[0]["last_upload_date"]
                earliest_dt = datetime.fromisoformat(
                    earliest_str.replace("Z", "+00:00")
                )
                reset_at = earliest_dt + timedelta(hours=24)

        return QuotaStatus(
            allowed=current_count < limit,
            current_count=current_count,
            limit=limit,
            reset_at=reset_at,
        )

    def record_upload(self, user_email: str) -> None:
        """
        Insert a new row into `user_uploads` for *user_email*.

        The row records:
          user_email       — the authenticated user's email
          upload_count     — always 1 (each row represents one upload)
          last_upload_date — current UTC timestamp (set by the database default,
                             but we pass it explicitly for testability)
        """
        self._db.table("user_uploads").insert(
            {
                "user_email": user_email,
                "upload_count": 1,
                "last_upload_date": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
