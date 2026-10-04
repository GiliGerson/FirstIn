-- 002 — Multiple users.
-- * profiles: one row per Auth user (created automatically on sign-up), with approval status,
--   onboarding state, Telegram link and scoring quota.
-- * Jobs stay a shared catalog (collected once); each user's score and state live in user_jobs.
-- * applications / emails / search_settings get a user_id. Existing rows go to the owner.
-- * RLS: every user sees only their own rows; shared tables are readable by approved users only.
-- Safe to run more than once. Run in Supabase: SQL Editor → New query → paste → Run.

-- ============================================================
-- profiles
-- ============================================================
create table if not exists profiles (
  user_id                uuid primary key references auth.users(id) on delete cascade,
  display_name           text,
  field_of_study         text,
  education              text,
  study_year             smallint,
  languages              jsonb not null default '["Hebrew", "English"]'::jsonb,
  open_to                text,
  status                 text not null default 'pending' check (status in ('pending', 'approved', 'blocked')),
  is_owner               boolean not null default false,
  onboarding_done        boolean not null default false,
  approval_requested_at  timestamptz,
  telegram_chat_id       bigint unique,
  telegram_link_code     text unique,
  telegram_link_expires  timestamptz,
  gmail_enabled          boolean not null default false,
  scoring_model          text not null default 'claude-haiku-4-5',
  daily_score_quota      integer default 30,          -- null = unlimited
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
alter table profiles enable row level security;

drop trigger if exists profiles_updated_at on profiles;
create trigger profiles_updated_at before update on profiles
  for each row execute function set_updated_at();

-- A profile for every new Auth user
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (user_id) values (new.id) on conflict do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Existing users: the dashboard owner from migration 001 becomes the owner profile
insert into profiles (user_id, status, is_owner, onboarding_done, gmail_enabled, scoring_model, daily_score_quota)
select user_id, 'approved', true, true, true, 'claude-sonnet-5-5', null from dashboard_owners
on conflict (user_id) do update set status = 'approved', is_owner = true, onboarding_done = true,
  gmail_enabled = true, scoring_model = 'claude-sonnet-5-5', daily_score_quota = null;
insert into profiles (user_id) select id from auth.users on conflict do nothing;

-- ============================================================
-- Helpers used by RLS policies and defaults
-- ============================================================
create or replace function public.is_owner() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles where user_id = (select auth.uid()) and is_owner)
$$;

create or replace function public.is_approved() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles where user_id = (select auth.uid()) and status = 'approved')
$$;

-- Rows written by the worker without an explicit user belong to the owner
create or replace function public.default_user_id() returns uuid
language sql stable security definer set search_path = '' as $$
  select coalesce((select auth.uid()), (select user_id from public.profiles where is_owner limit 1))
$$;

revoke all on function public.is_owner(), public.is_approved(), public.default_user_id() from public, anon;
grant execute on function public.is_owner(), public.is_approved(), public.default_user_id() to authenticated, service_role;

-- One-time code for connecting Telegram (t.me/<bot>?start=<code>), valid 30 minutes
create or replace function public.create_telegram_link_code() returns text
language plpgsql security definer set search_path = '' as $$
declare code text := replace(gen_random_uuid()::text, '-', '');
begin
  update public.profiles
     set telegram_link_code = code, telegram_link_expires = now() + interval '30 minutes'
   where user_id = (select auth.uid());
  return code;
end $$;
revoke all on function public.create_telegram_link_code() from public, anon;
grant execute on function public.create_telegram_link_code() to authenticated;

-- ============================================================
-- user_jobs: each user's score and state for a shared job
-- ============================================================
create table if not exists user_jobs (
  user_id             uuid not null default public.default_user_id() references auth.users(id) on delete cascade,
  job_id              bigint not null references jobs(id) on delete cascade,
  match_score         smallint check (match_score between 0 and 100),
  match_reasons       jsonb not null default '[]'::jsonb,
  red_flags           jsonb not null default '[]'::jsonb,
  requirements        jsonb not null default '[]'::jsonb,
  role_category       text,
  user_state          user_state not null default 'new',
  not_relevant_reason text,
  notified_at         timestamptz,
  scored_at           timestamptz,
  created_at          timestamptz not null default now(),
  primary key (user_id, job_id)
);
create index if not exists user_jobs_user_score_idx on user_jobs (user_id, match_score desc);
alter table user_jobs enable row level security;

-- The owner's existing scores and states move from jobs into user_jobs
insert into user_jobs (user_id, job_id, match_score, match_reasons, red_flags, requirements, role_category,
                       user_state, not_relevant_reason, notified_at, scored_at, created_at)
