-- Migration: 005_add_domain_to_users
-- Description: Adds a nullable domain column to the users table with a UNIQUE constraint.
--              Existing users (excluding dev whitelist) will have their domain populated.

ALTER TABLE users ADD COLUMN IF NOT EXISTS domain TEXT;

-- Update domain for existing users except dev whitelist accounts
UPDATE users 
SET domain = split_part(email, '@', 2)
WHERE email NOT IN ('krisna.renaldi@gmail.com', 'coffee.logica@gmail.com');

-- Add unique constraint on the domain column
-- Postgres allows multiple NULL values in UNIQUE columns, which fits dev whitelist users.
ALTER TABLE users ADD CONSTRAINT users_domain_key UNIQUE (domain);
