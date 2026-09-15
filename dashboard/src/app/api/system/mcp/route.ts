import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

const MCP_PORT = 8765;
const MCP_SERVER_URL = process.env.CONTEXTA_MCP_URL ?? `http://localhost:${MCP_PORT}`;
const MONO_REPO_ROOT = path.resolve(process.cwd(), "..");

export async function GET() {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2000);

  let online = false;
  let latencyMs = 0;
  const start = Date.now();

  try {
    const res = await fetch(`${MCP_SERVER_URL}/sse`, {
      signal: controller.signal,
      headers: { Accept: "text/event-stream" },
    });
    latencyMs = Date.now() - start;
    if (res.status === 200 || res.ok) {
      online = true;
    }
  } catch {
    online = false;
  } finally {
    clearTimeout(timeoutId);
  }

  return NextResponse.json({
    online,
    port: MCP_PORT,
    url: MCP_SERVER_URL,
    latency_ms: latencyMs,
  });
}

export async function POST() {
  try {
    const venvPython = path.join(MONO_REPO_ROOT, ".venv", "Scripts", "python.exe");
    const hasVenv = fs.existsSync(venvPython);

    const execPath = hasVenv ? venvPython : "python";
    const args = ["-m", "contexta.mcp", "--transport", "sse", "--port", String(MCP_PORT)];

    const mcpProcess = spawn(execPath, args, {
      cwd: MONO_REPO_ROOT,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: {
        ...process.env,
        CONTEXTA_DB_BOOT_CHECK: "false",
        PYTHONUNBUFFERED: "1",
      },
    });
    mcpProcess.unref();

    return NextResponse.json({
      success: true,
      message: "Contexta MCP Server startup initiated silently in background.",
    });
  } catch (err: any) {
    return NextResponse.json(
      {
        success: false,
        error: err?.message || "Failed to start MCP server.",
      },
      { status: 500 }
    );
  }
}