select p.user_id, j.id, j.match_score, j.match_reasons, j.red_flags, j.requirements, j.role_category,
       j.user_state, j.not_relevant_reason, j.notified_at,
       case when j.match_score is not null then j.first_seen_at end, j.first_seen_at
  from jobs j cross join (select user_id from profiles where is_owner limit 1) p
on conflict do nothing;

-- ============================================================
-- user_id on per-user tables (existing rows → owner)
-- ============================================================
alter table applications add column if not exists user_id uuid references auth.users(id) on delete cascade;
alter table emails add column if not exists user_id uuid references auth.users(id) on delete cascade;
alter table search_settings add column if not exists user_id uuid references auth.users(id) on delete cascade;

update applications set user_id = (select user_id from profiles where is_owner limit 1) where user_id is null;
update emails set user_id = (select user_id from profiles where is_owner limit 1) where user_id is null;
update search_settings set user_id = (select user_id from profiles where is_owner limit 1) where user_id is null;

alter table applications alter column user_id set default public.default_user_id();
alter table emails alter column user_id set default public.default_user_id();
alter table search_settings alter column user_id set default public.default_user_id();
alter table applications alter column user_id set not null;
alter table emails alter column user_id set not null;
alter table search_settings alter column user_id set not null;
create index if not exists applications_user_idx on applications (user_id);

-- Presets and the single active preset are per user now
alter table search_settings drop constraint if exists search_settings_preset_name_key;
create unique index if not exists search_settings_user_preset_uq on search_settings (user_id, preset_name);
drop index if exists search_settings_one_active;
create unique index if not exists search_settings_one_active_per_user on search_settings (user_id) where is_active;

-- ============================================================
-- RLS policies (replace migration 001's owner-only policies)
-- ============================================================
do $$
declare t text;
begin
  foreach t in array array['companies', 'jobs', 'job_sources', 'applications', 'emails', 'events', 'runs',
                           'search_settings', 'search_settings_history', 'user_jobs', 'profiles'] loop
    execute format('drop policy if exists owner_all on public.%I', t);
    execute format('drop policy if exists own_rows on public.%I', t);
    execute format('drop policy if exists approved_read on public.%I', t);
    execute format('drop policy if exists owner_read on public.%I', t);
    execute format('drop policy if exists own_select on public.%I', t);
    execute format('drop policy if exists own_update on public.%I', t);
    execute format('revoke all on public.%I from anon', t);
  end loop;
end $$;

-- Shared catalog: readable by approved users, written only by the worker
create policy approved_read on companies for select to authenticated using ((select public.is_approved()));
create policy approved_read on jobs for select to authenticated using ((select public.is_approved()));
create policy approved_read on job_sources for select to authenticated using ((select public.is_approved()));
revoke insert, update, delete on companies, jobs, job_sources from authenticated;
grant select on companies, jobs, job_sources to authenticated;

-- Own rows
create policy own_select on profiles for select to authenticated using (user_id = (select auth.uid()));
create policy own_update on profiles for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
revoke all on profiles from authenticated;
grant select on profiles to authenticated;
grant update (display_name, field_of_study, education, study_year, languages, open_to, onboarding_done)
  on profiles to authenticated;   -- status, owner flag, quota and Telegram link are not self-editable

create policy own_select on user_jobs for select to authenticated using (user_id = (select auth.uid()));
create policy own_update on user_jobs for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
revoke all on user_jobs from authenticated;
grant select on user_jobs to authenticated;
grant update (user_state, not_relevant_reason) on user_jobs to authenticated;

create policy own_rows on applications for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy own_rows on emails for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy own_rows on search_settings for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
grant select, insert, update, delete on applications, emails, search_settings to authenticated;

create policy own_rows on events for all to authenticated
  using (exists (select 1 from applications a where a.id = application_id and a.user_id = (select auth.uid())))
  with check (exists (select 1 from applications a where a.id = application_id and a.user_id = (select auth.uid())));
create policy own_rows on search_settings_history for all to authenticated
  using (exists (select 1 from search_settings s where s.id = settings_id and s.user_id = (select auth.uid())))
  with check (exists (select 1 from search_settings s where s.id = settings_id and s.user_id = (select auth.uid())));
grant select, insert, update, delete on events, search_settings_history to authenticated;

-- System runs: owner only
create policy owner_read on runs for select to authenticated using ((select public.is_owner()));
revoke insert, update, delete on runs from authenticated;
grant select on runs to authenticated;

grant usage on all sequences in schema public to authenticated;
