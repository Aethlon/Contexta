import { contexta, contextaError, type Context } from "@contexta/client";

/**
 * Options for configuring contextaMemory for Anthropic Claude SDK.
 */
export interface contextaMemoryOptions {
  tokenBudget?: number;
}

/**
 * Anthropic-focused memory wrapper around the contexta base SDK.
 *
 * Provides context fetching and observation recording for Claude conversations.
 *
 * Usage:
 *   const memory = new contextaMemory(contextaClient, { tokenBudget: 2000 });
 *   const ctx = await memory.contextFor("session-uuid");
 *   await memory.observe("session-uuid", [{ role: "user", content: "Hello" }]);
 */
export class contextaMemory {
  private client: contexta;
  private tokenBudget?: number;

  constructor(client: contexta, options: contextaMemoryOptions = {}) {
    this.client = client;
    this.tokenBudget = options.tokenBudget;
  }

  async contextFor(sessionId: string): Promise<{ role: string; content: string }[]> {
    try {
      const ctx = await this.client.context({
        session_id: sessionId,
        token_budget: this.tokenBudget,
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
      await this.client.observe({ session_id: sessionId, messages });
    } catch (err) {
      console.error(`contexta observe failed for session ${sessionId}`, err);
    }
  }

  private formatContext(ctx: Context): { role: string; content: string }[] {
    const blocks: { role: string; content: string }[] = [];
    if (ctx.user_profile?.name) {
      blocks.push({ role: "user", content: `User: ${ctx.user_profile.name}` });
    }
    for (const pref of ctx.preferences ?? []) {
      blocks.push({ role: "user", content: `Preference: ${pref.category}=${pref.value}` });
    }
    for (const goal of ctx.goals ?? []) {
      blocks.push({ role: "user", content: `Goal: ${goal.description}` });
    }
    for (const mem of ctx.relevant_memories ?? []) {
      blocks.push({ role: "assistant", content: `[Memory] ${mem.title}: ${mem.content}` });
    }
    return blocks;
  }
}
