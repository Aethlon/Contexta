import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { AsyncContexta, Asynccontexta, Contexta, contexta } from "../src/client.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const MANIFEST_PATH = resolve(HERE, "../../public-api.manifest.json");

interface Manifest {
  version: number;
  typescript: {
    clientClass: string;
    asyncClientClass: string;
    deprecatedAliases: Record<string, string>;
  };
  methods: { name: string; typescript: string }[];
}

const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf-8")) as Manifest;

function collectFunctionNames(prototype: object | null): Set<string> {
  const names = new Set<string>();
  let current = prototype;
  while (current && current !== Object.prototype && current !== Function.prototype) {
    for (const name of Object.getOwnPropertyNames(current)) {
      if (name.startsWith("_") || name === "constructor") continue;
      const descriptor = Object.getOwnPropertyDescriptor(current, name);
      if (descriptor && typeof descriptor.value === "function") {
        names.add(name);
      }
    }
    current = Object.getPrototypeOf(current);
  }
  return names;
}

function publicMethods(instance: object): Set<string> {
  return new Set([
    ...collectFunctionNames(Object.getPrototypeOf(instance)),
    ...collectFunctionNames(instance.constructor as object),
  ]);
}

describe("public API parity", () => {
  it("has a readable manifest", () => {
    expect(manifest.version).toBe(1);
    expect(manifest.methods.length).toBeGreaterThan(0);
  });

  it.each([
    ["Contexta", () => new Contexta({ apiKey: "mk_test" })],
    ["AsyncContexta", () => new AsyncContexta({ apiKey: "mk_test" })],
  ])("%s exposes exactly the manifest methods", (name, build) => {
    const expected = new Set(manifest.methods.map((entry) => entry.typescript));
    const actual = publicMethods(build());
    expect([...actual].sort()).toEqual([...expected].sort());
    expect(name).toBeTruthy();
  });

  it("keeps the deprecated lowercase aliases", () => {
    const expected = manifest.typescript.deprecatedAliases;
    expect(expected).toEqual({ contexta: "Contexta", Asynccontexta: "AsyncContexta" });
    expect(new contexta({ apiKey: "mk_test" })).toBeInstanceOf(Contexta);
    expect(new Asynccontexta({ apiKey: "mk_test" })).toBeInstanceOf(AsyncContexta);
  });

  it("matches the Python naming in the manifest", () => {
    const pythonNames = manifest.methods.map((entry) => entry.name);
    const tsNames = manifest.methods.map((entry) => entry.typescript);
    expect(new Set(pythonNames).size).toBe(pythonNames.length);
    expect(new Set(tsNames).size).toBe(tsNames.length);
  });
});
