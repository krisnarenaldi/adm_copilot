-- Migration: 003_create_login_attempts
-- Description: Creates the login_attempts table for account lockout tracking.
--              Lockout query: count rows where email = $1 AND success = false
--              AND attempted_at >= now() - interval '15 minutes'. If count >= 5, account is locked.
-- Requirements: 1.6

CREATE TABLE IF NOT EXISTS login_attempts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        TEXT NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    success      BOOLEAN NOT NULL DEFAULT false
);
