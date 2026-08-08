import { contexta, contextaError } from "@contexta/client";
import type { BaseMessage } from "@langchain/core/messages";
import { BaseChatMessageHistory } from "@langchain/core/chat_history";
import {
  HumanMessage,
  AIMessage,
  SystemMessage,
} from "@langchain/core/messages";

/**
 * LangChain chat message history backed by contexta's persistent store.
 *
 * Works as a drop-in with RunnableWithMessageHistory.
 *
 * Usage:
 *   const history = new contextaChatHistory(contextaClient, "session-uuid");
 *   const chain = new RunnableWithMessageHistory({ runnable: llm, getMessageHistory: () => history });
 */
export class contextaChatHistory extends BaseChatMessageHistory {
  lc_namespace = ["contexta", "langchain"];

  private client: contexta;
  private sessionId: string;
  private tokenBudget?: number;
  private buffer: BaseMessage[] = [];

  constructor(client: contexta, sessionId: string, tokenBudget?: number) {
    super();
    this.client = client;
    this.sessionId = sessionId;
    this.tokenBudget = tokenBudget;
  }

  async getMessages(): Promise<BaseMessage[]> {
    try {
      const ctx = await this.client.context({
        session_id: this.sessionId,
        token_budget: this.tokenBudget,
      });
      const memoryMessages: BaseMessage[] = [];
      if (ctx.user_profile?.name) {
        memoryMessages.push(new SystemMessage(`User: ${ctx.user_profile.name}`));
      }
      for (const pref of ctx.preferences ?? []) {
        memoryMessages.push(new SystemMessage(`Preference: ${pref.category}=${pref.value}`));
      }
      for (const goal of ctx.goals ?? []) {
        memoryMessages.push(new SystemMessage(`Goal: ${goal.description}`));
      }
      for (const mem of ctx.relevant_memories ?? []) {
        memoryMessages.push(new SystemMessage(`[Memory] ${mem.title}: ${mem.content}`));
      }
      return [...memoryMessages, ...this.buffer];
    } catch {
      return this.buffer;
    }
  }

  async addMessage(message: BaseMessage): Promise<void> {
    this.buffer.push(message);
  }

  async addUserMessage(message: string): Promise<void> {
    await this.addMessage(new HumanMessage(message));
  }

  async addAIMessage(message: string): Promise<void> {
    await this.addMessage(new AIMessage(message));
  }

  async clear(): Promise<void> {
    this.buffer = [];
  }

  async flush(): Promise<void> {
    if (this.buffer.length === 0) return;
    const raw = this.buffer.map((m) => ({
      role: this.inferRole(m),
      content: typeof m.content === "string" ? m.content : JSON.stringify(m.content),
    }));
    try {
      await this.client.observe({ session_id: this.sessionId, messages: raw });
    } catch (err) {
      console.error("contexta flush failed", err);
    }
    this.buffer = [];
  }

  private inferRole(message: BaseMessage): string {
    if (message instanceof HumanMessage) return "user";
    if (message instanceof AIMessage) return "assistant";
    if (message instanceof SystemMessage) return "system";
    return "user";
  }
}
