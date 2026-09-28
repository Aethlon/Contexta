"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Loader2,
  LogOut,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import { probeTenantAction, setTenantAction, signOutAction } from "@/app/actions";
import type { OperatorIdentity } from "@/lib/dashboard-identity";

const SOURCE_LABEL: Record<OperatorIdentity["source"], string> = {
  session: "signed-in session",
  operator: "operator override (cookie)",
  env: "environment",
  discovered: "discovered from API key",
  none: "unresolved",
};

export function TenantSwitcher({ identity }: { identity: OperatorIdentity }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [probe, setProbe] = useState<{
    ok: boolean;
    resolvedOrgId: string | null;
    keyCount: number;
    error: string | null;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const runProbe = () => {
    startTransition(async () => {
      const result = await probeTenantAction();
      setProbe(result);
    });
  };

  const apply = (formData: FormData) => {
    setError(null);
    startTransition(async () => {
      const result = await setTenantAction(formData);
      if (result?.error) {
        setError(result.error);
        return;
      }
      setProbe(null);
      setOpen(false);
      router.refresh();
    });
  };

  const copyOrg = async () => {
    if (!identity.orgId) return;
    await navigator.clipboard.writeText(identity.orgId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="shrink-0 border-t border-border p-2">
      <div className="rounded-md border border-border px-2 py-1.5" style={{ background: "color-mix(in srgb, var(--muted) 25%, transparent)" }}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex w-full min-w-0 items-center gap-2 text-left cursor-pointer"
        >
          <Building2 className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[10px] uppercase tracking-wider text-muted-foreground">
              Organization
            </span>
            <span className="block truncate font-mono text-[11px] text-foreground">
              {identity.orgId ?? "UNRESOLVED"}
            </span>
          </span>
          {/* Down when collapsed (click to open), up when expanded (click to close). */}
          {open ? (
            <ChevronUp className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
          ) : (
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
          )}
        </button>
        <p className="mt-1 truncate text-[10px] text-muted-foreground">
          {SOURCE_LABEL[identity.source]}
        </p>
      </div>

      {open && (
        <div className="mt-2 space-y-3 rounded-md border border-border bg-muted p-2.5 text-[11px]">
          <div className="space-y-1">
            <p className="text-muted-foreground">Acting as organization</p>
            <div className="flex items-center gap-1.5">
              <code className="min-w-0 flex-1 truncate rounded bg-card px-1.5 py-1 font-mono text-[10px] text-foreground">
                {identity.orgId ?? "â€”"}
              </code>
              <button
                type="button"
                onClick={copyOrg}
                disabled={!identity.orgId}
                title="Copy organization id"
                className="shrink-0 p-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
              >
                {copied ? (
                  <Check className="size-3 tone-green" />
                ) : (
                  <Copy className="size-3" />
                )}
              </button>
            </div>
          </div>

          <div className="space-y-1">
            <p className="text-muted-foreground">Actor (user) id</p>
            <code className="block truncate rounded bg-card px-1.5 py-1 font-mono text-[10px] text-foreground">
              {identity.userId ?? "â€” (resolved from API key)"}
            </code>
          </div>

          {!identity.resolved ? (
            <div className="flex items-start gap-1.5 rounded-md border p-2 text-[10px] pill pill-amber">
              <TriangleAlert className="mt-0.5 size-3 shrink-0" />
              <span>
                No tenant resolved. Set <code>CONTEXTA_DASHBOARD_API_KEY</code>{" "}
                (recommended) or fill the form below. Until then the API rejects
                every call with 401.
              </span>
            </div>
          ) : null}

          {probe ? (
            <div
              className={`rounded border p-2 text-[10px] ${
                probe.ok
                  ? "pill pill-green"
                  : "pill pill-red"
              }`}
            >
              {probe.ok ? (
                <span>
                  API resolved organization{" "}
                  <code className="font-mono">{probe.resolvedOrgId ?? "unknown"}</code>{" "}
                  ({probe.keyCount} key{probe.keyCount === 1 ? "" : "s"} visible)
                </span>
              ) : (
                <span>{probe.error}</span>
              )}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={runProbe}
              disabled={pending}
              className="nb-btn nb-btn-secondary px-2 py-1 text-[10px]"
            >
              {pending ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <RotateCcw className="size-3" />
              )}
              <span>Verify with API</span>
            </button>
            {identity.authRequired ? (
              <form action={signOutAction}>
                <button type="submit" className="nb-btn nb-btn-ghost px-2 py-1 text-[10px]">
                  <LogOut className="size-3" strokeWidth={1.75} />
                  <span>Sign out</span>
                </button>
              </form>
            ) : null}
          </div>

          <form action={apply} className="space-y-2 border-t border-border pt-2.5">
            <p className="text-muted-foreground">
              Point the console at a different tenant. The API re-checks every
              header, so a mismatch fails loudly instead of reading another
              organization&apos;s rows.
            </p>
            <input
              name="org_id"
              defaultValue={identity.orgId ?? ""}
              placeholder="Organization UUID"
              className="w-full rounded border border-border bg-card px-2 py-1.5 font-mono text-[10px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-ring"
            />
            <input
              name="user_id"
              defaultValue={identity.userId ?? ""}
              placeholder="User UUID (optional)"
              className="w-full rounded border border-border bg-card px-2 py-1.5 font-mono text-[10px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-ring"
            />
            <input
              name="api_key"
              type="password"
              placeholder="Bootstrap API key (optional)"
              className="w-full rounded border border-border bg-card px-2 py-1.5 font-mono text-[10px] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-ring"
            />
            {error ? <p className="tone-red">{error}</p> : null}
            <div className="flex gap-1.5">
              <button
                type="submit"
                disabled={pending}
                className="nb-btn nb-btn-primary flex-1 justify-center px-2 py-1 text-[10px]"
              >
                {pending ? <Loader2 className="size-3 animate-spin" /> : null}
                <span>Apply</span>
              </button>
              <button
                type="submit"
                name="mode"
                value="reset"
                disabled={pending}
                className="nb-btn nb-btn-ghost px-2 py-1 text-[10px]"
              >
                <span>Reset to env</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
