import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { aiApi } from "@/api/ai";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuthStore } from "@/stores/auth";

export function ImportFormats() {
  const scope = useAuthStore((s) => `${s.tenantId}:${s.userId}`);
  const [pending, setPending] = useState<{ id: string; revision: number } | null>(null);
  const client = useQueryClient();
  const list = useQuery({ queryKey: ["import-formats", scope], queryFn: aiApi.importFormats });
  const change = useMutation({ mutationFn: (args: { id: string; revision: number; disabled: boolean | null }) => aiApi.manageFormat(args.id, args.revision, args.disabled),
    onSuccess: () => { setPending(null); void client.invalidateQueries({ queryKey: ["import-formats"] }); } });
  return <div className="space-y-2 text-sm">
    <h3 className="font-medium">Saved import formats</h3>
    <p className="text-xs text-content-subtle">Showing up to 1,000 formats. Disabling keeps the configuration; deleting requires review again on the next import.</p>
    {list.isPending && <p role="status">Loading formats…</p>}
    {(list.isError || change.isError) && <p role="alert">Saved formats could not be updated. Refresh and retry.</p>}
    {list.data?.length === 0 && <p>No confirmed formats saved.</p>}
    {list.data?.map((format) => <div key={format.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
      <span>{format.kind} · {format.fingerprint.slice(0, 10)} · revision {format.revision}</span>
      <Button size="sm" variant="ghost" disabled={change.isPending} onClick={() => change.mutate({ id: format.id, revision: format.revision, disabled: !format.disabled })}>{format.disabled ? "Enable format" : "Disable format"}</Button>
      <Button size="sm" variant="ghost" disabled={change.isPending} onClick={() => setPending({ id: format.id, revision: format.revision })}>Delete format</Button>
    </div>)}
    <ConfirmDialog open={!!pending} onClose={() => setPending(null)} title="Delete this saved format?" message="Future imports of this format will require mapping review again. Imported data is kept." confirmLabel="Delete saved format" onConfirm={() => pending && change.mutate({ ...pending, disabled: null })} loading={change.isPending} />
  </div>;
}
