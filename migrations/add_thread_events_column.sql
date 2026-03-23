-- Add events column to threads table for thread activity tracking
-- Run this once on your Supabase project before deploying the thread tracking feature.

alter table threads add column if not exists events jsonb default '[]'::jsonb;
