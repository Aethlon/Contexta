import { requireSession } from "@/lib/auth-helpers";
import { listApiKeysAction } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export const revalidate = 0;

export default async function SettingsPage() {
  const session = await requireSession();
  const keys = await listApiKeysAction();

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold">Settings</h2>
        <p className="text-sm text-muted-foreground">Configure organization defaults and manage members.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Organization</CardTitle>
          <CardDescription>Used for tenant isolation and API key ownership.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="org-name">Organization name</Label>
            <Input id="org-name" defaultValue={session.user.org_id ? `Org ${session.user.org_id.slice(0, 8)}` : "contexta"} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="org-slug">Slug</Label>
            <Input id="org-slug" defaultValue={session.user.org_id?.slice(0, 12) ?? "contexta"} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="api-url">Backend API URL</Label>
            <Input id="api-url" defaultValue={process.env.CONTEXTA_API_URL ?? "http://localhost:8000"} />
          </div>
          <Button>Save settings</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Your account details.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Email</Label>
            <p className="text-sm text-foreground">{session.user.email}</p>
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <p className="text-sm text-foreground">{session.user.name}</p>
          </div>
          <div className="space-y-2">
            <Label>Role</Label>
            <p className="text-sm text-foreground">{session.user.role}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>API Key Management</CardTitle>
          <CardDescription>Overview of keys created for this organization.</CardDescription>
        </CardHeader>
        <CardContent>
          {(keys as any[])?.length === 0 ? (
            <p className="text-sm text-muted-foreground">No API keys yet. Create one in the API keys page.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Prefix</TableHead>
                  <TableHead>Scopes</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(keys as any[]).map((key: any) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">{key.name}</TableCell>
                    <TableCell className="font-mono text-xs">{key.prefix}...</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {key.scopes.map((scope: string) => <Badge key={scope}>{scope}</Badge>)}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(key.created_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
