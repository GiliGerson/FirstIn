-- 003 — Least-privilege hardening.
-- Supabase's default grants give anon/authenticated TRUNCATE, TRIGGER and REFERENCES on every
-- table. The app never uses them, and TRUNCATE is not subject to RLS — so remove them, also for
-- tables created later. The legacy dashboard_owners table (replaced by profiles.is_owner in 002)
-- keeps read access for its owner only.
-- Safe to run more than once.

revoke truncate, references, trigger on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke truncate, references, trigger on tables from anon, authenticated;

revoke all on dashboard_owners from anon;
revoke insert, update, delete, truncate, references, trigger on dashboard_owners from authenticated;
