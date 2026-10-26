import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { locationsApi, type LocationPatch } from "@/api/locations";
import { invalidatePlanningData } from "@/api/planningKeys";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getErrorMessage } from "@/utils/errors";

export const NetworkCard = () => {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({ queryKey: ["locations"], queryFn: locationsApi.list });
  const mutation = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: LocationPatch }) => locationsApi.update(id, patch),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["locations"] });
      await invalidatePlanningData(qc);
    },
  });
  const save = (id: string, patch: LocationPatch) => mutation.mutate({ id, patch });
  const warehouses = data?.locations.filter((l) => l.kind === "warehouse" && l.is_active) ?? [];
  const field = "rounded-lg border border-line bg-surface px-2 py-2 text-sm text-content focus:ring-2 focus:ring-primary";

  return <Card title="Network" description="Confirm your warehouse, branches, and delivery lead times for advisory allocations and transfers.">
    {isLoading && <p>Loading locations…</p>}
    {isError && <p role="alert">Locations could not be loaded. Try again.</p>}
    {mutation.isError && <p role="alert">{getErrorMessage(mutation.error, "Location could not be saved")}</p>}
    {data && <div className="space-y-4">
      {data.network.degraded && <p role="status" className="text-sm text-amber-700">
        Location split incomplete: {data.network.unassigned_share == null ? "Unknown" : Math.round(data.network.unassigned_share * 100)}% of sales have no location
      </p>}
      <div className="flex flex-wrap gap-2">
        {data.network.allocation_ready && <Badge variant="success">Allocation ready</Badge>}
        {data.network.transfers_ready && <Badge variant="success">Transfers ready</Badge>}
      </div>
      {data.network.missing.length > 0 && <ul className="space-y-1 text-sm text-content-muted list-disc pl-5">
        {data.network.missing.map((message) => <li key={message}>{message}</li>)}
      </ul>}
      {data.locations.length === 0 ? <p>No locations yet. Import sales or stock with a location (store/branch) column.</p> :
        <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead><tr>{["Name", "Kind", "Supplied by", "Lead time (days)", "Active"].map((heading) =>
            <th key={heading} className="p-2 text-content-subtle font-medium">{heading}</th>)}</tr></thead>
          <tbody>{data.locations.map((loc) => <tr key={loc.id} className="border-t border-line">
            <td className="p-2 font-medium">{loc.name}</td>
            <td className="p-2"><select aria-label={`Kind for ${loc.name}`} className={field}
              value={loc.kind} disabled={mutation.isPending}
              onChange={(e) => save(loc.id, { kind: e.target.value as LocationPatch["kind"] })}>
              <option value="unconfirmed">Unconfirmed</option><option value="warehouse">Warehouse</option><option value="store">Store</option>
            </select></td>
            <td className="p-2"><select aria-label={`Supplied by for ${loc.name}`} className={field}
              value={loc.parent_location_id ?? ""} disabled={loc.kind !== "store" || mutation.isPending}
              onChange={(e) => save(loc.id, { parent_location_id: e.target.value || null })}>
              <option value="">Choose warehouse</option>
              {warehouses.filter((w) => w.id !== loc.id).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select></td>
            <td className="p-2"><input key={`${loc.id}-${loc.lead_time_days_from_parent}`} type="number" min={0} max={365}
              aria-label={`Lead time for ${loc.name}`} className={`${field} w-24`}
              defaultValue={loc.lead_time_days_from_parent ?? ""} disabled={loc.kind !== "store" || mutation.isPending}
              onBlur={(e) => {
                if (!e.target.validity.valid) return;
                const value = e.target.value === "" ? null : Number(e.target.value);
                if (value !== loc.lead_time_days_from_parent) save(loc.id, { lead_time_days_from_parent: value });
              }} /></td>
            <td className="p-2"><input type="checkbox" aria-label={`Active for ${loc.name}`}
              checked={loc.is_active} disabled={mutation.isPending}
              onChange={(e) => save(loc.id, { is_active: e.target.checked })} /></td>
          </tr>)}</tbody>
        </table></div>}
    </div>}
  </Card>;
};
