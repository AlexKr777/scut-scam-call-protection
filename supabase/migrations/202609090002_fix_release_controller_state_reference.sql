-- Qualify controller_commands.state because the table-return output column of
-- release_controller is also named state.
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
    update controller_commands command set state = 'REJECTED', rejection_reason = 'CONTROLLER_RELEASED'
      where command.controller_id = previous_id and command.state in ('PENDING', 'LEASED');
  end if;
  update system_settings set active_controller_id = null, hardware_controls_enabled = false, updated_at = now()
    where id = true;
  return query select 'NO_CONTROLLER'::text, (previous_id is not null);
end;
$$;
