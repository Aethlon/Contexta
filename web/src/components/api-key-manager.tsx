"use client";

import * as React from "react";
import { CheckCircle2, Copy, Loader2, RefreshCw, Trash2, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { createApiKeyAction } from "@/app/actions";

const AVAILABLE_SCOPES = [
  { id: "observe", label: "Observe", description: "Write observations" },
  { id: "retrieve", label: "Retrieve", description: "Read memories and context" },
] as const;

type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  organization_id: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
};

type CreatedApiKey = {
  token: string;
  key: ApiKey;
};

export function ApiKeyManager({ initialKeys = [] }: { initialKeys?: ApiKey[] }) {
  const [keys, setKeys] = React.useState<ApiKey[]>(initialKeys);
  const [created, setCreated] = React.useState<CreatedApiKey | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isCreating, setIsCreating] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [selectedScopes, setSelectedScopes] = React.useState<string[]>(["observe", "retrieve"]);

  async function loadKeys() {
    setIsLoading(true);
    setError(null);
    try {
      const { listApiKeysAction } = await import("@/app/actions");
      const data = await listApiKeysAction();
      setKeys(data as ApiKey[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load keys");
    }
    setIsLoading(false);
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsCreating(true);
    setError(null);
    setCreated(null);
    const form = new FormData(event.currentTarget);
    form.set("scopes", selectedScopes.join(","));
    const result = await createApiKeyAction(form);
    setIsCreating(false);
    if (result?.error) {
      setError(result.error);
      return;
    }
    if (result?.data) {
      setCreated(result.data as CreatedApiKey);
      setKeys((current) => [result.data.key, ...current.filter((key) => key.id !== result.data.key.id)]);
    }
    event.currentTarget?.reset();
  }

  async function handleRevoke(keyId: string) {
    const { contextaFetch } = await import("@/lib/auth-helpers");
    const res = await contextaFetch(`/v1/keys/${keyId}`, { method: "DELETE" });
    if (res.ok) {
      setKeys((current) => current.filter((k) => k.id !== keyId));
    }
  }

  async function copyToken() {
    if (created?.token) {
      await navigator.clipboard.writeText(created.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[0.82fr_1.18fr]">
      <Card>
        <CardHeader>
          <CardTitle>Create API Key</CardTitle>
          <CardDescription>Keys are created by the contexta backend and scoped to this organization.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {created ? (
            <div className="mb-4 border-b border-[var(--color-graphite)]/30 pb-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 size={18} strokeWidth={1.2} className="text-[var(--color-smoke)] mt-0.5" />
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-normal text-[var(--color-ghost)]">Copy this token now</span>
                  <span className="text-xs font-light text-[var(--color-smoke)]">It will not be shown again.</span>
                </div>
              </div>
              <code className="mt-3 block break-all rounded-xl bg-[var(--color-abyss)] p-3 font-mono text-xs text-[var(--color-ghost)] border border-[var(--color-graphite)]/30">
                {created.token}
              </code>
              <Button className="mt-3" onClick={copyToken} variant="outline">
                {copied ? "Copied!" : <><Copy className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.2} /> Copy</>}
              </Button>
            </div>
          ) : null}

          {error ? (
            <div className="mb-4 flex items-start gap-3">
              <AlertCircle size={18} strokeWidth={1.2} className="text-[var(--color-smoke)] mt-0.5" />
              <div className="flex flex-col gap-1">
                <span className="text-sm font-normal text-[var(--color-ghost)]">Key generation failed</span>
                <span className="text-xs font-light text-[var(--color-smoke)]">{error}</span>
              </div>
            </div>
          ) : null}

          <form className="space-y-6" onSubmit={onSubmit}>
            <div className="flex flex-col gap-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" name="name" placeholder="Production agent" required />
            </div>
            <div className="flex flex-col gap-3">
              <Label>Scopes</Label>
              <div className="flex flex-col gap-2">
                {AVAILABLE_SCOPES.map((scope) => (
                  <label key={scope.id} className="flex items-center gap-3 rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 cursor-pointer hover:bg-[var(--color-charcoal)] transition-colors duration-200">
                    <Checkbox
                      checked={selectedScopes.includes(scope.id)}
                      onCheckedChange={(checked) => {
                        setSelectedScopes((prev) =>
                          checked ? [...prev, scope.id] : prev.filter((s) => s !== scope.id),
                        );
                      }}
                    />
                    <div className="leading-tight">
                      <p className="text-sm font-normal text-[var(--color-ghost)]">{scope.label}</p>
                      <p className="text-xs font-light text-[var(--color-smoke)]">{scope.description}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
            <Button disabled={isCreating} type="submit">
              {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Generate key
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
          <div>
            <CardTitle>Active Keys</CardTitle>
            <CardDescription>Prefixes, scopes, and usage metadata from contexta.</CardDescription>
          </div>
          <Button disabled={isLoading} onClick={() => void loadKeys()} type="button" variant="outline" className="h-9 px-3">
            <RefreshCw className={isLoading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} strokeWidth={1.2} />
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>Scopes</TableHead>
                <TableHead>Created</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((key) => (
                <TableRow key={key.id} className="hover:bg-[var(--color-charcoal)]/30 transition-colors duration-200">
                  <TableCell className="font-normal text-[var(--color-ghost)]">{key.name}</TableCell>
                  <TableCell className="font-mono text-xs text-[var(--color-smoke)]">{key.prefix}...</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {key.scopes.map((scope) => <Badge key={scope}>{scope}</Badge>)}
                    </div>
                  </TableCell>
                  <TableCell className="text-[var(--color-smoke)] text-xs">
                    {new Date(key.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell>
                    <Button onClick={() => handleRevoke(key.id)} variant="ghost" className="h-8 w-8 p-0 rounded-lg">
                      <Trash2 className="h-3.5 w-3.5 text-[var(--color-smoke)] hover:text-red-400" strokeWidth={1.2} />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!isLoading && keys.length === 0 ? (
                <TableRow>
                  <TableCell className="text-[var(--color-smoke)] text-center py-8 font-light" colSpan={5}>
                    No API keys yet.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
