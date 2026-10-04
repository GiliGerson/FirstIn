-- 001 — Dashboard access (stage 2).
-- The dashboard signs in with Supabase Auth and uses the publishable key, so every table
-- needs RLS policies. Only users listed in dashboard_owners get access; everyone else
-- (including anyone who somehow signs up) sees nothing.
-- Safe to run more than once. Run in Supabase: SQL Editor → New query → paste → Run.

create table if not exists dashboard_owners (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table dashboard_owners enable row level security;

-- security definer: reads dashboard_owners regardless of its own RLS
create or replace function public.is_owner() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.dashboard_owners where user_id = (select auth.uid()))
$$;
revoke all on function public.is_owner() from public, anon;
grant execute on function public.is_owner() to authenticated;

do $$
declare t text;
begin
  foreach t in array array['companies', 'jobs', 'job_sources', 'applications', 'emails', 'events',
                           'runs', 'search_settings', 'search_settings_history'] loop
    execute format('drop policy if exists owner_all on public.%I', t);
    execute format('create policy owner_all on public.%I for all to authenticated '
                   'using ((select public.is_owner())) with check ((select public.is_owner()))', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end $$;

drop policy if exists owner_self on dashboard_owners;
create policy owner_self on dashboard_owners for select to authenticated using (user_id = (select auth.uid()));
grant select on dashboard_owners to authenticated;

-- Identity columns need their sequences for inserts from the dashboard
grant usage on all sequences in schema public to authenticated;
