"use client";

import * as React from "react";
import { CheckCircle2, Copy, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { createApiKeyAction } from "@/app/actions";

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
    form.set("scopes", String(form.get("scopes") || "observe,retrieve"));
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
    event.currentTarget.reset();
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
    <div className="grid gap-4 lg:grid-cols-[0.82fr_1.18fr]">
      <Card>
        <CardHeader>
          <CardTitle>Create API Key</CardTitle>
          <CardDescription>Keys are created by the contexta backend and scoped to this organization.</CardDescription>
        </CardHeader>
        <CardContent>
          {created ? (
            <div className="mb-4 rounded-md border border-primary/30 bg-accent p-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <CheckCircle2 className="h-4 w-4 text-primary" />
                Copy this token now
              </div>
              <code className="mt-2 block break-all rounded-md bg-background p-2 font-mono text-xs text-primary">
                {created.token}
              </code>
              <Button className="mt-2" onClick={copyToken} variant="outline">
                {copied ? "Copied!" : <><Copy className="mr-1 h-3 w-3" /> Copy</>}
              </Button>
            </div>
          ) : null}
          {error ? (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-foreground">
              {error}
            </div>
          ) : null}
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" name="name" placeholder="Production agent" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="scopes">Scopes (comma-separated)</Label>
              <Input id="scopes" name="scopes" defaultValue="observe,retrieve" />
            </div>
            <Button disabled={isCreating} type="submit">
              {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Generate key
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
          <div>
            <CardTitle>Active Keys</CardTitle>
            <CardDescription>Prefixes, scopes, and usage metadata from contexta.</CardDescription>
          </div>
          <Button disabled={isLoading} onClick={() => void loadKeys()} type="button" variant="outline">
            <RefreshCw className={isLoading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
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
                <TableRow key={key.id}>
                  <TableCell className="font-medium">{key.name}</TableCell>
                  <TableCell className="font-mono text-xs">{key.prefix}...</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {key.scopes.map((scope) => <Badge key={scope}>{scope}</Badge>)}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(key.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell>
                    <Button onClick={() => handleRevoke(key.id)} variant="ghost">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!isLoading && keys.length === 0 ? (
                <TableRow>
                  <TableCell className="text-muted-foreground" colSpan={5}>
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
