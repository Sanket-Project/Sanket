import { useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { Lock, User } from "@/components/ui/icons";
import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LogoMark } from "@/components/ui/Logo";
import { useAuthStore } from "@/stores/auth";
import { getErrorMessage } from "@/utils/errors";

/**
 * Redeem a workspace invitation.
 *
 * The invite link has always pointed here; nothing ever served the page, so
 * every invitation an owner sent was a dead end.
 *
 * There is deliberately no industry control and no role control. Both come from
 * the invite record on the server — a member inherits the workspace's industry,
 * which is the whole point of scoping a workspace to one.
 */
export const AcceptInvitePage = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = useMemo(() => params.get("token") ?? "", [params]);
  const isAuth = useAuthStore((s) => s.isAuthenticated);

  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isAuth) return <Navigate to="/workspace" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const session = await authApi.acceptInvite({ token, name, password });
      // Redemption creates the account; it does not sign anyone in. Marking the
      // store authenticated with a null bearer would get them past
      // ProtectedRoute and then 401 every request the shell makes, ending in a
      // forced sign-out. Send them to sign in with the workspace prefilled.
      toast.success("You're in — sign in to open your workspace.");
      navigate("/login", {
        replace: true,
        state: { email: session.email, tenantSlug: session.tenant_slug },
      });
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "This invitation is no longer valid. Ask an admin to send a new one.",
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-6 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <LogoMark size={36} variant="tile" className="rounded-xl" />
          <span className="font-heading text-lg font-bold tracking-tight text-content">
            SANKET
          </span>
        </div>

        {!token ? (
          <div className="space-y-2">
            <h1 className="font-heading text-2xl font-bold tracking-tight text-content">
              Invitation link incomplete
            </h1>
            <p className="text-sm text-content-subtle">
              This link is missing its token. Ask whoever invited you to send it
              again.
            </p>
            <Link to="/login" className="text-sm font-medium text-accent underline underline-offset-2">
              Go to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" aria-label="Accept invitation">
            <div>
              <h1 className="font-heading text-2xl font-bold tracking-tight text-content">
                Join your team
              </h1>
              <p className="mt-1 text-sm text-content-subtle">
                Set a password to finish joining the workspace you were invited
                to. Your industry and role are already set by your admin.
              </p>
            </div>

            <Input
              id="invite-name"
              name="invite-name"
              label="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              icon={<User size={15} aria-hidden="true" />}
              placeholder="Jane Smith"
              required
              autoComplete="name"
            />
            <Input
              id="invite-password"
              name="invite-password"
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              icon={<Lock size={15} aria-hidden="true" />}
              placeholder="Min. 8 characters"
              required
              autoComplete="new-password"
            />
            <Input
              id="invite-confirm-password"
              name="invite-confirm-password"
              label="Confirm password"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              icon={<Lock size={15} aria-hidden="true" />}
              required
              autoComplete="new-password"
              error={error ?? undefined}
            />

            <Button type="submit" loading={loading} className="w-full">
              Join workspace
            </Button>
          </form>
        )}
      </div>
    </main>
  );
};
