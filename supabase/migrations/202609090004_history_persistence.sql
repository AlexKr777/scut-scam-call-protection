-- Cross-device conversation history built on the existing authoritative
-- call_sessions, transcript_segments and incidents records. Raw audio remains
-- local and is intentionally absent from this schema.

alter table public.call_sessions
  add column if not exists protected_receiver_id uuid references public.devices(id),
  add column if not exists deleted_at timestamptz;

alter table public.transcript_segments
  add column if not exists sequence bigint;

with ranked as (
  select id, row_number() over (partition by session_id order by ended_at, created_at, id) - 1 as sequence
  from public.transcript_segments
  where sequence is null
)
update public.transcript_segments segment
set sequence = ranked.sequence
from ranked
where segment.id = ranked.id;

alter table public.transcript_segments alter column sequence set not null;

create unique index if not exists transcript_segments_session_sequence
  on public.transcript_segments (session_id, sequence);

create index if not exists call_sessions_history_idx
  on public.call_sessions (started_at desc, id)
  where deleted_at is null;

create or replace view public.conversation_history
with (security_invoker = true)
as
select
  session.id,
  session.protected_receiver_id,
  receiver.display_name as protected_receiver_name,
  session.started_at,
  session.ended_at,
  session.state as lifecycle_status,
  greatest(0, extract(epoch from (coalesce(session.ended_at, now()) - session.started_at)))::bigint as duration_seconds,
  left(coalesce(transcript.preview, ''), 240) as preview,
  case
    when latest_incident.state in ('PENDING_FORCE', 'PENDING_AUTO', 'CONFIRMED') then 'incident'
    when latest_incident.state in ('USER_DISMISSED', 'CLEARED') then 'cleared'
    when latest_incident.id is not null then 'suspicious'
    else 'normal'
  end as attention_state,
  latest_incident.id as incident_id,
  latest_incident.state as incident_state,
  session.created_at,
  session.updated_at
from public.call_sessions session
left join public.devices receiver on receiver.id = session.protected_receiver_id
left join lateral (
  select string_agg(segment.text, ' ' order by segment.sequence) as preview
  from public.transcript_segments segment
  where segment.session_id = session.id
) transcript on true
left join lateral (
  select incident.id, incident.state
  from public.incidents incident
  where incident.session_id = session.id
  order by incident.updated_at desc, incident.id
  limit 1
) latest_incident on true
where session.deleted_at is null;

create or replace view public.alert_history
with (security_invoker = true)
as
select
  incident.id,
  incident.session_id as conversation_id,
  incident.state,
  incident.source,
  incident.created_at,
  incident.updated_at,
  (session.deleted_at is not null) as conversation_deleted,
  case when session.deleted_at is null then left(coalesce(transcript.preview, ''), 180) else '' end as conversation_preview
from public.incidents incident
join public.call_sessions session on session.id = incident.session_id
left join lateral (
  select string_agg(segment.text, ' ' order by segment.sequence) as preview
  from public.transcript_segments segment
  where segment.session_id = session.id
) transcript on true;

create or replace function public.delete_conversation_history(p_session_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare changed_count integer;
begin
  update call_sessions
  set deleted_at = now(), updated_at = now()
  where id = p_session_id and deleted_at is null;
  get diagnostics changed_count = row_count;
  if changed_count = 0 then return false; end if;

  delete from transcript_segments where session_id = p_session_id;
  update incident_evidence evidence
  set payload = jsonb_build_object('redacted', true)
  from incidents incident
  where evidence.incident_id = incident.id and incident.session_id = p_session_id;
  return true;
end;
$$;

-- Receiver selection is authorized by the active Controller credential at the
-- Edge boundary. Requiring the master PIN again would force a secret into the
-- ordinary product UI and is not an additional authorization factor.
create or replace function public.configure_system(
  p_controller_id uuid,
  p_receiver_id uuid,
  p_hardware_controls_enabled boolean
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not exists (
    select 1 from devices controller
    join system_settings settings on settings.id = true and settings.active_controller_id = controller.id
    where controller.id = p_controller_id and controller.role = 'CONTROLLER'
      and controller.enabled and controller.revoked_at is null
  ) then
    raise exception 'active controller device not found';
  end if;
  if not exists (
    select 1 from devices
    where id = p_receiver_id and role = 'RECEIVER' and enabled and revoked_at is null
  ) then
    raise exception 'active receiver device not found';
  end if;
  update system_settings
  set active_receiver_id = p_receiver_id,
      hardware_controls_enabled = p_hardware_controls_enabled,
      updated_at = now()
  where id = true;
end;
$$;

revoke all on public.conversation_history, public.alert_history from public, anon, authenticated;
revoke all on function public.delete_conversation_history(uuid) from public, anon, authenticated;
grant select on public.conversation_history, public.alert_history to service_role;
grant execute on function public.delete_conversation_history(uuid) to service_role;
