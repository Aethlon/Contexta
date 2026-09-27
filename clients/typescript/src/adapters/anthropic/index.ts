import { Contexta, contextaError, type Context } from "@contexta/client";

/**
 * Options for configuring contextaMemory for Anthropic Claude SDK.
 */
export interface contextaMemoryOptions {
  userId: string;
  organizationId?: string;
  tokenBudget?: number;
}

/**
 * Anthropic-focused memory wrapper around the contexta base SDK.
 *
 * Provides context fetching and observation recording for Claude conversations.
 *
 * Usage:
 *   const memory = new contextaMemory(contextaClient, { userId, tokenBudget: 2000 });
 *   const ctx = await memory.contextFor("session-uuid");
 *   await memory.observe("session-uuid", [{ role: "user", content: "Hello" }]);
 */
export class contextaMemory {
  private client: Contexta;
  private userId: string;
  private organizationId: string;
  private tokenBudget?: number;

  constructor(client: Contexta, options: contextaMemoryOptions) {
    this.client = client;
    this.userId = options.userId;
    this.organizationId = options.organizationId ?? client.organizationId ?? "";
    this.tokenBudget = options.tokenBudget;
  }

  async contextFor(sessionId: string): Promise<{ role: string; content: string }[]> {
    try {
      const ctx = await this.client.context({
        userId: this.userId,
        organizationId: this.organizationId,
        sessionId,
        tokenBudget: this.tokenBudget,
      });
      return this.formatContext(ctx);
    } catch (err) {
      if (err instanceof contextaError) {
        console.warn(`contexta context unavailable: ${err.message}`);
      }
      return [];
    }
  }

  async observe(sessionId: string, messages: { role: string; content: string }[]): Promise<void> {
    if (messages.length === 0) return;
    try {
      await this.client.observe({ userId: this.userId, sessionId, messages });
    } catch (err) {
      console.error(`contexta observe failed for session ${sessionId}`, err);
    }
  }

  private formatContext(ctx: Context): { role: string; content: string }[] {
    const blocks: { role: string; content: string }[] = [];
    if (ctx.userProfile) {
      blocks.push({ role: "user", content: `User: ${JSON.stringify(ctx.userProfile)}` });
    }
    for (const pref of ctx.preferences ?? []) {
      blocks.push({ role: "user", content: `Preference: ${JSON.stringify(pref)}` });
    }
    for (const goal of ctx.goals ?? []) {
      blocks.push({ role: "user", content: `Goal: ${JSON.stringify(goal)}` });
    }
    for (const mem of ctx.relevantMemories ?? []) {
      blocks.push({ role: "assistant", content: `[Memory] ${mem.memory?.title}: ${mem.memory?.content}` });
    }
    return blocks;
  }
}
