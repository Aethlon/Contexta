import { contexta, contextaError, type Context } from "@contexta/client";
import OpenAI from "openai";
import type {
  Assistant,
  AssistantTool,
  Thread,
  ThreadMessage,
  Run,
} from "openai/resources/beta/index";

/**
 * Options for configuring contextaMemory.
 */
export interface contextaMemoryOptions {
  tokenBudget?: number;
  autoBatchSize?: number;
}

/**
 * Fetches contexta context and formats it for injection into an assistant thread.
 */
export class contextaMemory {
  private client: contexta;
  private tokenBudget?: number;
  private autoBatchSize: number;

  constructor(client: contexta, options: contextaMemoryOptions = {}) {
    this.client = client;
    this.tokenBudget = options.tokenBudget;
    this.autoBatchSize = options.autoBatchSize ?? 10;
  }

  async buildSystemMessage(sessionId: string): Promise<string> {
    try {
      const ctx = await this.client.context({
        session_id: sessionId,
        token_budget: this.tokenBudget,
      });
      return this.formatContext(ctx);
    } catch (err) {
      if (err instanceof contextaError) {
        console.warn(`contexta context fetch failed: ${err.message}`);
      }
      return "";
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

  async observeThread(sessionId: string, threadMessages: ThreadMessage[]): Promise<void> {
    const extracted = threadMessages.map((m) => ({
      role: m.role,
      content: m.content
        .filter((b) => b.type === "text")
        .map((b) => (b as any).text?.value ?? "")
        .join("\n"),
    }));
    await this.observe(sessionId, extracted);
  }

  private formatContext(ctx: Context): string {
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
    return parts.join("\n");
  }
}

/**
 * Drop-in runner that injects contexta context before each user turn and
 * observes thread content after each run completes.
 */
export class contextaAssistantRunner {
  private openai: OpenAI;
  private memory: contextaMemory;
  private autoObserve: boolean;
  private sessionThreadMap: Map<string, string> = new Map();

  constructor(
    openaiClient: OpenAI,
    memory: contextaMemory,
    autoObserve = true,
  ) {
    this.openai = openaiClient;
    this.memory = memory;
    this.autoObserve = autoObserve;
  }

  async runWithSession(
    assistantId: string,
    sessionId: string,
    userMessage: string,
    threadId?: string,
    runOptions?: Omit<OpenAI.Beta.Threads.RunCreateParams, "assistant_id" | "thread_id">,
  ): Promise<Run> {
    const tid = threadId ?? await this.getOrCreateThread(sessionId);

    const context = await this.memory.buildSystemMessage(sessionId);
    if (context) {
      await this.openai.beta.threads.messages.create(tid, {
        role: "user",
        content: `[contexta Context]\n${context}`,
      });
    }

    await this.openai.beta.threads.messages.create(tid, {
      role: "user",
      content: userMessage,
    });

    const run = await this.openai.beta.threads.runs.createAndPoll(tid, {
      assistant_id: assistantId,
      ...runOptions,
    });

    if (this.autoObserve && run.status === "completed") {
      const messages = await this.openai.beta.threads.messages.list(tid);
      await this.memory.observeThread(sessionId, messages.data);
    }

    return run;
  }

  private async getOrCreateThread(sessionId: string): Promise<string> {
    const existing = this.sessionThreadMap.get(sessionId);
    if (existing) return existing;
    const thread = await this.openai.beta.threads.create();
    this.sessionThreadMap.set(sessionId, thread.id);
    return thread.id;
  }
}
