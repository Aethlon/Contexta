import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";

const observe = `await fetch(process.env.CONTEXTA_API_URL + "/observations", {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "authorization": \`Bearer \${process.env.CONTEXTA_API_KEY}\`
  },
  body: JSON.stringify({
    user_id: "user-id",
    organization_id: "org-id",
    session_id: "session-id",
    messages: [{ role: "user", content: "Remember I prefer Python." }]
  })
})`;

const retrieve = `await fetch(process.env.CONTEXTA_API_URL + "/retrieve", {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "authorization": \`Bearer \${process.env.CONTEXTA_API_KEY}\`
  },
  body: JSON.stringify({
    user_id: "user-id",
    organization_id: "org-id",
    query_text: "What should this agent remember?"
  })
})`;

export default function DocsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Setup</h2>
        <p className="text-sm text-muted-foreground">Create a backend-synced key, add it to your agent environment, then send observations and retrieve context.</p>
      </div>
      <Tabs
        tabs={[
          {
            label: "Environment",
            content: (
              <Card>
                <CardHeader><CardTitle>.env</CardTitle></CardHeader>
                <CardContent>
                  <pre className="overflow-x-auto rounded-md bg-background p-4 font-mono text-xs text-muted-foreground">
{`CONTEXTA_API_URL=http://localhost:8000
CONTEXTA_API_KEY=mk_live_...`}
                  </pre>
                </CardContent>
              </Card>
            ),
          },
          {
            label: "Observe",
            content: (
              <Card>
                <CardHeader><CardTitle>Send observations</CardTitle></CardHeader>
                <CardContent><pre className="overflow-x-auto rounded-md bg-background p-4 font-mono text-xs text-muted-foreground">{observe}</pre></CardContent>
              </Card>
            ),
          },
          {
            label: "Retrieve",
            content: (
              <Card>
                <CardHeader><CardTitle>Retrieve context</CardTitle></CardHeader>
                <CardContent><pre className="overflow-x-auto rounded-md bg-background p-4 font-mono text-xs text-muted-foreground">{retrieve}</pre></CardContent>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
