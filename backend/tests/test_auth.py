"""
Unit tests for AuthService and POST /auth/login.

Tests cover:
  - login: valid credentials → JWT issued
  - login: invalid password → AuthError, failure recorded
  - login: unknown email → AuthError, failure recorded
  - login: locked account → LockoutError raised before DB password check
  - verify_jwt: valid token → UserClaims returned
  - verify_jwt: expired token → None
  - verify_jwt: tampered token → None
  - verify_jwt: garbage string → None
  - check_lockout: fewer than 5 failures → not locked
  - check_lockout: 5+ failures → locked, locked_until set
  - record_failed_attempt: inserts a row
  - POST /auth/login 200: returns access_token, token_type, expires_in
  - POST /auth/login 401: invalid credentials
  - POST /auth/login 429: account locked
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

from models import AuthError, LockoutError, LockoutStatus, UserClaims
from auth import AuthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JWT_SECRET = "test-secret-key-for-unit-tests"
_JWT_ALGORITHM = "HS256"


def _make_service(supabase_mock: MagicMock) -> AuthService:
    """Create an AuthService with a mocked Supabase client and fixed JWT secret."""
    with patch.dict("os.environ", {"JWT_SECRET": _JWT_SECRET, "JWT_ALGORITHM": _JWT_ALGORITHM}):
        return AuthService(supabase_client=supabase_mock)


def _make_query_chain(*, rows: list[dict], count: int | None) -> MagicMock:
    """
    Build a mock that supports arbitrary Supabase query chaining and returns
    the given data from .execute().

    Every named method (select, eq, gte, order, limit, insert, etc.) returns
    the same chain object, enabling patterns like:
        .table("x").select("col").eq("k", v).gte("t", ts).execute()
    """
    execute_result = MagicMock()
    execute_result.data = rows
    execute_result.count = count

    chain = MagicMock()

    # Set each chaining method's return_value to the chain itself AFTER creation
    for method in ("select", "eq", "neq", "gte", "lte", "gt", "lt",
                   "order", "limit", "insert", "update", "delete",
                   "upsert", "filter", "match", "contains", "ilike"):
        getattr(chain, method).return_value = chain

    chain.execute.return_value = execute_result
    # Calling the chain itself also returns the chain (handles .table() → chain())
    chain.return_value = chain
    return chain


def _build_supabase_mock(
    *,
    user_rows: list[dict] | None = None,
    lockout_count: int = 0,
    earliest_attempt_at: str | None = None,
) -> MagicMock:
    """
    Build a Supabase client mock that returns the given data for common queries.
    Dispatches by table name via table() side_effect.
    """
    mock = MagicMock()

    users_chain = _make_query_chain(rows=user_rows or [], count=None)
    lockout_count_chain = _make_query_chain(rows=[], count=lockout_count)
    earliest_chain = _make_query_chain(
        rows=[{"attempted_at": earliest_attempt_at}] if earliest_attempt_at else [],
        count=None,
    )
    insert_chain = _make_query_chain(rows=[], count=None)

    call_counts = {"login_attempts_select": 0}

    def table_side_effect(table_name: str):
        if table_name == "users":
            return users_chain
        if table_name == "login_attempts":
            call_counts["login_attempts_select"] += 1
            if call_counts["login_attempts_select"] == 1:
                return lockout_count_chain   # count query
            elif call_counts["login_attempts_select"] == 2:
                return earliest_chain        # earliest attempt query (when locked)
            else:
                return insert_chain          # insert failure record
        return MagicMock()

    mock.table.side_effect = table_side_effect
    return mock


def _make_bcrypt_hash(plain: str) -> str:
    """
    Hash a password using bcrypt directly so that AuthService.login can verify it.
    Uses bcrypt directly to avoid passlib's self-test incompatibility with bcrypt 4.x.
    """
    import bcrypt
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ---------------------------------------------------------------------------
# AuthService.verify_jwt
# ---------------------------------------------------------------------------

class TestVerifyJwt:
    def _service(self) -> AuthService:
        return _make_service(MagicMock())

    def test_valid_token_returns_claims(self):
        svc = self._service()
        from jose import jwt as jose_jwt
        now = int(time.time())
        token = jose_jwt.encode(
            {"sub": "user@example.com", "iat": now, "exp": now + 86400},
            _JWT_SECRET,
            algorithm=_JWT_ALGORITHM,
        )
        claims = svc.verify_jwt(token)
        assert claims is not None
        assert claims.sub == "user@example.com"
        assert claims.exp == now + 86400
        assert claims.iat == now

    def test_expired_token_returns_none(self):
        svc = self._service()
        from jose import jwt as jose_jwt
        now = int(time.time())
        token = jose_jwt.encode(
            {"sub": "user@example.com", "iat": now - 90000, "exp": now - 3600},
            _JWT_SECRET,
            algorithm=_JWT_ALGORITHM,
        )
        assert svc.verify_jwt(token) is None

    def test_tampered_token_returns_none(self):
        svc = self._service()
        from jose import jwt as jose_jwt
        now = int(time.time())
        token = jose_jwt.encode(
            {"sub": "user@example.com", "iat": now, "exp": now + 86400},
            _JWT_SECRET,
            algorithm=_JWT_ALGORITHM,
        )
        tampered = token[:-4] + "XXXX"
        assert svc.verify_jwt(tampered) is None

    def test_garbage_string_returns_none(self):
        svc = self._service()
        assert svc.verify_jwt("not.a.jwt") is None
        assert svc.verify_jwt("") is None
        assert svc.verify_jwt("garbage") is None


# ---------------------------------------------------------------------------
# AuthService.check_lockout
# ---------------------------------------------------------------------------

class TestCheckLockout:
    def test_no_failures_not_locked(self):
        mock = _build_supabase_mock(lockout_count=0)
        svc = _make_service(mock)
        status = svc.check_lockout("user@example.com")
        assert status.is_locked is False
        assert status.failed_attempts == 0
        assert status.locked_until is None

    def test_four_failures_not_locked(self):
        mock = _build_supabase_mock(lockout_count=4)
        svc = _make_service(mock)
        status = svc.check_lockout("user@example.com")
        assert status.is_locked is False
        assert status.failed_attempts == 4

    def test_five_failures_locked(self):
        earliest = "2025-01-01T12:00:00+00:00"
        mock = _build_supabase_mock(lockout_count=5, earliest_attempt_at=earliest)
        svc = _make_service(mock)
        status = svc.check_lockout("user@example.com")
        assert status.is_locked is True
        assert status.failed_attempts == 5
        assert status.locked_until is not None
        expected_locked_until = datetime(2025, 1, 1, 12, 15, 0, tzinfo=timezone.utc)
        assert status.locked_until == expected_locked_until

    def test_more_than_five_failures_locked(self):
        earliest = "2025-06-15T08:30:00+00:00"
        mock = _build_supabase_mock(lockout_count=10, earliest_attempt_at=earliest)
        svc = _make_service(mock)
        status = svc.check_lockout("user@example.com")
        assert status.is_locked is True
        assert status.failed_attempts == 10


# ---------------------------------------------------------------------------
# AuthService.record_failed_attempt
# ---------------------------------------------------------------------------

class TestRecordFailedAttempt:
    def test_inserts_row_with_success_false(self):
        mock = MagicMock()
        insert_result = MagicMock()
        insert_result.data = []
        table_mock = MagicMock()
        table_mock.insert.return_value.execute.return_value = insert_result
        mock.table.return_value = table_mock

        svc = _make_service(mock)
        svc.record_failed_attempt("user@example.com")

        mock.table.assert_called_with("login_attempts")
        table_mock.insert.assert_called_once_with(
            {"email": "user@example.com", "success": False}
        )


# ---------------------------------------------------------------------------
# AuthService.login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_valid_credentials_returns_jwt(self):
        hashed = _make_bcrypt_hash("correct-password")
        mock = _build_supabase_mock(
            user_rows=[{"email": "user@example.com", "password_hash": hashed}],
            lockout_count=0,
        )
        svc = _make_service(mock)
        token = svc.login("user@example.com", "correct-password")
        assert isinstance(token, str)
        claims = svc.verify_jwt(token)
        assert claims is not None
        assert claims.sub == "user@example.com"

    def test_jwt_expiry_is_24h(self):
        hashed = _make_bcrypt_hash("correct-password")
        mock = _build_supabase_mock(
            user_rows=[{"email": "user@example.com", "password_hash": hashed}],
            lockout_count=0,
        )
        svc = _make_service(mock)
        before = int(time.time())
        token = svc.login("user@example.com", "correct-password")
        after = int(time.time())

        claims = svc.verify_jwt(token)
        assert claims is not None
        assert claims.exp == claims.iat + 86400
        assert before <= claims.iat <= after

    def test_wrong_password_raises_auth_error(self):
        hashed = _make_bcrypt_hash("correct-password")
        mock = _build_supabase_mock(
            user_rows=[{"email": "user@example.com", "password_hash": hashed}],
            lockout_count=0,
        )
        svc = _make_service(mock)
        with pytest.raises(AuthError):
            svc.login("user@example.com", "wrong-password")

    def test_unknown_email_raises_auth_error(self):
        mock = _build_supabase_mock(user_rows=[], lockout_count=0)
        svc = _make_service(mock)
        with pytest.raises(AuthError):
            svc.login("nobody@example.com", "any-password")

    def test_locked_account_raises_lockout_error(self):
        earliest = "2025-01-01T12:00:00+00:00"
        mock = _build_supabase_mock(lockout_count=5, earliest_attempt_at=earliest)
        svc = _make_service(mock)
        with pytest.raises(LockoutError) as exc_info:
            svc.login("user@example.com", "any-password")
        assert exc_info.value.locked_until is not None

    def test_invalid_credentials_error_message_is_generic(self):
        """Error message must not hint at which field is wrong."""
        mock = _build_supabase_mock(user_rows=[], lockout_count=0)
        svc = _make_service(mock)
        with pytest.raises(AuthError) as exc_info:
            svc.login("nobody@example.com", "any-password")
        msg = exc_info.value.message.lower()
        assert "email" not in msg
        assert "password" not in msg


# ---------------------------------------------------------------------------
# POST /auth/login endpoint (integration via TestClient)
# ---------------------------------------------------------------------------

class TestLoginEndpoint:
    """
    Tests for POST /auth/login using the FastAPI test client.
    AuthService is mocked at the main module level to avoid real Supabase calls.
    """

    def _patch_auth_service(self, mock_service: MagicMock):
        """Patch the AuthService name in main's namespace."""
        return patch("main.AuthService", return_value=mock_service)

    @pytest.mark.asyncio
    async def test_success_returns_200_with_token(self, client):
        mock_svc = MagicMock()
        mock_svc.login.return_value = "fake.jwt.token"

        with self._patch_auth_service(mock_svc):
            response = await client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "correct-password"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "fake.jwt.token"
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 86400

    @pytest.mark.asyncio
    async def test_invalid_credentials_returns_401(self, client):
        mock_svc = MagicMock()
        mock_svc.login.side_effect = AuthError("Invalid credentials.")

        with self._patch_auth_service(mock_svc):
            response = await client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "wrong-password"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials."

    @pytest.mark.asyncio
    async def test_locked_account_returns_429(self, client):
        locked_until = datetime(2025, 1, 1, 12, 15, 0, tzinfo=timezone.utc)
        mock_svc = MagicMock()
        mock_svc.login.side_effect = LockoutError(locked_until)

        with self._patch_auth_service(mock_svc):
            response = await client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "any-password"},
            )

        assert response.status_code == 429
        detail = response.json()["detail"]
        assert "Account locked" in detail
        assert "2025-01-01T12:15:00Z" in detail

    @pytest.mark.asyncio
    async def test_short_password_returns_422(self, client):
        """Pydantic validation rejects passwords shorter than 8 characters."""
        response = await client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "short"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_email_returns_422(self, client):
        """Pydantic validation rejects malformed email addresses."""
        response = await client.post(
            "/auth/login",
            json={"email": "not-an-email", "password": "correct-password"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_401_detail_does_not_reveal_field(self, client):
        """Generic 401 message must not mention 'email' or 'password'."""
        mock_svc = MagicMock()
        mock_svc.login.side_effect = AuthError("Invalid credentials.")

        with self._patch_auth_service(mock_svc):
            response = await client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "wrong-password"},
            )

        detail = response.json()["detail"].lower()
        assert "email" not in detail
        assert "password" not in detail


