import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  AsyncContexta,
  Asynccontexta,
  Contexta,
  contexta,
} from "../src/client";

describe("Contexta TypeScript Client", () => {
  it("should support getMany, retrieveBatch, feedback, addRule, investigate, and reflect", async () => {
    const client = new Contexta({ apiKey: "mk_test_123" });

    const mockRequest = vi
      .spyOn((client as any).http, "request")
      .mockImplementation(async (method, path, body) => {
        if (path === "/memories/batch-get") {
          return { count: 1, memories: [{ id: "m1", title: "Test" }] };
        }
        if (path === "/retrieve/batch") {
          return { status: "success", count: 1, batchResults: [] };
        }
        if (path === "/memories/m1/feedback") {
          return { status: "success", memoryId: "m1", utilityScore: 0.8 };
        }
        if (path === "/observations") {
          return { status: "accepted", jobId: "obs_1" };
        }
        if (path === "/retrieve/investigate") {
          return { status: "success", query: "investigate query", results: [] };
        }
        if (path === "/memories/reflect") {
          return {
            status: "success",
            contradictionsResolved: 1,
            patternsConsolidated: 1,
          };
        }
        return {};
      });

    const memories = await client.getMany(["m1"]);
    expect(memories.length).toBe(1);
    expect(mockRequest).toHaveBeenCalledWith("POST", "/memories/batch-get", { memory_ids: ["m1"] });

    const batchRet = await client.retrieveBatch([
      { userId: "u1", organizationId: "org1", queryText: "test" },
    ]);
    expect(Array.isArray(batchRet)).toBe(true);
    expect(mockRequest).toHaveBeenCalledWith(
      "POST",
      "/retrieve/batch",
      expect.objectContaining({ queries: [expect.objectContaining({ query_text: "test" })] })
    );

    const fb = await client.feedback("m1", { signal: "positive" });
    expect(fb.status).toBe("success");
    expect(mockRequest).toHaveBeenCalledWith("POST", "/memories/m1/feedback", {
      signal: "positive",
      penalty: 0.5,
    });

    const ruleRes = await client.addRule({
      userId: "u1",
      rule: "Always respond in concise bullet points",
    });
    expect(ruleRes.status).toBe("accepted");
    expect(mockRequest).toHaveBeenCalledWith(
      "POST",
      "/observations",
      expect.objectContaining({
        user_id: "u1",
        metadata: expect.objectContaining({ memory_type: "procedural" }),
      })
    );

    const invRes = await client.investigate({
      userId: "u1",
      queryText: "What stack did we use earlier?",
    });
    expect(invRes.status).toBe("success");
    expect(mockRequest).toHaveBeenCalledWith(
      "POST",
      "/retrieve/investigate",
      expect.objectContaining({
        query_text: "What stack did we use earlier?",
        user_id: "u1",
      })
    );

    const refRes = await client.reflect({ userId: "u1" });
    expect(refRes.status).toBe("success");
    expect(mockRequest).toHaveBeenCalledWith(
      "POST",
      "/memories/reflect",
      expect.objectContaining({ user_id: "u1", apply_supersession: true })
    );
  });

  it("sends user_id, organization_id and session_id to GET /memories/context", async () => {
    const client = new Contexta({ apiKey: "mk_test_123" });
    const mockRequest = vi
      .spyOn((client as any).http, "request")
      .mockResolvedValue({ userProfile: null, relevantMemories: [], tokenUsage: { total: 0 } });

    await client.context({
      userId: "11111111-1111-4111-8111-111111111111",
      organizationId: "22222222-2222-4222-8222-222222222222",
      sessionId: "33333333-3333-4333-8333-333333333333",
      tokenBudget: 2000,
    });

    const [method, path, , options] = mockRequest.mock.calls[0];
    expect(method).toBe("GET");
    expect(path.startsWith("/memories/context?")).toBe(true);
    expect(path).toContain("user_id=11111111-1111-4111-8111-111111111111");
    expect(path).toContain("organization_id=22222222-2222-4222-8222-222222222222");
    expect(path).toContain("session_id=33333333-3333-4333-8333-333333333333");
    expect(path).toContain("token_budget=2000");
    expect(options.headers["X-contexta-User-Id"]).toBe("11111111-1111-4111-8111-111111111111");
  });

  it("escapes the /v1 prefix for the health check", async () => {
    const client = new Contexta({ apiKey: "mk_test_123", baseUrl: "https://api.example.com/v1" });
    const mockRequest = vi
      .spyOn((client as any).http, "request")
      .mockResolvedValue({ status: "ok", version: "0.1.0" });

    await client.ping();

    const [, path, , options] = mockRequest.mock.calls[0];
    expect(path).toBe("/healthz");
    expect(options.absolute).toBe(true);
    expect((client as any).http.resolve("/healthz", true)).toBe("https://api.example.com/healthz");
  });

  it("close() is safe to call twice and flush() drains the durable buffer", async () => {
    const client = new Contexta({ apiKey: "mk_test_123" });
    const buffer = (client as any).http.buffer;

    const drained: string[] = [];
    await buffer.push("https://api.example.com/v1/observations", "{}", {});
    const flushed = await client.flush();
    expect(flushed).toBe(0);
    expect(drained).toEqual([]);

    client.close();
    expect(() => client.close()).not.toThrow();
    await expect(client.flush()).rejects.toThrow(/closed/i);
  });

  it("keeps the deprecated lowercase names working with a single warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const legacySync = new contexta({ apiKey: "mk_test_123" });
      const legacyAsync = new Asynccontexta({ apiKey: "mk_test_123" });
      expect(legacySync).toBeInstanceOf(Contexta);
      expect(legacyAsync).toBeInstanceOf(AsyncContexta);
      expect(legacySync.context).toBeInstanceOf(Function);
      expect(legacyAsync.reflect).toBeInstanceOf(Function);
      expect(warn).toHaveBeenCalledTimes(2);
    } finally {
      warn.mockRestore();
    }
  });
});
