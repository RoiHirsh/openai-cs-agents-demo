-- ============================================================
-- Migration: add bot column to broker_assets
-- Run this in the Supabase SQL editor.
-- ============================================================

alter table broker_assets
  add column if not exists bot text;

-- Existing rows keep bot = NULL (meaning: applies to all bots).
-- Set bot on rows that are specific to a particular bot, e.g.:
--   update broker_assets set bot = 'Crypto' where broker = 'vantage' and purpose = 'copy_trade_connect' and title ilike '%crypto%';
