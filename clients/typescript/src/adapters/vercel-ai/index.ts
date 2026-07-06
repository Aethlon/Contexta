import { contexta, contextaError } from "@contexta/client";

/**
 * Options for the contexta Vercel AI SDK integration.
 */
export interface contextaVercelOptions {
  tokenBudget?: number;
}

/**
 * Creates a contexta memory object that hooks into the Vercel AI SDK's
 * onFinish callback and streamText.
 *
 * Usage:
 *   import { streamText } from "ai";
 *   const mem = contextaMemory(contextaClient, { tokenBudget: 2000 });
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
  client: contexta,
  options: contextaVercelOptions = {},
) {
  const tokenBudget = options.tokenBudget;

  async function buildSystemMessages(
    sessionId: string,
  ): Promise<{ role: "system"; content: string }[]> {
    try {
      const ctx = await client.context({
        session_id: sessionId,
        token_budget: tokenBudget,
      });
      const parts: string[] = [];
      if (ctx.user_profile?.name) {
        parts.push(`User Profile: ${ctx.user_profile.name}`);
      }
      for (const pref of ctx.preferences ?? []) {
        parts.push(`Preference: ${pref.category}=${pref.value}`);
      }
      for (const goal of ctx.goals ?? []) {
        parts.push(`Goal: ${goal.description}`);
      }
      for (const proj of ctx.active_projects ?? []) {
        parts.push(`Active Project: ${proj.name}`);
      }
      for (const mem of ctx.relevant_memories ?? []) {
        parts.push(`[Memory] ${mem.title}: ${mem.content}`);
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
      await client.observe({ session_id: sessionId, messages });
    } catch (err) {
      console.error("contexta observe failed", err);
    }
  }

  return { buildSystemMessages, observe };
}

export type contextaMemory = ReturnType<typeof contextaMemory>;
