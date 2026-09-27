import type { contextaConfig, FetchLike, TlsOptions } from "./types.js";
import {
  AuthenticationError,
  AuthorizationError,
  ValidationError,
  QuotaExceeded,
  RateLimited,
  ServerError,
  NotFoundError,
  ConflictError,
  contextaError,
} from "./types.js";
import { DurableBuffer, type QueuedEntry } from "./buffer.js";

const SDK_VERSION = "0.2.0";

let insecureTlsWarned = false;

export function uuidV7(): string {
  const hex = (value: number, width: number) => value.toString(16).padStart(width, "0");
  const timestamp = Date.now() & 0xffffffffffff;
  const randA = Math.floor(Math.random() * 0x1000);
  const randBHi = Math.floor(Math.random() * 0x4000);
  const randBLo = Math.floor(Math.random() * 0x1000000000000);
  return [
    hex(timestamp >>> 16, 8),
    hex(timestamp & 0xffff, 4),
    hex(0x7000 | randA, 4),
    hex(0x8000 | randBHi, 4),
    hex(randBLo, 12),
  ].join("-");
}

function getRuntime(): string {
  if (typeof process !== "undefined" && process.versions?.node) {
    return `node/${process.versions.node}`;
  }
  if (typeof Deno !== "undefined") {
    return `deno/${(Deno as Record<string, unknown>).version as string}`;
  }
  if (typeof Bun !== "undefined") {
    return "bun/1";
  }
  if (typeof navigator !== "undefined") {
    return `browser/${navigator.userAgent}`;
  }
  return "unknown";
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function configFromEnv(): contextaConfig {
  const apiKey = getEnvVar("CONTEXTA_API_KEY");
  if (!apiKey) {
    throw new contextaError(
      "CONTEXTA_API_KEY is not set. Pass apiKey directly or set the environment variable.",
      0,
      "config_error"
    );
  }
  const caPath = getEnvVar("CONTEXTA_CA_BUNDLE");
  const verify = getEnvVar("CONTEXTA_VERIFY_TLS");
  return {
    apiKey,
    baseUrl: getEnvVar("CONTEXTA_API_URL") ?? "https://api.contexta.dev",
    timeout: parseInt(getEnvVar("CONTEXTA_TIMEOUT") ?? "30000", 10),
    maxRetries: parseInt(getEnvVar("CONTEXTA_MAX_RETRIES") ?? "3", 10),
    telemetry: getEnvVar("CONTEXTA_TELEMETRY") !== "false",
    organizationId: getEnvVar("CONTEXTA_ORGANIZATION_ID"),
    tls: {
      ...(caPath ? { caPath } : {}),
      rejectUnauthorized: verify === undefined ? undefined : verify !== "false",
    },
  };
}

async function buildDispatcher(tls: TlsOptions | undefined): Promise<unknown> {
  if (!tls) return undefined;
  const wantsCustomCa = Boolean(tls.ca || tls.caPath);
  const wantsInsecure = tls.rejectUnauthorized === false;
  if (!wantsCustomCa && !wantsInsecure) return undefined;

  if (wantsInsecure && !insecureTlsWarned) {
    insecureTlsWarned = true;
    console.warn(
      "[contexta] TLS certificate verification is DISABLED (tls.rejectUnauthorized=false). " +
        "Only use this against a local, trusted gateway."
    );
  }

  let ca: string | undefined = tls.ca;
  if (!ca && tls.caPath) {
    const fs = await importFs();
    if (!fs) {
      throw new contextaError(
        `tls.caPath requires Node filesystem access; pass tls.ca instead or use tls.caPath on Node. (${tls.caPath})`,
        0,
        "config_error"
      );
    }
    ca = fs.readFileSync(tls.caPath, "utf-8");
  }

  const undici = await importUndici();
  if (!undici) {
    throw new contextaError(
      "Custom TLS options require the optional 'undici' package in Node. " +
        "Install undici, or pass config.fetch with your own TLS-configured fetch implementation.",
      0,
      "config_error"
    );
  }
  return new undici.Agent({
    connect: {
      ...(ca ? { ca } : {}),
      ...(wantsInsecure ? { rejectUnauthorized: false } : {}),
    },
  });
}

async function importUndici(): Promise<{ Agent: new (options: unknown) => unknown } | null> {
  try {
    const mod = (await import(/* @vite-ignore */ "undici" as string)) as unknown as {
      Agent: new (options: unknown) => unknown;
    };
    return typeof mod?.Agent === "function" ? mod : null;
  } catch {
    return null;
  }
}

async function importFs(): Promise<{ readFileSync: (path: string, encoding: string) => string } | null> {
  try {
    const mod = (await import(/* @vite-ignore */ "node:fs" as string)) as unknown as {
      readFileSync: (path: string, encoding: string) => string;
    };
    return typeof mod?.readFileSync === "function" ? mod : null;
  } catch {
    return null;
  }
}

export interface RequestOptions {
  idempotent?: boolean;
  headers?: Record<string, string>;
  absolute?: boolean;
}

export class HttpClient {
  private apiKey: string;
  private baseUrl: string;
  private originUrl: string;
  private timeout: number;
  private maxRetries: number;
  private telemetry: boolean;
  private buffer: DurableBuffer;
  private fetchImpl: FetchLike;
  private dispatcher: unknown;
  private dispatcherReady: Promise<unknown>;
  private closed = false;

  constructor(config: contextaConfig) {
    this.apiKey = config.apiKey;
    this.baseUrl = (config.baseUrl ?? "https://api.contexta.dev").replace(/\/+$/, "");
    this.originUrl = this.baseUrl.endsWith("/v1") ? this.baseUrl.slice(0, -3) : this.baseUrl;
    this.timeout = config.timeout ?? 30_000;
    this.maxRetries = config.maxRetries ?? 3;
    this.telemetry = config.telemetry !== false;
    this.buffer = new DurableBuffer();
    this.fetchImpl = config.fetch ?? ((input, init) => fetch(input, init));
    this.dispatcher = config.dispatcher;
    this.dispatcherReady = config.dispatcher
      ? Promise.resolve(config.dispatcher)
      : buildDispatcher(config.tls);
  }

  get origin(): string {
    return this.originUrl;
  }

  async init(): Promise<void> {
    await this.buffer.waitForInit();
  }

  resolve(path: string, absolute = false): string {
    return `${absolute ? this.originUrl : this.baseUrl}${path}`;
  }

  async request<T>(
    method: string,
    path: string,
    body?: Record<string, unknown> | Record<string, unknown>[],
    options?: RequestOptions
  ): Promise<T> {
    if (this.closed) {
      throw new contextaError("Client is closed.", 0, "client_closed");
    }
    const url = this.resolve(path, options?.absolute);
    const isWrite = ["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase());
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.apiKey}`,
      "User-Agent": `contexta-sdk-ts/${SDK_VERSION}`,
      ...(options?.headers ?? {}),
    };

    if (isWrite && !options?.idempotent) {
      headers["Idempotency-Key"] = uuidV7();
    }

    if (this.telemetry) {
      headers["X-contexta-SDK"] = `typescript/${SDK_VERSION}`;
      headers["X-contexta-Runtime"] = getRuntime();
    }

    const fetchOptions: RequestInit = {
      method,
      headers,
      signal: AbortSignal.timeout(this.timeout),
    };

    if (body !== undefined) {
      fetchOptions.body = JSON.stringify(body);
    }

    const dispatcher = await this.dispatcherReady;
    if (dispatcher !== undefined) {
      (fetchOptions as { dispatcher?: unknown }).dispatcher = dispatcher;
    }

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const response = await this.fetchImpl(url, fetchOptions);
        return await this.handleResponse<T>(response);
      } catch (err) {
        if (err instanceof contextaError) {
          throw err;
        }

        const isLastAttempt = attempt === this.maxRetries;

        if (err instanceof TypeError || (err instanceof DOMException && err.name === "TimeoutError")) {
          if (isWrite && !options?.idempotent) {
            try {
              await this.buffer.push(url, JSON.stringify(body ?? {}), headers);
            } catch {
            }
          }
          if (isLastAttempt) {
            throw new contextaError(
              `Request failed after ${this.maxRetries + 1} attempts: ${(err as Error).message}`,
              0,
              "network_error"
            );
          }
          const delay = Math.min(1000 * 2 ** attempt + Math.random() * 200, 30_000);
          await sleep(delay);
          continue;
        }

        throw err;
      }
    }

    throw new contextaError("Unexpected error in request loop", 0, "internal_error");
  }

  /** Replay every buffered write. Entries that still fail are requeued or dead-lettered. */
  async flush(): Promise<number> {
    if (this.closed) {
      throw new contextaError("Client is closed.", 0, "client_closed");
    }
    await this.init();
    return this.buffer.drain(async (entry: QueuedEntry) => {
      const response = await this.fetchImpl(entry.url, {
        method: "POST",
        headers: entry.headers,
        body: entry.body,
        signal: AbortSignal.timeout(this.timeout),
      });
      if (!response.ok) {
        throw new contextaError(
          `Buffered request replay failed with HTTP ${response.status}`,
          response.status,
          "network_error"
        );
      }
    });
  }

  /** Release resources. Safe to call more than once. */
  close(): void {
    this.closed = true;
    const dispatcher = this.dispatcher as { close?: () => Promise<void> | void } | undefined;
    this.dispatcher = undefined;
    if (dispatcher && typeof dispatcher.close === "function") {
      void dispatcher.close();
    }
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (response.ok) {
      if (response.status === 204) {
        return undefined as T;
      }
      const json = await response.json();
      return this.camelCaseKeys(json) as T;
    }

    const body = await this.tryParseBody(response);

    if (response.status === 401) throw new AuthenticationError(body?.message as string | undefined);
    if (response.status === 403) throw new AuthorizationError(body?.message as string | undefined);
    if (response.status === 404) throw new NotFoundError(body?.message as string | undefined);
    if (response.status === 409) throw new ConflictError(body?.message as string | undefined);
    if (response.status === 422) {
      throw new ValidationError(
        body?.message as string | undefined,
        body?.errors as Record<string, string[]> | undefined
      );
    }
    if (response.status === 429) {
      const retryAfter = response.headers.get("Retry-After");
      throw new RateLimited(
        body?.message as string | undefined,
        retryAfter ? parseInt(retryAfter, 10) : undefined
      );
    }
    if (response.status >= 500) {
      throw new ServerError(body?.message as string | undefined, response.status);
    }

    throw new contextaError(
      (body?.message as string) ?? `HTTP ${response.status}`,
      response.status,
      "unknown"
    );
  }

  private async tryParseBody(response: Response): Promise<Record<string, unknown> | null> {
    try {
      return await response.json() as Record<string, unknown>;
    } catch {
      return null;
    }
  }

  private camelCaseKeys(obj: unknown): unknown {
    if (Array.isArray(obj)) {
      return obj.map((item) => this.camelCaseKeys(item));
    }
    if (obj !== null && typeof obj === "object") {
      const result: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
        const ccKey = key.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
        result[ccKey] = this.camelCaseKeys(value);
      }
      return result;
    }
    return obj;
  }
}

function getEnvVar(name: string): string | undefined {
  if (typeof process !== "undefined" && process.env) {
    return process.env[name];
  }
  if (typeof Deno !== "undefined") {
    try {
      return (Deno as { env?: { get?: (name: string) => string | undefined } }).env?.get?.(name) as string | undefined;
    } catch {
      return undefined;
    }
  }
  return undefined;
}
