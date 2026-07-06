import type { Context, ScoredMemory, TokenUsage } from "./types.js";

export class ContextResult {
  public userProfile: Context["userProfile"];
  public activeProjects: Context["activeProjects"];
  public preferences: Context["preferences"];
  public goals: Context["goals"];
  public recentEvents: Context["recentEvents"];
  public relevantMemories: Context["relevantMemories"];
  public tokenUsage: TokenUsage;
  public cacheHit: boolean;
  public requestId: string;

  constructor(data: Context) {
    this.userProfile = data.userProfile;
    this.activeProjects = data.activeProjects;
    this.preferences = data.preferences;
    this.goals = data.goals;
    this.recentEvents = data.recentEvents;
    this.relevantMemories = data.relevantMemories;
    this.tokenUsage = data.tokenUsage;
    this.cacheHit = data.cacheHit;
    this.requestId = data.requestId;
  }

  toSystemPrompt(): string {
    const sections: string[] = [];

    if (this.userProfile) {
      sections.push(`[User Profile]\n${this.userProfile.summary ?? JSON.stringify(this.userProfile.traits ?? {})}`);
    }

    if (this.activeProjects.length > 0) {
      sections.push(`[Active Projects]\n${this.activeProjects.map((p) => `- ${p.name}: ${p.description ?? ""}`).join("\n")}`);
    }

    if (this.preferences.length > 0) {
      sections.push(`[Preferences]\n${this.preferences.map((p) => `- ${p.key}: ${JSON.stringify(p.value)}`).join("\n")}`);
    }

    if (this.goals.length > 0) {
      sections.push(`[Goals]\n${this.goals.map((g) => `- ${g.description} (${g.status ?? "active"})`).join("\n")}`);
    }

    if (this.recentEvents.length > 0) {
      sections.push(`[Recent Events]\n${this.recentEvents.map((e) => `- [${e.type}] ${e.description}`).join("\n")}`);
    }

    if (this.relevantMemories.length > 0) {
      sections.push(`[Relevant Memories]\n${this.relevantMemories.map((m) => `- (score: ${m.score.toFixed(3)}) ${m.memory.title}: ${m.memory.content}`).join("\n")}`);
    }

    sections.push(`[Token Usage]\nTotal: ${this.tokenUsage.total}`);

    return sections.join("\n\n");
  }

  toMessages(): Array<{ role: string; content: string }> {
    const messages: Array<{ role: string; content: string }> = [];

    if (this.userProfile) {
      messages.push({
        role: "system",
        content: `User profile: ${this.userProfile.summary ?? JSON.stringify(this.userProfile.traits ?? {})}`,
      });
    }

    if (this.activeProjects.length > 0) {
      messages.push({
        role: "system",
        content: `Active projects: ${this.activeProjects.map((p) => p.name).join(", ")}`,
      });
    }

    if (this.preferences.length > 0) {
      messages.push({
        role: "system",
        content: `User preferences: ${this.preferences.map((p) => `${p.key}=${JSON.stringify(p.value)}`).join(", ")}`,
      });
    }

    if (this.goals.length > 0) {
      messages.push({
        role: "system",
        content: `User goals: ${this.goals.map((g) => g.description).join("; ")}`,
      });
    }

    if (this.recentEvents.length > 0) {
      messages.push({
        role: "system",
        content: `Recent events: ${this.recentEvents.map((e) => `[${e.type}] ${e.description}`).join(" | ")}`,
      });
    }

    if (this.relevantMemories.length > 0) {
      messages.push({
        role: "system",
        content: `Relevant memories:\n${this.relevantMemories.map((m) => `[score: ${m.score.toFixed(3)}] ${m.memory.title}: ${m.memory.content}`).join("\n")}`,
      });
    }

    return messages;
  }

  toMarkdown(): string {
    const sections: string[] = [];

    sections.push("# Memory Context\n");

    if (this.userProfile) {
      sections.push("## User Profile\n");
      sections.push(`${this.userProfile.summary ?? JSON.stringify(this.userProfile.traits ?? {})}\n");
    }

    if (this.activeProjects.length > 0) {
      sections.push("## Active Projects\n");
      for (const p of this.activeProjects) {
        sections.push(`### ${p.name}\n${p.description ?? ""}\n`);
      }
    }

    if (this.preferences.length > 0) {
      sections.push("## Preferences\n");
      sections.push("| Key | Value |\n|-----|-------|\n");
      for (const p of this.preferences) {
        sections.push(`| ${p.key} | ${JSON.stringify(p.value)} |\n`);
      }
      sections.push("\n");
    }

    if (this.goals.length > 0) {
      sections.push("## Goals\n");
      for (const g of this.goals) {
        sections.push(`- ${g.description} (${g.status ?? "active"})\n`);
      }
      sections.push("\n");
    }

    if (this.recentEvents.length > 0) {
      sections.push("## Recent Events\n");
      for (const e of this.recentEvents) {
        sections.push(`- **${e.type}**: ${e.description}\n`);
      }
      sections.push("\n");
    }

    if (this.relevantMemories.length > 0) {
      sections.push("## Relevant Memories\n");
      for (const m of this.relevantMemories) {
        sections.push(`### ${m.memory.title}\n- Score: ${m.score.toFixed(3)}\n- ${m.memory.content}\n\n`);
      }
    }

    sections.push(`---\n*Token usage: ${this.tokenUsage.total}*`);

    return sections.join("");
  }

  toDict(): Context {
    return {
      userProfile: this.userProfile,
      activeProjects: this.activeProjects,
      preferences: this.preferences,
      goals: this.goals,
      recentEvents: this.recentEvents,
      relevantMemories: this.relevantMemories,
      tokenUsage: this.tokenUsage,
      cacheHit: this.cacheHit,
      requestId: this.requestId,
    };
  }
}
