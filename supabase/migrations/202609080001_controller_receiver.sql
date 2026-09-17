-- SCUT controller/receiver command plane.  Direct mobile/database access is
-- deliberately denied: Edge Functions authenticate device credentials and the
-- Windows EXE remains authoritative for sessions and incidents.

create extension if not exists pgcrypto;

create table public.devices (
  id uuid primary key default gen_random_uuid(),
  install_id text not null unique,
  display_name text not null check (char_length(display_name) between 1 and 96),
  role text not null check (role in ('CONTROLLER', 'RECEIVER')),
  credential_hash text not null,
  fcm_registration_token text,
  app_version text,
  enabled boolean not null default true,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  revoked_at timestamptz
);

create unique index devices_one_active_controller
  on public.devices (role)
  where role = 'CONTROLLER' and revoked_at is null;

create table public.system_settings (
  id boolean primary key default true check (id),
  active_controller_id uuid references public.devices(id),
  active_receiver_id uuid references public.devices(id),
  hardware_controls_enabled boolean not null default false,
  test_mode_enabled boolean not null default false,
  updated_at timestamptz not null default now()
);

insert into public.system_settings (id) values (true) on conflict (id) do nothing;

create table public.call_sessions (
  id uuid primary key,
  started_at timestamptz not null,
  ended_at timestamptz,
  decision_epoch integer not null default 0 check (decision_epoch >= 0),
  state text not null check (state in ('ACTIVE', 'ENDED')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.controller_commands (
  id uuid primary key default gen_random_uuid(),
  controller_id uuid not null references public.devices(id),
  session_id uuid references public.call_sessions(id),
  command_type text not null check (command_type in ('FORCE', 'VETO')),
  client_sequence bigint not null check (client_sequence >= 0),
  decision_epoch integer,
  state text not null default 'PENDING'
    check (state in ('PENDING', 'LEASED', 'APPLIED', 'REJECTED', 'EXPIRED')),
  received_at timestamptz not null default now(),
  expires_at timestamptz not null,
  applied_at timestamptz,
  lease_expires_at timestamptz,
  rejection_reason text,
  unique (controller_id, client_sequence)
);

create index controller_commands_pending_idx
  on public.controller_commands (state, received_at)
  where state = 'PENDING';

create table public.incidents (
  id uuid primary key,
  session_id uuid not null references public.call_sessions(id),
  state text not null check (state in (
    'PENDING_FORCE', 'PENDING_AUTO', 'CONFIRMED', 'USER_DISMISSED', 'CLEARED'
  )),
  decision_epoch integer not null check (decision_epoch >= 0),
  force_count integer not null default 0 check (force_count >= 0),
  source text not null check (source in ('FORCE', 'AUTO', 'MERGED')),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  notification_message_id text
);

create index incidents_session_idx on public.incidents (session_id, updated_at desc);

create table public.incident_evidence (
  id uuid primary key default gen_random_uuid(),
  client_event_id uuid not null unique,
  incident_id uuid not null references public.incidents(id) on delete cascade,
  evidence_type text not null check (evidence_type in ('TRANSCRIPT', 'DECISION', 'COMMAND')),
  occurred_at timestamptz not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create index incident_evidence_incident_idx on public.incident_evidence (incident_id, occurred_at);

create table public.transcript_segments (
  id uuid primary key default gen_random_uuid(),
  client_event_id uuid not null unique,
  session_id uuid not null references public.call_sessions(id) on delete cascade,
  text text not null check (char_length(text) between 1 and 6000),
  speaker text,
  started_at timestamptz,
  ended_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index transcript_segments_session_idx on public.transcript_segments (session_id, ended_at);

create table public.enrollment_attempts (
  key_hash text primary key,
  window_started_at timestamptz not null default now(),
  attempts integer not null default 1 check (attempts >= 0)
);

-- Reassignment is only reachable to a service-role Edge Function.  It keeps
-- controller ownership atomic and avoids a brief two-controller state.
create or replace function public.reassign_controller(p_device_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not exists (select 1 from devices where id = p_device_id and revoked_at is null and enabled) then
    raise exception 'eligible controller device not found';
  end if;
  update devices set role = 'RECEIVER', updated_at = now()
    where role = 'CONTROLLER' and revoked_at is null and id <> p_device_id;
  update devices set role = 'CONTROLLER', updated_at = now() where id = p_device_id;
  update system_settings set active_controller_id = p_device_id, updated_at = now() where id = true;
end;
$$;

revoke all on function public.reassign_controller(uuid) from public, anon, authenticated;
grant execute on function public.reassign_controller(uuid) to service_role;

create or replace function public.configure_system(p_controller_id uuid, p_receiver_id uuid, p_hardware_controls_enabled boolean)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not exists (select 1 from devices where id = p_controller_id and role = 'CONTROLLER' and enabled and revoked_at is null) then
    raise exception 'active controller device not found';
  end if;
  if not exists (select 1 from devices where id = p_receiver_id and role = 'RECEIVER' and enabled and revoked_at is null) then
    raise exception 'active receiver device not found';
  end if;
  update system_settings set active_controller_id = p_controller_id, active_receiver_id = p_receiver_id,
    hardware_controls_enabled = p_hardware_controls_enabled, updated_at = now() where id = true;
end;
$$;

revoke all on function public.configure_system(uuid, uuid, boolean) from public, anon, authenticated;
grant execute on function public.configure_system(uuid, uuid, boolean) to service_role;

-- Atomic database rate limiting and leasing prevent password/enrollment
-- brute-force and duplicate/replayed controller commands after reconnects.
create or replace function public.allow_enrollment(p_key_hash text, p_window_seconds integer, p_limit integer)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare allowed boolean;
begin
  insert into enrollment_attempts (key_hash) values (p_key_hash)
  on conflict (key_hash) do update set
    attempts = case when enrollment_attempts.window_started_at < now() - make_interval(secs => p_window_seconds)
      then 1 else enrollment_attempts.attempts + 1 end,
    window_started_at = case when enrollment_attempts.window_started_at < now() - make_interval(secs => p_window_seconds)
      then now() else enrollment_attempts.window_started_at end
  returning attempts <= p_limit into allowed;
  return allowed;
end;
$$;

create or replace function public.claim_controller_commands(p_limit integer default 16)
returns setof public.controller_commands
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidates as (
    select id from controller_commands
    where (state = 'PENDING' or (state = 'LEASED' and lease_expires_at < now()))
      and expires_at > now()
    order by received_at
    for update skip locked
    limit greatest(1, least(p_limit, 64))
  ), leased as (
    update controller_commands command set state = 'LEASED', lease_expires_at = now() + interval '15 seconds'
    from candidates where command.id = candidates.id
    returning command.*
  ) select * from leased;
end;
$$;

revoke all on function public.allow_enrollment(text, integer, integer) from public, anon, authenticated;
revoke all on function public.claim_controller_commands(integer) from public, anon, authenticated;
grant execute on function public.allow_enrollment(text, integer, integer) to service_role;
grant execute on function public.claim_controller_commands(integer) to service_role;

alter table public.devices enable row level security;
alter table public.system_settings enable row level security;
alter table public.call_sessions enable row level security;
alter table public.controller_commands enable row level security;
alter table public.incidents enable row level security;
alter table public.incident_evidence enable row level security;
alter table public.transcript_segments enable row level security;

revoke all on table public.devices, public.system_settings, public.call_sessions,
  public.controller_commands, public.incidents, public.incident_evidence,
  public.transcript_segments from anon, authenticated;

alter publication supabase_realtime add table public.controller_commands;
