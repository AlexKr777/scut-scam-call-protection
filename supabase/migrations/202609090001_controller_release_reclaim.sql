-- Controller release/reclaim lifecycle.  The singleton settings row is the
-- serialization point: a valid PIN claim may only win while it is unlocked
-- and active_controller_id is NULL.

create or replace function public.release_controller()
returns table(state text, had_controller boolean)
language plpgsql
security definer
set search_path = public
as $$
declare previous_id uuid;
begin
  select active_controller_id into previous_id from system_settings where id = true for update;
  if previous_id is not null then
    update devices set role = 'RECEIVER', updated_at = now()
      where id = previous_id and revoked_at is null;
    update controller_commands set state = 'REJECTED', rejection_reason = 'CONTROLLER_RELEASED'
      where controller_id = previous_id and state in ('PENDING', 'LEASED');
  end if;
  update system_settings set active_controller_id = null, hardware_controls_enabled = false, updated_at = now()
    where id = true;
  return query select 'NO_CONTROLLER'::text, (previous_id is not null);
end;
$$;

create or replace function public.claim_unassigned_controller(p_device_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare current_id uuid;
begin
  select active_controller_id into current_id from system_settings where id = true for update;
  if current_id is not null then return false; end if;
  if not exists (select 1 from devices where id = p_device_id and role = 'RECEIVER' and enabled and revoked_at is null) then
    raise exception 'eligible receiver device not found';
  end if;
  update devices set role = 'CONTROLLER', updated_at = now() where id = p_device_id;
  update system_settings set active_controller_id = p_device_id, updated_at = now() where id = true;
  return true;
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
    select command.id from controller_commands command
      join system_settings settings on settings.id = true and settings.active_controller_id = command.controller_id
      join devices controller on controller.id = command.controller_id
    where (command.state = 'PENDING' or (command.state = 'LEASED' and command.lease_expires_at < now()))
      and command.expires_at > now() and controller.role = 'CONTROLLER'
      and controller.enabled and controller.revoked_at is null
    order by command.received_at for update of command skip locked
    limit greatest(1, least(p_limit, 64))
  ), leased as (
    update controller_commands command set state = 'LEASED', lease_expires_at = now() + interval '15 seconds'
      from candidates where command.id = candidates.id returning command.*
  ) select * from leased;
end;
$$;

revoke all on function public.release_controller() from public, anon, authenticated;
revoke all on function public.claim_unassigned_controller(uuid) from public, anon, authenticated;
grant execute on function public.release_controller() to service_role;
grant execute on function public.claim_unassigned_controller(uuid) to service_role;
