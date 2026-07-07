import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Mail, Trash2, UserPlus, Users } from "lucide-react";
import { forwardRef, useImperativeHandle, useState, type FormEvent } from "react";
import toast from "react-hot-toast";

import { invitesApi } from "@/api/onboarding";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import type { InviteRole } from "@/types/api";
import type { StepHandle, StepProps } from "./types";

const ROLES: { value: InviteRole; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "analyst", label: "Analyst" },
  { value: "viewer", label: "Viewer" },
];

export const StepTeam = forwardRef<StepHandle, StepProps>(function StepTeam(
  { nextStep, thisStep, save },
  ref,
) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>("analyst");

  const { data } = useQuery({ queryKey: ["invites"], queryFn: invitesApi.list });

  const create = useMutation({
    mutationFn: () => invitesApi.create(email.trim(), role),
    onSuccess: (inv) => {
      setEmail("");
      qc.invalidateQueries({ queryKey: ["invites"] });
      const url = `${window.location.origin}${inv.invite_url}`;
      navigator.clipboard?.writeText(url).catch(() => {});
      toast.success("Invite created — link copied to clipboard");
    },
  });

  const revoke = useMutation({
    mutationFn: (id: string) => invitesApi.revoke(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
  });

  useImperativeHandle(ref, () => ({
    submit: async () => {
      await save({
        mark_step: thisStep,
        current_step: nextStep,
        step_meta: { invited: data?.invites.length ?? 0 },
      });
      return true;
    },
  }));

  const seatsFull = !!data && data.seats_used >= data.seats_total;

  const onAdd = (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    create.mutate();
  };

  return (
    <div className="space-y-5">
      <form onSubmit={onAdd} className="flex flex-col gap-2.5 sm:flex-row">
        <div className="relative flex-1">
          <Mail
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-subtle"
            aria-hidden="true"
          />
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teammate@company.com"
            aria-label="Invitee email"
            className="input pl-9"
            disabled={seatsFull}
          />
        </div>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as InviteRole)}
          aria-label="Role"
          className="input sm:w-36"
          disabled={seatsFull}
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
        <Button
          type="submit"
          icon={<UserPlus size={15} aria-hidden="true" />}
          loading={create.isPending}
          disabled={!email.trim() || seatsFull}
        >
          Invite
        </Button>
      </form>

      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-content-muted">
          <Users size={14} aria-hidden="true" />
          <span className="font-mono">
            {data ? `${data.seats_used} / ${data.seats_total}` : "—"}
          </span>{" "}
          seats used
        </span>
        {seatsFull && (
          <span className="text-xs text-amber-600">Seat limit reached</span>
        )}
      </div>

      {data && data.invites.length > 0 ? (
        <ul className="divide-y divide-line rounded-2xl border border-line bg-surface">
          {data.invites.map((inv) => (
            <li key={inv.id} className="flex items-center gap-3 px-4 py-3">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-surface-3 text-xs font-semibold uppercase text-content-muted">
                {inv.email.slice(0, 2)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-content">{inv.email}</div>
                <div className="font-mono text-[11px] capitalize text-content-subtle">
                  {inv.role} · pending
                </div>
              </div>
              <button
                type="button"
                onClick={() => revoke.mutate(inv.id)}
                aria-label={`Revoke invite for ${inv.email}`}
                className="rounded-lg p-1.5 text-content-subtle tactile-press hover:bg-surface-3 hover:text-rose-600"
              >
                <Trash2 size={15} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          variant="subtle"
          icon={<Link2 size={20} aria-hidden="true" />}
          title="No invites yet"
          description="Invite teammates now or do it later from Settings. You can keep going either way."
        />
      )}
    </div>
  );
});
