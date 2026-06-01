-- Migration: 002_create_user_uploads
-- Description: Creates the user_uploads table for rate-limit tracking.
--              Records each successfully processed ADM upload per user.
--              Rate-limit query: count rows where last_upload_date >= now() - interval '24 hours'.
-- Requirements: 2.4

CREATE TABLE IF NOT EXISTS user_uploads (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email       TEXT NOT NULL REFERENCES users(email),
    upload_count     INTEGER NOT NULL DEFAULT 1,
    last_upload_date TIMESTAMPTZ NOT NULL DEFAULT now()
);
