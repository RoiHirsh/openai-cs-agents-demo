-- ============================================================
-- Migration: brokers, country_groups, bots reference tables
-- Run this in the Supabase SQL editor.
-- ============================================================

-- ── brokers ──────────────────────────────────────────────────

create table if not exists brokers (
  id           uuid        primary key default gen_random_uuid(),
  broker_id    text        not null unique,   -- canonical slug (bybit, vantage, pu_prime)
  display_name text        not null,
  aliases      text[]      not null default '{}',  -- lowercase alternatives for agent normalization
  active       boolean     not null default true,
  created_at   timestamptz not null default now()
);

-- ── country_groups ───────────────────────────────────────────

create table if not exists country_groups (
  id         uuid        primary key default gen_random_uuid(),
  name       text        not null unique,   -- canonical name (AUSTRALIA, CANADA, UK, OTHER)
  aliases    text[]      not null default '{}',  -- lowercase alternatives for agent normalization
  active     boolean     not null default true,
  created_at timestamptz not null default now()
);

-- ── bots ─────────────────────────────────────────────────────

create table if not exists bots (
  id         uuid        primary key default gen_random_uuid(),
  name       text        not null unique,
  active     boolean     not null default true,
  created_at timestamptz not null default now()
);

-- ── Seed brokers ─────────────────────────────────────────────

insert into brokers (broker_id, display_name, aliases) values
('bybit',    'Bybit',    ARRAY['bybit', 'by bit']),
('vantage',  'Vantage',  ARRAY['vantage']),
('pu_prime', 'PU Prime', ARRAY['pu prime', 'pu_prime', 'puprime', 'pu-prime']);

-- ── Seed country_groups ──────────────────────────────────────

insert into country_groups (name, aliases) values
('AUSTRALIA', ARRAY['australia', 'au', 'aus']),
('CANADA',    ARRAY['canada', 'ca', 'can']),
('UK',        ARRAY['united kingdom', 'uk', 'gb', 'gbr', 'great britain', 'england', 'scotland', 'wales']),
('OTHER',     ARRAY[]::text[]);

-- ── Seed bots ────────────────────────────────────────────────

insert into bots (name) values
('Gold'),
('Silver'),
('Crypto'),
('Forex'),
('Futures in crypto');
