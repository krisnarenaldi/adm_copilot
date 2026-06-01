-- Migration: 004_create_airlines
-- Description: Creates the airlines table for the airline selector combobox.
--              Stores airline codes (e.g., "GA") and full names (e.g., "Garuda Indonesia").
--              Queried by GET /airlines to populate the frontend dropdown.
-- Requirements: 1.1

CREATE TABLE IF NOT EXISTS airlines (
    code       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
