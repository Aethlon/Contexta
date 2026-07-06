import type { contextaConfig } from "./types.js";
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
import { DurableBuffer } from "./buffer.js";

const SDK_VERSION = "0.1.0";

function uuidV7(): string {
  const now = Date.now();
  const hex = now.toString(16).padStart(12, "0");
  const rest = Array.from({ length: 24 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-7${rest.slice(0, 3)}-${(8 + Math.floor(Math.random() * 4)).toString(16)}${rest.slice(3, 7)}-${rest.slice(7)}`;
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
  return {
    apiKey,
    baseUrl: getEnvVar("CONTEXTA_API_URL") ?? "https://api.contexta.dev",
    timeout: parseInt(getEnvVar("CONTEXTA_TIMEOUT") ?? "30000", 10),
    maxRetries: parseInt(getEnvVar("CONTEXTA_MAX_RETRIES") ?? "3", 10),
    telemetry: getEnvVar("CONTEXTA_TELEMETRY") !== "false",
  };
}

export class HttpClient {
  private apiKey: string;
  private baseUrl: string;
  private timeout: number;
  private maxRetries: number;
  private telemetry: boolean;
  private buffer: DurableBuffer;

  constructor(config: contextaConfig) {
    this.apiKey = config.apiKey;
    this.baseUrl = (config.baseUrl ?? "https://api.contexta.dev").replace(/\/+$/, "");
    this.timeout = config.timeout ?? 30_000;
    this.maxRetries = config.maxRetries ?? 3;
    this.telemetry = config.telemetry !== false;
    this.buffer = new DurableBuffer();
  }

  async init(): Promise<void> {
    await this.buffer.waitForInit();
  }

  async request<T>(
    method: string,
    path: string,
    body?: Record<string, unknown> | Record<string, unknown>[],
    options?: { idempotent?: boolean }
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const isWrite = ["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase());
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.apiKey}`,
      "User-Agent": `contexta-sdk-ts/${SDK_VERSION}`,
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

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const response = await fetch(url, fetchOptions);
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
      return (Deno as Record<string, unknown>).env?.get?.(name) as string | undefined;
    } catch {
      return undefined;
    }
  }
  return undefined;
}
