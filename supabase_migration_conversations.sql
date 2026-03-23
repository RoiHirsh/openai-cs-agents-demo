-- Migration: Conversations tab + correction history
-- Run this once in the Supabase SQL editor.

-- 1. Add reset_at to threads so resets archive instead of delete conversations
ALTER TABLE threads
  ADD COLUMN IF NOT EXISTS reset_at timestamptz;

-- 2. Corrections table for flagging wrong AI messages and praising good ones
CREATE TABLE IF NOT EXISTS corrections (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id         text        NOT NULL,
  message_index     int         NOT NULL,
  original_message  text        NOT NULL,
  corrected_message text,                          -- NULL for praise entries
  note              text,
  feedback_type     text        NOT NULL DEFAULT 'correction',  -- 'correction' | 'praise'
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (thread_id, message_index)
);
