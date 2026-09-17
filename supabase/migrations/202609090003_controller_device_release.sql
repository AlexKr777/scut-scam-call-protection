create or replace function public.release_controller(p_expected_controller_id uuid)
returns table(state text, released boolean)
language plpgsql security definer set search_path = public
as $$
declare previous_id uuid;
begin
  select active_controller_id into previous_id from system_settings where id = true for update;
  if previous_id is distinct from p_expected_controller_id then
    return query select case when previous_id is null then 'NO_CONTROLLER' else 'CONTROLLER_ASSIGNED' end, false;
    return;
  end if;
  update devices set role = 'RECEIVER', updated_at = now() where id = previous_id and revoked_at is null;
  update controller_commands command set state = 'REJECTED', rejection_reason = 'CONTROLLER_RELEASED'
    where command.controller_id = previous_id and command.state in ('PENDING', 'LEASED');
  update system_settings set active_controller_id = null, hardware_controls_enabled = false, updated_at = now() where id = true;
  return query select 'NO_CONTROLLER'::text, true;
end;
$$;
revoke all on function public.release_controller(uuid) from public, anon, authenticated;
grant execute on function public.release_controller(uuid) to service_role;
