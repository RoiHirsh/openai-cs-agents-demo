-- Dedupe table for backend Telegram team notifications (one row per Chatwoot conversation + event type).
-- Run once on your Supabase project before deploying.

create table if not exists team_notification_events (
  id uuid primary key default gen_random_uuid(),
  conversation_id text not null,
  event_type text not null,
  sent_at timestamptz not null default now(),
  unique (conversation_id, event_type)
);

create index if not exists idx_team_notification_events_conversation
  on team_notification_events (conversation_id);
