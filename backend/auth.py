"""
AuthService — JWT-based authentication for ADM Copilot.

Responsibilities:
  - login(email, password) → JWT string | raises AuthError / LockoutError
  - verify_jwt(token) → UserClaims | None
  - check_lockout(email) → LockoutStatus
  - record_failed_attempt(email) → None

Environment variables required:
  - SUPABASE_URL          (or NEXT_PUBLIC_SUPABASE_URL as fallback)
  - SUPABASE_KEY          (or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY as fallback)
  - JWT_SECRET
  - JWT_ALGORITHM         (default: HS256)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta

from jose import JWTError, jwt
import bcrypt as _bcrypt_lib
from supabase import create_client, Client

from models import AuthError, LockoutError, LockoutStatus, UserClaims, RegistrationError

# ---------------------------------------------------------------------------
# Password hashing helpers (using bcrypt directly — passlib 1.7 is
# incompatible with bcrypt 4.x due to a self-test that exceeds the 72-byte
# password limit enforced by the newer library)
# ---------------------------------------------------------------------------

def _hash_password(plain: str) -> str:
    return _bcrypt_lib.hashpw(plain.encode(), _bcrypt_lib.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt_lib.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Free email provider blocklist and dev whitelist
# ---------------------------------------------------------------------------

# Domains that are blocked for registration (free / consumer email providers)
_FREE_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.id", "yahoo.fr", "yahoo.de",
    "yahoo.es", "yahoo.it", "yahoo.com.au", "yahoo.com.br", "yahoo.com.ar",
    "hotmail.com", "hotmail.co.uk", "hotmail.fr", "hotmail.de", "hotmail.it",
    "hotmail.es", "hotmail.com.br",
    "outlook.com", "outlook.co.uk", "outlook.fr", "outlook.de",
    "live.com", "live.co.uk", "live.fr",
    "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com",
    "protonmail.com", "proton.me",
    "mail.com", "email.com",
    "yandex.com", "yandex.ru",
    "zoho.com",
    "gmx.com", "gmx.net", "gmx.de",
    "web.de",
    "inbox.com",
    "fastmail.com", "fastmail.fm",
})

# Specific addresses allowed regardless of domain (development / testing accounts)
_DEV_WHITELIST: frozenset[str] = frozenset({
    "krisna.renaldi@gmail.com",
    "coffee.logica@gmail.com",
})


def _is_company_email(email: str) -> bool:
    """
    Return True if the email is allowed for registration.

    Rules (in order):
      1. Dev-whitelist addresses are always allowed.
      2. Addresses whose domain is in the free-provider blocklist are rejected.
      3. All other addresses are accepted (assumed to be company emails).
    """
    normalized = email.strip().lower()
    if normalized in _DEV_WHITELIST:
        return True
    domain = normalized.split("@")[-1]
    return domain not in _FREE_EMAIL_DOMAINS

# ---------------------------------------------------------------------------
# Lockout constants
# ---------------------------------------------------------------------------
_LOCKOUT_THRESHOLD = 5          # consecutive failures before lockout
_LOCKOUT_WINDOW_MINUTES = 15    # rolling window in minutes
_LOCKOUT_DURATION_MINUTES = 15  # how long the lockout lasts


def _get_supabase_client() -> Client:
    """Build a Supabase client from environment variables."""
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    key = (
        os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "")
    )
    print("KEY supabase =",key)
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials not configured. "
            "Set SUPABASE_URL and SUPABASE_KEY environment variables."
        )
    return create_client(url, key)


class AuthService:
    """Handles all authentication logic for ADM Copilot."""

    def __init__(self, supabase_client: Client | None = None) -> None:
        self._db: Client = supabase_client or _get_supabase_client()
        self._jwt_secret: str = os.getenv("JWT_SECRET", "")
        self._jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

        if not self._jwt_secret:
            raise RuntimeError(
                "JWT_SECRET environment variable is not set."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> str:
        """
        Authenticate a user and return a signed JWT string.

        Raises:
            LockoutError: if the account is currently locked.
            AuthError:    if credentials are invalid.
        """
        # 1. Check lockout before touching the password
        lockout = self.check_lockout(email)
        if lockout.is_locked:
            assert lockout.locked_until is not None  # invariant
            raise LockoutError(lockout.locked_until)

        # 2. Fetch user record from Supabase
        response = (
            self._db.table("users")
            .select("email, password_hash")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        rows = response.data or []

        # 3. Verify password — use constant-time comparison even on miss
        stored_hash = rows[0]["password_hash"] if rows else None
        password_ok = (
            _verify_password(password, stored_hash)
            if stored_hash
            else False
        )

        if not rows or not password_ok:
            # Record the failure and return a generic error
            self.record_failed_attempt(email)
            raise AuthError("Invalid credentials.")

        # 4. Issue JWT
        now = int(time.time())
        claims = {
            "sub": email,
            "iat": now,
            "exp": now + 86400,  # 24-hour expiry
        }
        token = jwt.encode(claims, self._jwt_secret, algorithm=self._jwt_algorithm)
        return token

    def verify_jwt(self, token: str) -> UserClaims | None:
        """
        Decode and validate a JWT.

        Returns:
            UserClaims if the token is valid and not expired.
            None if the token is invalid, expired, or malformed.
        """
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
            )
            return UserClaims(
                sub=payload["sub"],
                exp=payload["exp"],
                iat=payload["iat"],
            )
        except (JWTError, KeyError, ValueError):
            return None

    def check_lockout(self, email: str) -> LockoutStatus:
        """
        Count failed login attempts in the last 15 minutes.

        Returns:
            LockoutStatus with is_locked=True and locked_until set if the
            account is locked; is_locked=False otherwise.
        """
        window_start = (
            datetime.now(timezone.utc) - timedelta(minutes=_LOCKOUT_WINDOW_MINUTES)
        ).isoformat()

        response = (
            self._db.table("login_attempts")
            .select("attempted_at", count="exact")
            .eq("email", email)
            .eq("success", False)
            .gte("attempted_at", window_start)
            .execute()
        )
        failed_count = response.count or 0

        if failed_count >= _LOCKOUT_THRESHOLD:
            # Determine when the lockout expires: earliest failure + 15 min
            earliest_response = (
                self._db.table("login_attempts")
                .select("attempted_at")
                .eq("email", email)
                .eq("success", False)
                .gte("attempted_at", window_start)
                .order("attempted_at", desc=False)
                .limit(1)
                .execute()
            )
            earliest_rows = earliest_response.data or []
            if earliest_rows:
                earliest_str = earliest_rows[0]["attempted_at"]
                # Parse ISO timestamp (Supabase returns UTC with +00:00 or Z)
                earliest_dt = datetime.fromisoformat(
                    earliest_str.replace("Z", "+00:00")
                )
                locked_until = earliest_dt + timedelta(minutes=_LOCKOUT_DURATION_MINUTES)
            else:
                # Fallback: lock for 15 minutes from now
                locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=_LOCKOUT_DURATION_MINUTES
                )

            return LockoutStatus(
                is_locked=True,
                failed_attempts=failed_count,
                locked_until=locked_until,
            )

        return LockoutStatus(
            is_locked=False,
            failed_attempts=failed_count,
            locked_until=None,
        )

    def record_failed_attempt(self, email: str) -> None:
        """Insert a failed login attempt row into the login_attempts table."""
        self._db.table("login_attempts").insert(
            {
                "email": email,
                "success": False,
            }
        ).execute()

    def register(self, agent_travel_name: str, email: str, password: str) -> None:
        """
        Register a new user.

        Raises:
            RegistrationError: if the email domain is a free provider (and not
                               in the dev whitelist), if the email is already
                               registered, or if the domain is already registered.
        """
        # 1. Validate email domain
        if not _is_company_email(email):
            raise RegistrationError(
                "Registration requires a company email address. "
                "Free email providers (Gmail, Yahoo, Hotmail, etc.) are not accepted."
            )

        # 2. Check for duplicate email
        existing = (
            self._db.table("users")
            .select("email")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if existing.data:
            raise RegistrationError("An account with this email address already exists.")

        # 3. Extract domain and check for duplicate domain (excluding whitelisted dev emails)
        normalized_email = email.strip().lower()
        is_dev = normalized_email in _DEV_WHITELIST
        domain = None if is_dev else normalized_email.split("@")[-1]

        if domain:
            existing_domain = (
                self._db.table("users")
                .select("email")
                .eq("domain", domain)
                .limit(1)
                .execute()
            )
            if existing_domain.data:
                raise RegistrationError("An account with this company domain has already been registered.")

        # 4. Hash password and insert user
        password_hash = _hash_password(password)
        self._db.table("users").insert(
            {
                "agent_travel_name": agent_travel_name,
                "email": email,
                "password_hash": password_hash,
                "domain": domain,
            }
        ).execute()
