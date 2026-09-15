import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

const CONTEXTA_API_URL = (process.env.CONTEXTA_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const MONO_REPO_ROOT = path.resolve(process.cwd(), "..");

export async function GET() {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2000);

  let online = false;
  let statusText = "offline";
  let latencyMs = 0;
  const start = Date.now();

  try {
    const res = await fetch(`${CONTEXTA_API_URL}/docs`, {
      signal: controller.signal,
      headers: { Accept: "text/html" },
    });
    latencyMs = Date.now() - start;
    if (res.ok || res.status === 404 || res.status === 200) {
      online = true;
      statusText = "online";
    }
  } catch (err: any) {
    statusText = err?.name === "AbortError" ? "timeout" : "offline";
  } finally {
    clearTimeout(timeoutId);
  }

  return NextResponse.json({
    online,
    status: statusText,
    url: CONTEXTA_API_URL,
    latency_ms: latencyMs,
    native_runtime: true,
  });
}

export async function POST() {
  try {
    const venvPython = path.join(MONO_REPO_ROOT, ".venv", "Scripts", "python.exe");
    const hasVenv = fs.existsSync(venvPython);

    const execPath = hasVenv ? venvPython : "python";
    const args = ["-m", "uvicorn", "contexta.api.app:app", "--host", "127.0.0.1", "--port", "8000"];

    const engineProcess = spawn(execPath, args, {
      cwd: MONO_REPO_ROOT,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: {
        ...process.env,
        CONTEXTA_DB_BOOT_CHECK: "false",
        CONTEXTA_CELERY_TASK_ALWAYS_EAGER: "true",
        PYTHONUNBUFFERED: "1",
      },
    });
    engineProcess.unref();

    return NextResponse.json({
      success: true,
      message: "Contexta native engine startup initiated silently in the background.",
    });
  } catch (err: any) {
    return NextResponse.json(
      {
        success: false,
        error: err?.message || "Failed to initiate native engine launch.",
      },
      { status: 500 }
    );
  }
}
