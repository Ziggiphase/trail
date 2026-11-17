-- Trail database setup for Supabase.
-- Run once: Supabase dashboard → SQL Editor → New query → paste all of this → Run.
-- Safe to run again (it only creates what's missing and replaces the functions).

-- One row per user, computer, day and app. Seconds are added up across syncs.
create table if not exists public.activity (
    user_id    uuid        not null default auth.uid() references auth.users (id) on delete cascade,
    device     text        not null check (char_length(device) between 1 and 100),
    day        date        not null,
    app        text        not null check (char_length(app) between 1 and 200),
    seconds    integer     not null default 0 check (seconds between 0 and 86400),
    updated_at timestamptz not null default now(),
    primary key (user_id, device, day, app)
);

-- Row Level Security: every signed-in user can only ever see and change their own rows.
alter table public.activity enable row level security;

drop policy if exists "own rows: read"   on public.activity;
drop policy if exists "own rows: add"    on public.activity;
drop policy if exists "own rows: change" on public.activity;
drop policy if exists "own rows: delete" on public.activity;
create policy "own rows: read"   on public.activity for select to authenticated using ((select auth.uid()) = user_id);
create policy "own rows: add"    on public.activity for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "own rows: change" on public.activity for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "own rows: delete" on public.activity for delete to authenticated using ((select auth.uid()) = user_id);

revoke all on public.activity from anon;
grant select, insert, update, delete on public.activity to authenticated;

-- Add time from the app. rows = [{"device": "...", "day": "2026-11-17", "app": "code", "seconds": 300}, ...]
-- Runs with the caller's permissions, so the security rules above still apply.
create or replace function public.add_activity(rows jsonb)
returns void
language sql
security invoker
set search_path = ''
as $$
    insert into public.activity as a (user_id, device, day, app, seconds)
    select auth.uid(),
           left(r ->> 'device', 100),
           (r ->> 'day')::date,
           left(r ->> 'app', 200),
           least(greatest((r ->> 'seconds')::integer, 0), 86400)
    from jsonb_array_elements(rows) as r
    on conflict (user_id, device, day, app)
    do update set seconds    = least(a.seconds + excluded.seconds, 86400),
                  updated_at = now();
$$;

-- Totals per day and app (all of the user's computers combined) since a date.
create or replace function public.daily_totals(since date)
returns table (day date, app text, seconds bigint)
language sql
stable
security invoker
set search_path = ''
as $$
    select a.day, a.app, sum(a.seconds)::bigint
    from public.activity as a
    where a.user_id = auth.uid() and a.day >= since
    group by a.day, a.app
    order by a.day, a.app;
$$;

-- "Delete all my data" button in Settings.
create or replace function public.delete_my_data()
returns void
language sql
security invoker
set search_path = ''
as $$
    delete from public.activity where user_id = auth.uid();
$$;

revoke execute on function public.add_activity(jsonb)  from public, anon;
revoke execute on function public.daily_totals(date)   from public, anon;
revoke execute on function public.delete_my_data()     from public, anon;
grant  execute on function public.add_activity(jsonb)  to authenticated;
grant  execute on function public.daily_totals(date)   to authenticated;
grant  execute on function public.delete_my_data()     to authenticated;
