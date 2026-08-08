// Minimal ambient declarations for cross-runtime detection (Node/Deno/Bun).
// Keeps the SDK dependency-free; the real guards live in http.ts.

declare const process:
  | {
      env: Record<string, string | undefined>;
      versions?: { node?: string };
    }
  | undefined;

declare const Deno:
  | {
      version?: string;
      env?: { get?: (name: string) => string | undefined };
    }
  | undefined;

declare const Bun: unknown;
