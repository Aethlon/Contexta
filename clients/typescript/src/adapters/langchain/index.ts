import { Contexta, contextaError } from "@contexta/client";
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
 *   const history = new contextaChatHistory(contextaClient, userId, organizationId, "session-uuid");
 *   const chain = new RunnableWithMessageHistory({ runnable: llm, getMessageHistory: () => history });
 */
export class contextaChatHistory extends BaseChatMessageHistory {
  lc_namespace = ["contexta", "langchain"];

  private client: Contexta;
  private userId: string;
  private organizationId: string;
  private sessionId: string;
  private tokenBudget?: number;
  private buffer: BaseMessage[] = [];

  constructor(
    client: Contexta,
    userId: string,
    organizationId: string,
    sessionId: string,
    tokenBudget?: number,
  ) {
    super();
    this.client = client;
    this.userId = userId;
    this.organizationId = organizationId || client.organizationId || "";
    this.sessionId = sessionId;
    this.tokenBudget = tokenBudget;
  }

  async getMessages(): Promise<BaseMessage[]> {
    try {
      const ctx = await this.client.context({
        userId: this.userId,
        organizationId: this.organizationId,
        sessionId: this.sessionId,
        tokenBudget: this.tokenBudget,
      });
      const memoryMessages: BaseMessage[] = [];
      if (ctx.userProfile) {
        memoryMessages.push(new SystemMessage(`User: ${JSON.stringify(ctx.userProfile)}`));
      }
      for (const pref of ctx.preferences ?? []) {
        memoryMessages.push(new SystemMessage(`Preference: ${JSON.stringify(pref)}`));
      }
      for (const goal of ctx.goals ?? []) {
        memoryMessages.push(new SystemMessage(`Goal: ${JSON.stringify(goal)}`));
      }
      for (const mem of ctx.relevantMemories ?? []) {
        memoryMessages.push(new SystemMessage(`[Memory] ${mem.memory?.title}: ${mem.memory?.content}`));
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
      await this.client.observe({ userId: this.userId, sessionId: this.sessionId, messages: raw });
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
