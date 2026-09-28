import { NextResponse } from "next/server";

/**
 * End-to-end verification for the MCP setup wizard.
 *
 * The setup screen has exactly two ways to fail, and they are independent:
 *
 *   1. the MCP transport is not running (or is not speaking MCP at all)
 *   2. the API key is wrong, revoked, or belongs to another tenant
 *
 * So we check both, separately, and report each one. A single boolean would
 * leave the user guessing which half is broken.
 */

const MCP_PORT = 8765;
const MCP_URL = process.env.CONTEXTA_MCP_URL ?? `http://localhost:${MCP_PORT}`;
const API_URL = (process.env.CONTEXTA_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const PROTOCOL_VERSION = "2025-06-18";

export async function POST(request: Request) {
  let apiKey = "";
  try {
    const body = await request.json();
    apiKey = typeof body?.apiKey === "string" ? body.apiKey.trim() : "";
  } catch {
    return NextResponse.json(
      { ok: false, transport: { ok: false, error: "Malformed request." }, key: { ok: false, error: "Malformed request." } },
      { status: 400 },
    );
  }

  // 1. Is the MCP transport alive and speaking the protocol?
  const transport = await checkTransport();

  // 2. Is the key accepted by the API, and does its tenant resolve?
  const key = apiKey ? await checkKey(apiKey) : { ok: false, error: "No API key supplied." };

  return NextResponse.json({
    ok: transport.ok && key.ok,
    transport,
    key,
  });
}

async function checkTransport() {
  const started = Date.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);

  try {
    // A real MCP streamable-HTTP handshake: POST initialize and require both a
    // 2xx and a session id. Hitting the URL is not enough — an unrelated server
    // on :8765 would also answer.
    const res = await fetch(`${MCP_URL}/mcp`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
          protocolVersion: PROTOCOL_VERSION,
          capabilities: {},
          clientInfo: { name: "contexta-console", version: "1.0" },
        },
      }),
    });

    const latencyMs = Date.now() - started;

    if (!res.ok) {
      return {
        ok: false,
        latencyMs,
        error: `MCP server answered ${res.status}. Is the mcp container running?`,
      };
    }

    const sessionId = res.headers.get("mcp-session-id");
    if (!sessionId) {
      return {
        ok: false,
        latencyMs,
        error: "Endpoint responded but did not complete an MCP handshake.",
      };
    }

    return { ok: true, latencyMs, url: `${MCP_URL}/mcp`, protocol: PROTOCOL_VERSION };
  } catch (err) {
    const latencyMs = Date.now() - started;
    return {
      ok: false,
      latencyMs,
      error:
        err instanceof Error && err.name === "AbortError"
          ? "MCP server did not respond within 5s."
          : `Cannot reach the MCP server at ${MCP_URL}. Is it running?`,
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function checkKey(apiKey: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);

  try {
    const res = await fetch(`${API_URL}/v1/memories?limit=1`, {
      signal: controller.signal,
      headers: { "x-api-key": apiKey },
    });

    if (res.status === 401 || res.status === 403) {
      return { ok: false, error: "That API key was rejected. Mint a fresh one and try again." };
    }
    if (!res.ok) {
      return { ok: false, error: `The API answered ${res.status} for this key.` };
    }
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error:
        err instanceof Error && err.name === "AbortError"
          ? "The Contexta API did not respond within 8s."
          : `Cannot reach the Contexta API at ${API_URL}.`,
    };
  } finally {
    clearTimeout(timeout);
  }
}
