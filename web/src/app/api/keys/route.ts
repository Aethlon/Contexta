import { createcontextaApiKey, listcontextaApiKeys } from "@/lib/contexta-api";

export async function GET() {
  try {
    return Response.json(await listcontextaApiKeys());
  } catch (error) {
    return Response.json(
      { detail: error instanceof Error ? error.message : "Unable to load API keys." },
      { status: 502 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const scopes = Array.isArray(body.scopes)
      ? body.scopes
      : String(body.scope ?? "observe,retrieve").split(",");
    const created = await createcontextaApiKey({
      name: String(body.name ?? "Agent key"),
      scopes,
    });
    return Response.json(created, { status: 201 });
  } catch (error) {
    return Response.json(
      { detail: error instanceof Error ? error.message : "Unable to create API key." },
      { status: 502 },
    );
  }
}
