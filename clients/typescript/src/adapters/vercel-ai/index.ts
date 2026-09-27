import { Contexta, contextaError } from "@contexta/client";

/**
 * Options for the contexta Vercel AI SDK integration.
 */
export interface contextaVercelOptions {
  userId: string;
  organizationId?: string;
  tokenBudget?: number;
}

/**
 * Creates a contexta memory object that hooks into the Vercel AI SDK's
 * onFinish callback and streamText.
 *
 * Usage:
 *   import { streamText } from "ai";
 *   const mem = contextaMemory(contextaClient, { userId, tokenBudget: 2000 });
 *
 *   const result = await streamText({
 *     model: openai("gpt-4"),
 *     messages: [...(await mem.buildSystemMessages("session-uuid")), ...userMessages],
 *     onFinish: async ({ messages }) => {
 *       await mem.observe("session-uuid", messages);
 *     },
 *   });
 */
export function contextaMemory(
  client: Contexta,
  options: contextaVercelOptions,
) {
  const tokenBudget = options.tokenBudget;
  const userId = options.userId;
  const organizationId = options.organizationId || client.organizationId || "";

  async function buildSystemMessages(
    sessionId: string,
  ): Promise<{ role: "system"; content: string }[]> {
    try {
      const ctx = await client.context({
        userId,
        organizationId,
        sessionId,
        tokenBudget,
      });
      const parts: string[] = [];
      if (ctx.userProfile) {
        parts.push(`User Profile: ${JSON.stringify(ctx.userProfile)}`);
      }
      for (const pref of ctx.preferences ?? []) {
        parts.push(`Preference: ${JSON.stringify(pref)}`);
      }
      for (const goal of ctx.goals ?? []) {
        parts.push(`Goal: ${JSON.stringify(goal)}`);
      }
      for (const proj of ctx.activeProjects ?? []) {
        parts.push(`Active Project: ${JSON.stringify(proj)}`);
      }
      for (const mem of ctx.relevantMemories ?? []) {
        parts.push(`[Memory] ${mem.memory?.title}: ${mem.memory?.content}`);
      }
      return parts.length > 0
        ? [{ role: "system" as const, content: parts.join("\n") }]
        : [];
    } catch (err) {
      if (err instanceof contextaError) {
        console.warn("contexta context fetch failed", err.message);
      }
      return [];
    }
  }

  async function observe(
    sessionId: string,
    messages: { role: string; content: string }[],
  ): Promise<void> {
    if (messages.length === 0) return;
    try {
      await client.observe({ userId, sessionId, messages });
    } catch (err) {
      console.error("contexta observe failed", err);
    }
  }

  return { buildSystemMessages, observe };
}

export type contextaMemory = ReturnType<typeof contextaMemory>;
