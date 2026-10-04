-- FirstIn — Supabase / Postgres schema (PRD section 10)
-- Safe to run more than once: types are created only if missing, tables use IF NOT EXISTS.
-- Run in Supabase: SQL Editor → New query → paste this file → Run.

-- ============================================================
-- Enum types
-- ============================================================
do $$ begin create type company_kind as enum ('startup', 'enterprise');
exception when duplicate_object then null; end $$;

do $$ begin create type company_priority as enum ('favorite', 'normal', 'blocked');
exception when duplicate_object then null; end $$;

do $$ begin create type discovered_via as enum ('seed', 'job', 'vc_board', 'ats_search', 'manual');
exception when duplicate_object then null; end $$;

do $$ begin create type scan_tier as enum ('hourly', 'every_3h', 'daily');
exception when duplicate_object then null; end $$;

do $$ begin create type ats_status as enum ('ok', 'unsupported', 'failing');
exception when duplicate_object then null; end $$;

do $$ begin create type job_type as enum ('student', 'part_time', 'internship', 'other');
exception when duplicate_object then null; end $$;

do $$ begin create type job_status as enum ('open', 'closed');
exception when duplicate_object then null; end $$;

do $$ begin create type user_state as enum ('new', 'saved', 'not_relevant', 'applied');
exception when duplicate_object then null; end $$;

do $$ begin create type job_source as enum (
  'greenhouse', 'lever', 'ashby', 'comeet', 'workday', 'smartrecruiters',
  'linkedin', 'gmail', 'drushim', 'alljobs', 'jobmaster', 'other');
exception when duplicate_object then null; end $$;

do $$ begin create type application_stage as enum (
  'applied', 'screening', 'interview', 'home_assignment', 'offer', 'rejected', 'ghosted', 'withdrawn');
exception when duplicate_object then null; end $$;

do $$ begin create type email_category as enum ('job_alert', 'recruiter_outreach', 'application_update', 'other');
exception when duplicate_object then null; end $$;

do $$ begin create type settings_change_source as enum ('dashboard', 'telegram', 'suggestion');
exception when duplicate_object then null; end $$;

-- ============================================================
-- Tables
-- ============================================================
create table if not exists companies (
  id                  bigint generated always as identity primary key,
  name                text not null,
  website             text,
  careers_url         text,
  ats_type            text,                 -- greenhouse / lever / ashby / comeet / ... / unknown
  ats_token           text,
  kind                company_kind,
  priority            company_priority not null default 'normal',
  discovered_via      discovered_via not null default 'seed',
  scan_tier           scan_tier not null default 'daily',
  ats_status          ats_status not null default 'ok',
  last_student_job_at timestamptz,
  created_at          timestamptz not null default now()
);
create unique index if not exists companies_name_uq on companies (lower(name));
create unique index if not exists companies_ats_uq on companies (ats_type, ats_token) where ats_token is not null;

create table if not exists jobs (
  id                  bigint generated always as identity primary key,
  company_id          bigint references companies(id) on delete cascade,
  title               text not null,
  title_normalized    text not null,
  description         text,
  url                 text,
  canonical_url       text,
  location            text,
  is_hybrid           boolean,
  is_remote           boolean,
  job_type            job_type,
  role_category       text,
  posted_at           timestamptz,
  first_seen_at       timestamptz not null default now(),
  last_seen_at        timestamptz not null default now(),
  status              job_status not null default 'open',
  match_score         smallint check (match_score between 0 and 100),
  match_reasons       jsonb not null default '[]'::jsonb,
  red_flags           jsonb not null default '[]'::jsonb,
  requirements        jsonb not null default '[]'::jsonb,
  user_state          user_state not null default 'new',
  not_relevant_reason text,
  notified_at         timestamptz
);
-- De-dup keys (FR1): canonical URL, or company + normalized title + location
create unique index if not exists jobs_canonical_url_uq on jobs (canonical_url) where canonical_url is not null;
create unique index if not exists jobs_dedup_uq on jobs (company_id, title_normalized, coalesce(location, ''));
create index if not exists jobs_status_score_idx on jobs (status, match_score desc);
create index if not exists jobs_first_seen_idx on jobs (first_seen_at desc);

