import { describe, it, expect, vi } from "vitest";
import { contexta } from "../src/client";

describe("contexta TypeScript Client", () => {
  it("should support getMany, retrieveBatch, feedback, addRule, investigate, and reflect", async () => {
    const client = new contexta({ apiKey: "mk_test_123" });

    // Mock the internal request method
    const mockRequest = vi.spyOn((client as any).http, "request").mockImplementation(async (method, path, body) => {
      if (path === "/memories/batch-get") {
        return { count: 1, memories: [{ id: "m1", title: "Test" }] };
      }
      if (path === "/retrieve/batch") {
        return { status: "success", count: 1, batch_results: [] };
      }
      if (path === "/memories/m1/feedback") {
        return { status: "success", memory_id: "m1", utility_score: 0.8 };
      }
      if (path === "/observations") {
        return { status: "success", observation_id: "obs_1" };
      }
      if (path === "/retrieve/investigate") {
        return { status: "success", query: "investigate query", results: [] };
      }
      if (path === "/memories/reflect") {
        return { status: "success", contradictions_resolved: 1, patterns_consolidated: 1 };
      }
      return {};
    });

    const memories = await client.getMany(["m1"]);
    expect(memories.length).toBe(1);
    expect(mockRequest).toHaveBeenCalledWith("POST", "/memories/batch-get", { memory_ids: ["m1"] });

    const batchRet = await client.retrieveBatch([{ userId: "u1", organizationId: "org1", queryText: "test" }]);
    expect(Array.isArray(batchRet)).toBe(true);
    expect(mockRequest).toHaveBeenCalledWith("POST", "/retrieve/batch", expect.any(Object));

    const fb = await client.feedback("m1", { signal: "positive" });
    expect(fb.status).toBe("success");
    expect(mockRequest).toHaveBeenCalledWith("POST", "/memories/m1/feedback", {
      signal: "positive",
      user_correction: undefined,
      penalty: 0.5,
    });

    const ruleRes = await client.addRule({ userId: "u1", rule: "Always respond in concise bullet points" });
    expect(ruleRes.status).toBe("success");
    expect(mockRequest).toHaveBeenCalledWith("POST", "/observations", expect.objectContaining({
      user_id: "u1",
      metadata: expect.objectContaining({ memory_type: "procedural" }),
    }));

    const invRes = await client.investigate({ userId: "u1", queryText: "What stack did we use earlier?" });
    expect(invRes.status).toBe("success");
    expect(mockRequest).toHaveBeenCalledWith("POST", "/retrieve/investigate", expect.objectContaining({
      query_text: "What stack did we use earlier?",
      user_id: "u1",
    }));

    const refRes = await client.reflect({ userId: "u1" });
    expect(refRes.status).toBe("success");
    expect(mockRequest).toHaveBeenCalledWith("POST", "/memories/reflect", expect.objectContaining({
      user_id: "u1",
      apply_supersession: true,
    }));
  });
});