# ---------------------------------------------------------------------------
# AuthService.register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self):
        mock = MagicMock()
        select_chain = _make_query_chain(rows=[], count=None)
        
        mock.table.return_value = select_chain

        svc = _make_service(mock)
        svc.register("My Travel Agency", "agent@mytravelagency.com", "validpassword123")

        # Ensure we check for duplicate email and duplicate domain
        mock.table.assert_called_with("users")
        select_chain.select.assert_any_call("email")
        select_chain.eq.assert_any_call("email", "agent@mytravelagency.com")
        select_chain.eq.assert_any_call("domain", "mytravelagency.com")

        # Verify insert includes domain
        from unittest.mock import ANY
        select_chain.insert.assert_called_once_with({
            "agent_travel_name": "My Travel Agency",
            "email": "agent@mytravelagency.com",
            "password_hash": ANY,
            "domain": "mytravelagency.com",
        })

    def test_register_duplicate_domain_fails(self):
        mock = MagicMock()
        
        # We need the first select query (duplicate email) to return empty
        # and the second select query (duplicate domain) to return a match.
        email_check_chain = _make_query_chain(rows=[], count=None)
        domain_check_chain = _make_query_chain(rows=[{"email": "other@mytravelagency.com"}], count=None)
        
        call_count = {"users_select": 0}
        def table_side_effect(table_name: str):
            if table_name == "users":
                call_count["users_select"] += 1
                if call_count["users_select"] == 1:
                    return email_check_chain
                else:
                    return domain_check_chain
            return MagicMock()

        mock.table.side_effect = table_side_effect

        svc = _make_service(mock)
        from models import RegistrationError
        with pytest.raises(RegistrationError) as exc_info:
            svc.register("My Travel Agency", "agent2@mytravelagency.com", "validpassword123")

        assert "company domain has already been registered" in str(exc_info.value)

    def test_register_dev_whitelist_bypasses_domain_check(self):
        mock = MagicMock()
        select_chain = _make_query_chain(rows=[], count=None)
        
        mock.table.return_value = select_chain

        svc = _make_service(mock)
        # coffee.logica@gmail.com is in dev whitelist
        svc.register("Dev Agent", "coffee.logica@gmail.com", "validpassword123")

        # Verify domain is stored as None/NULL for whitelisted accounts
        from unittest.mock import ANY
        select_chain.insert.assert_called_once_with({
            "agent_travel_name": "Dev Agent",
            "email": "coffee.logica@gmail.com",
            "password_hash": ANY,
            "domain": None,
        })