create table if not exists job_sources (
  job_id      bigint not null references jobs(id) on delete cascade,
  source      job_source not null,
  source_url  text not null default '',
  seen_at     timestamptz not null default now(),
  primary key (job_id, source, source_url)
);

create table if not exists applications (
  id               bigint generated always as identity primary key,
  job_id           bigint references jobs(id) on delete set null,
  applied_at       timestamptz not null default now(),
  stage            application_stage not null default 'applied',
  cv_version_path  text,
  cover_note       text,
  contact_name     text,
  contact_email    text,
  next_followup_at timestamptz,
  notes            text
);
create index if not exists applications_stage_idx on applications (stage);

create table if not exists emails (
  id                    bigint generated always as identity primary key,
  gmail_message_id      text not null unique,
  received_at           timestamptz,
  from_addr             text,
  subject               text,
  category              email_category not null default 'other',
  linked_job_id         bigint references jobs(id) on delete set null,
  linked_application_id bigint references applications(id) on delete set null,
  summary               text
);

create table if not exists events (
  id             bigint generated always as identity primary key,
  application_id bigint not null references applications(id) on delete cascade,
  type           text not null,
  occurred_at    timestamptz not null default now(),
  payload        jsonb not null default '{}'::jsonb
);

create table if not exists runs (
  id           bigint generated always as identity primary key,
  collector    text not null,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  items_found  integer not null default 0,
  errors       jsonb not null default '[]'::jsonb
);
create index if not exists runs_collector_idx on runs (collector, started_at desc);

create table if not exists search_settings (
  id                bigint generated always as identity primary key,
  preset_name       text not null unique,
  is_active         boolean not null default false,
  roles             jsonb not null default '[]'::jsonb,
  include_keywords  jsonb not null default '[]'::jsonb,
  exclude_keywords  jsonb not null default '[]'::jsonb,
  job_types         jsonb not null default '[]'::jsonb,
  locations         jsonb not null default '[]'::jsonb,
  accept_hybrid     boolean not null default true,
  accept_remote     boolean not null default true,
  max_days_per_week smallint not null default 3,
  instant_threshold smallint not null default 75,
  digest_threshold  smallint not null default 50,
  sources           jsonb not null default '{}'::jsonb,
  linkedin_queries  jsonb not null default '[]'::jsonb,
  quiet_hours       jsonb not null default '{"start": "23:00", "end": "08:00"}'::jsonb,
  paused_until      timestamptz,
  updated_at        timestamptz not null default now()
);
-- Only one active preset at a time
create unique index if not exists search_settings_one_active on search_settings (is_active) where is_active;

create table if not exists search_settings_history (
  id          bigint generated always as identity primary key,
  settings_id bigint not null references search_settings(id) on delete cascade,
  changed_at  timestamptz not null default now(),
  changed_via settings_change_source not null,
  diff        jsonb not null default '{}'::jsonb
);

-- ============================================================
-- updated_at trigger for search_settings
-- ============================================================
create or replace function set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists search_settings_updated_at on search_settings;
create trigger search_settings_updated_at
  before update on search_settings
  for each row execute function set_updated_at();

-- ============================================================
-- Row Level Security: on for every table, no policies yet.
-- The worker uses the secret key (bypasses RLS); the publishable key sees nothing.
-- Dashboard policies (Supabase Auth, single user) will be added in stage 2.
-- ============================================================
alter table companies               enable row level security;
alter table jobs                    enable row level security;
alter table job_sources             enable row level security;
alter table applications            enable row level security;
alter table emails                  enable row level security;
alter table events                  enable row level security;
alter table runs                    enable row level security;
alter table search_settings         enable row level security;
alter table search_settings_history enable row level security;
