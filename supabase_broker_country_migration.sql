-- ============================================================
-- Migration: broker_assets + country_offers tables
-- Run this in the Supabase SQL editor.
-- ============================================================

-- ── broker_assets ────────────────────────────────────────────

create table if not exists broker_assets (
  id          uuid        primary key default gen_random_uuid(),
  broker      text        not null,
  purpose     text        not null,
  asset_type  text        not null check (asset_type in ('link', 'video')),
  title       text        not null,
  url         text        not null,
  sort_order  int         not null default 0,
  active      boolean     not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ── country_offers ───────────────────────────────────────────

create table if not exists country_offers (
  id            uuid        primary key default gen_random_uuid(),
  country_group text        not null,
  broker_name   text        not null,
  bots          text[]      not null default '{}',
  broker_notes  text[]      not null default '{}',
  group_notes   text[]      not null default '{}',
  sort_order    int         not null default 0,
  active        boolean     not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- ── Seed broker_assets ───────────────────────────────────────

insert into broker_assets (broker, purpose, asset_type, title, url, sort_order) values

-- bybit — registration
('bybit', 'registration', 'link',  'Bybit link for sign up',       'https://bybit.com/en/invite?ref=BYQLKL', 0),
('bybit', 'registration', 'video', 'video to sign up',             'https://www.youtube.com/shorts/_xABSqSZZsg', 0),

-- bybit — copy_trade_connect
('bybit', 'copy_trade_connect', 'link',  'Link for Copy Trade',          'https://i.bybit.com/Jabvb8i?action=inviteToCopy', 0),
('bybit', 'copy_trade_connect', 'video', 'video how to copy in bybit',   'https://drive.google.com/file/d/1IHl8aaQyNfDSLqmzNJuJxODBLX2-WyCj/view?usp=drive_link', 0),

-- vantage — registration
('vantage', 'registration', 'link',  'Vantage sign up link',                  'https://www.vantagemarkets.com/forex-trading/forex-trading-account/?affid=7361340', 0),
('vantage', 'registration', 'video', 'video How to sign up in vantage',        'https://drive.google.com/file/d/1kr0JYMPYrfO7BFvpWxghoel4ULmfm2d5/view?usp=sharing', 0),

-- vantage — copy_trade_connect
('vantage', 'copy_trade_connect', 'link',  'link to copy crypto in vantage',  'https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-820189', 0),
('vantage', 'copy_trade_connect', 'link',  'link to copy gold in vantage',    'https://vantageapp.onelink.me/qaPD?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7361340%7Cplatform-copytrading&deep_link_sub1=spid-828839', 1),
('vantage', 'copy_trade_connect', 'video', 'video how to copy in vantage',    'https://drive.google.com/file/d/11upZwKRE_eYaqjenyr41RTYPyuf58CBR/view?usp=sharing', 0),

-- pu_prime — registration
('pu_prime', 'registration', 'link',  'PU Prime sign up link',              'https://www.puprime.partners/forex-trading-account/?affid=7525953', 0),
('pu_prime', 'registration', 'video', 'video how to sign up',               'https://drive.google.com/file/d/1Ej39VG4uJSWC_xnkSyyGJN_XCzPM2pvO/view?usp=sharing', 0),

-- pu_prime — copy_trade_open_account
('pu_prime', 'copy_trade_open_account', 'video', 'video how open a copy trading account', 'https://drive.google.com/file/d/10UHdv8K59Lw6U-GutEI6f1TvJkIRplSR/view?usp=sharing', 0),

-- pu_prime — copy_trade_connect
('pu_prime', 'copy_trade_connect', 'link',  'PU Prime Silver register',     'https://puprime.onelink.me/O5Jx?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7525953%7Cplatform-copytrading&deep_link_sub1=spid-825967&campaignCode=1pHJLS6RBENRLbA7/b+Ayg==', 0),
('pu_prime', 'copy_trade_connect', 'link',  'Pu Prime Gold register',       'https://puprime.onelink.me/O5Jx?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7525953%7Cplatform-copytrading&deep_link_sub1=spid-825948&campaignCode=1pHJLS6RBENRLbA7/b+Ayg==', 1),
('pu_prime', 'copy_trade_connect', 'link',  'Pu Prime forex register',      'https://puprime.onelink.me/O5Jx?af_xp=referral&pid=IBSHARE&deep_link_value=mt4id-7525953%7Cplatform-copytrading&deep_link_sub1=spid-878524&campaignCode=1pHJLS6RBENRLbA7/b+Ayg==', 2),
('pu_prime', 'copy_trade_connect', 'video', 'video how to connect to copy trading', 'https://drive.google.com/file/d/1o6yJMZ9_1wLS-A_mTN9Mzh_w3gJh6yCA/view?usp=sharing', 0);

-- ── Seed country_offers ──────────────────────────────────────

insert into country_offers (country_group, broker_name, bots, broker_notes, group_notes, sort_order) values

('AUSTRALIA', 'ByBit',    ARRAY['Futures in crypto'],            ARRAY[]::text[], ARRAY[]::text[], 0),
('CANADA',    'PU Prime', ARRAY['Gold', 'Silver', 'Forex'],      ARRAY['Gold/Silver only in cents; $500–$10,000 USD only'], ARRAY['PU Prime investment in Gold/Silver is only in cents and within $500–$10,000.'], 0),
('UK',        'Vantage',  ARRAY['Crypto', 'Gold'],               ARRAY[]::text[], ARRAY['PU Prime investment in Gold/Silver is only in cents and within $500–$10,000.'], 0),
('UK',        'PU Prime', ARRAY['Gold', 'Silver', 'Forex'],      ARRAY['Gold/Silver only in cents; $500–$10,000 USD only'], ARRAY['PU Prime investment in Gold/Silver is only in cents and within $500–$10,000.'], 1),
('OTHER',     'Vantage',  ARRAY['Crypto', 'Gold'],               ARRAY[]::text[], ARRAY['PU Prime investment in Gold/Silver is only in cents and within $500–$10,000.'], 0),
('OTHER',     'PU Prime', ARRAY['Gold', 'Silver', 'Forex'],      ARRAY['Gold/Silver only in cents; $500–$10,000 USD only'], ARRAY['PU Prime investment in Gold/Silver is only in cents and within $500–$10,000.'], 1),
('OTHER',     'ByBit',    ARRAY['Futures in crypto'],            ARRAY[]::text[], ARRAY['PU Prime investment in Gold/Silver is only in cents and within $500–$10,000.'], 2);
