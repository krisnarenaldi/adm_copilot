"""
Unit tests for RateLimiter.

Tests cover:
  - check_quota: under limit → allowed=True
  - check_quota: at limit → allowed=False, correct reset_at
  - check_quota: no prior uploads → allowed=True, reset_at=None
  - record_upload: inserts correct row
  - MAX_UPLOADS_PER_DAY parsing:
      valid int (e.g. 10) → 10
      missing env var     → 5
      non-integer string  → 5
      value 0             → 5
      value 101           → 5
      value 100           → 100
      value 1             → 1
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from rate_limiter import RateLimiter, _parse_max_uploads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query_chain(*, rows: list[dict], count: int | None) -> MagicMock:
    """
    Build a mock that supports arbitrary chaining and returns the given data
    from .execute().

    MagicMock already returns a new MagicMock for any attribute access, so we
    only need to wire up .execute() to return the desired result.  We do this
    by making every attribute access on the chain return the chain itself so
    that fluent calls like .select(...).eq(...).gte(...).execute() all resolve
    to the same object and ultimately call our wired .execute().
    """
    # Use a simple namespace for the execute result so .data and .count are
    # plain attributes, not intercepted by any mock __getattr__.
    class _Result:
        pass

    execute_result = _Result()
    execute_result.data = rows
    execute_result.count = count

    # Use a spec-free MagicMock and override __getattr__ via the class so that
    # any attribute lookup returns the chain itself, enabling arbitrary fluent
    # chaining without hitting the dunder-method restriction on instances.
    class _Chain(MagicMock):
        def __getattr__(self, name: str):  # type: ignore[override]
            if name in ("_mock_name", "_mock_new_parent", "_mock_new_name",
                        "_mock_children", "_mock_return_value", "_mock_called",
                        "_mock_call_args", "_mock_call_args_list",
                        "_mock_call_count", "_mock_mock_calls",
                        "_mock_unsafe", "_spec_class", "_spec_signature",
                        "_mock_methods", "_mock_wraps", "_mock_delegate",
                        "_mock_sealed", "method_calls", "mock_calls",
                        "called", "call_count", "call_args",
                        "call_args_list", "return_value", "side_effect"):
                return super().__getattr__(name)
            return self

        def __call__(self, *args, **kwargs):  # type: ignore[override]
            return self

    chain = _Chain()
    # Wire execute() to return our plain result object
    chain.execute = lambda: execute_result  # type: ignore[attr-defined]
    return chain


def _build_supabase_mock(
    *,
    upload_count: int = 0,
    earliest_upload_at: str | None = None,
) -> MagicMock:
    """
    Build a Supabase client mock for user_uploads queries.

    The mock handles:
      1st table("user_uploads") call → count query
      2nd table("user_uploads") call → earliest upload query (when count > 0)
      3rd table("user_uploads") call → insert (record_upload)
    """
    mock = MagicMock()

    count_chain = _make_query_chain(rows=[], count=upload_count)
    earliest_chain = _make_query_chain(
        rows=[{"last_upload_date": earliest_upload_at}] if earliest_upload_at else [],
        count=None,
    )
    insert_chain = _make_query_chain(rows=[], count=None)

    call_counts = {"user_uploads": 0}

    def table_side_effect(table_name: str):
        if table_name == "user_uploads":
            call_counts["user_uploads"] += 1
            n = call_counts["user_uploads"]
            if n == 1:
                return count_chain
            elif n == 2:
                return earliest_chain
            else:
                return insert_chain
        return MagicMock()

    mock.table.side_effect = table_side_effect
    return mock


def _make_limiter(supabase_mock: MagicMock) -> RateLimiter:
    return RateLimiter(supabase_client=supabase_mock)


# ---------------------------------------------------------------------------
# _parse_max_uploads — env var parsing
# ---------------------------------------------------------------------------


class TestParseMaxUploads:
    def test_valid_integer_10(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "10"}):
            assert _parse_max_uploads() == 10

    def test_missing_env_var_defaults_to_5(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "MAX_UPLOADS_PER_DAY"}
        with patch.dict("os.environ", env, clear=True):
            assert _parse_max_uploads() == 5

    def test_non_integer_string_defaults_to_5(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "abc"}):
            assert _parse_max_uploads() == 5

    def test_value_zero_defaults_to_5(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "0"}):
            assert _parse_max_uploads() == 5

    def test_value_101_defaults_to_5(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "101"}):
            assert _parse_max_uploads() == 5

    def test_value_100_is_valid(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "100"}):
            assert _parse_max_uploads() == 100

    def test_value_1_is_valid(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "1"}):
            assert _parse_max_uploads() == 1

    def test_negative_value_defaults_to_5(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "-1"}):
            assert _parse_max_uploads() == 5

    def test_float_string_defaults_to_5(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "3.5"}):
            assert _parse_max_uploads() == 5

    def test_empty_string_defaults_to_5(self):
        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": ""}):
            assert _parse_max_uploads() == 5


# ---------------------------------------------------------------------------
# RateLimiter.check_quota
# ---------------------------------------------------------------------------


class TestCheckQuota:
    def test_no_prior_uploads_allowed_true_reset_at_none(self):
        """User with no uploads in the window: allowed=True, reset_at=None."""
        mock = _build_supabase_mock(upload_count=0)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "5"}):
            status = limiter.check_quota("user@example.com")

        assert status.allowed is True
        assert status.current_count == 0
        assert status.limit == 5
        assert status.reset_at is None

    def test_under_limit_allowed_true(self):
        """User with 3 uploads against a limit of 5: allowed=True."""
        earliest = "2025-06-01T10:00:00+00:00"
        mock = _build_supabase_mock(upload_count=3, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "5"}):
            status = limiter.check_quota("user@example.com")

        assert status.allowed is True
        assert status.current_count == 3
        assert status.limit == 5

    def test_under_limit_reset_at_is_earliest_plus_24h(self):
        """reset_at must equal the earliest upload timestamp + 24 hours."""
        earliest = "2025-06-01T10:00:00+00:00"
        mock = _build_supabase_mock(upload_count=3, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "5"}):
            status = limiter.check_quota("user@example.com")

        expected_reset = datetime(2025, 6, 2, 10, 0, 0, tzinfo=timezone.utc)
        assert status.reset_at == expected_reset

    def test_at_limit_allowed_false(self):
        """User with 5 uploads against a limit of 5: allowed=False."""
        earliest = "2025-06-01T08:30:00+00:00"
        mock = _build_supabase_mock(upload_count=5, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "5"}):
            status = limiter.check_quota("user@example.com")

        assert status.allowed is False
        assert status.current_count == 5
        assert status.limit == 5

    def test_at_limit_reset_at_correct(self):
        """reset_at is earliest upload + 24h when at the limit."""
        earliest = "2025-06-01T08:30:00+00:00"
        mock = _build_supabase_mock(upload_count=5, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "5"}):
            status = limiter.check_quota("user@example.com")

        expected_reset = datetime(2025, 6, 2, 8, 30, 0, tzinfo=timezone.utc)
        assert status.reset_at == expected_reset

    def test_over_limit_allowed_false(self):
        """User with 7 uploads against a limit of 5: allowed=False."""
        earliest = "2025-06-01T09:00:00+00:00"
        mock = _build_supabase_mock(upload_count=7, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "5"}):
            status = limiter.check_quota("user@example.com")

        assert status.allowed is False
        assert status.current_count == 7

    def test_custom_limit_respected(self):
        """MAX_UPLOADS_PER_DAY=10: 9 uploads → allowed=True."""
        earliest = "2025-06-01T10:00:00+00:00"
        mock = _build_supabase_mock(upload_count=9, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "10"}):
            status = limiter.check_quota("user@example.com")

        assert status.allowed is True
        assert status.limit == 10

    def test_custom_limit_at_boundary(self):
        """MAX_UPLOADS_PER_DAY=10: 10 uploads → allowed=False."""
        earliest = "2025-06-01T10:00:00+00:00"
        mock = _build_supabase_mock(upload_count=10, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "10"}):
            status = limiter.check_quota("user@example.com")

        assert status.allowed is False
        assert status.limit == 10

    def test_invalid_env_var_falls_back_to_default_5(self):
        """Invalid MAX_UPLOADS_PER_DAY falls back to 5."""
        mock = _build_supabase_mock(upload_count=0)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "not-a-number"}):
            status = limiter.check_quota("user@example.com")

        assert status.limit == 5

    def test_reset_at_uses_z_suffix_timestamp(self):
        """Timestamps with 'Z' suffix are parsed correctly."""
        earliest = "2025-06-01T10:00:00Z"
        mock = _build_supabase_mock(upload_count=2, earliest_upload_at=earliest)
        limiter = _make_limiter(mock)

        with patch.dict("os.environ", {"MAX_UPLOADS_PER_DAY": "5"}):
            status = limiter.check_quota("user@example.com")

        expected_reset = datetime(2025, 6, 2, 10, 0, 0, tzinfo=timezone.utc)
        assert status.reset_at == expected_reset


# ---------------------------------------------------------------------------
# RateLimiter.record_upload
# ---------------------------------------------------------------------------


class TestRecordUpload:
    def test_inserts_row_with_correct_fields(self):
        """record_upload must insert a row with user_email and upload_count=1."""
        mock = MagicMock()
        insert_result = MagicMock()
        insert_result.data = []
        table_mock = MagicMock()
        table_mock.insert.return_value.execute.return_value = insert_result
        mock.table.return_value = table_mock

        limiter = _make_limiter(mock)
        limiter.record_upload("user@example.com")

        mock.table.assert_called_with("user_uploads")
        call_args = table_mock.insert.call_args[0][0]
        assert call_args["user_email"] == "user@example.com"
        assert call_args["upload_count"] == 1
        assert "last_upload_date" in call_args

    def test_insert_last_upload_date_is_utc_iso(self):
        """last_upload_date in the inserted row must be a valid UTC ISO string."""
        mock = MagicMock()
        insert_result = MagicMock()
        insert_result.data = []
        table_mock = MagicMock()
        table_mock.insert.return_value.execute.return_value = insert_result
        mock.table.return_value = table_mock

        limiter = _make_limiter(mock)
        limiter.record_upload("auditor@airline.com")

        call_args = table_mock.insert.call_args[0][0]
        # Should be parseable as a datetime
        dt = datetime.fromisoformat(call_args["last_upload_date"])
        assert dt.tzinfo is not None  # must be timezone-aware
