-- Migration: 001_create_users
-- Description: Creates the users table for authentication.
--              Stores agent travel name, email, and bcrypt password hash.
-- Requirements: 1.1, 1.6

CREATE TABLE IF NOT EXISTS users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_travel_name TEXT NOT NULL,
    email             TEXT UNIQUE NOT NULL,
    password_hash     TEXT NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT now()
);
