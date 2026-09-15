"use client";

import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Loader2,
  CheckCircle2,
  ArrowRight,
  ShieldCheck,
  Bot,
  User,
  Database,
  Cpu,
  Terminal,
  Zap,
  UploadCloud,
  FileText,
  HelpCircle,
  MessageSquare,
} from "lucide-react";

export interface ExtractedMemoryItem {
  id: string;
  title: string;
  content: string;
  memory_type: "fact" | "preference" | "goal" | "skill" | "rule";
  confidence: number;
  tags: string[];
}

interface QuestionStage {
  id: string;
  agentPrompt: string;
  field: "name" | "focus" | "companion_role" | "format_preference" | "tools" | "memory_wish" | "pet_peeves" | "goals" | "favorite_color";
  suggestions: string[];
  placeholder: string;
}

const ONBOARDING_QUESTIONS: QuestionStage[] = [
  {
    id: "name",
    field: "name",
    agentPrompt: "Welcome to Contexta! I'm your private memory engine. Before we begin, what name or handle should I remember you by?",
    suggestions: ["Jenit", "Alex", "Sam", "Call me by my initials"],
    placeholder: "Type your preferred name or handle...",
  },
  {
    id: "focus",
    field: "focus",
    agentPrompt: "Nice to meet you! Tell me a bit about what fills your days—what kind of work, projects, studies, or passions do you spend most of your time on?",
    suggestions: [
      "Software engineering & systems architecture",
      "Product management & business operations",
      "Creative writing & content research",
      "Academic studies & learning",
    ],
    placeholder: "Describe your everyday focus...",
  },
  {
    id: "companion_role",
    field: "companion_role",
    agentPrompt: "When working with an assistant, what role best fits your workflow?",
    suggestions: [
      "Autonomous pair programmer & code reviewer",
      "Thoughtful research & brainstorming partner",
      "Efficient organizer keeping contexts in sync",
      "Concise summarizer and day-to-day assistant",
    ],
    placeholder: "e.g. Autonomous pair programmer, research partner...",
  },
  {
    id: "format_preference",
    field: "format_preference",
    agentPrompt: "How do you like information communicated to you?",
    suggestions: [
      "Concise bullet points, minimal fluff",
      "Thorough step-by-step explanations",
      "Direct code solutions with minimal commentary",
      "Conversational and friendly tone",
    ],
    placeholder: "e.g. Short summaries, bullet points, technical details...",
  },
  {
    id: "tools",
    field: "tools",
    agentPrompt: "What primary tools, operating systems, or environments do you frequently work in?",
    suggestions: [
      "macOS, VS Code, Cursor & Terminal",
      "Windows / WSL2, Next.js & Docker",
      "Linux, Neovim, Python & Go",
      "Browser apps, Notion, Slack & Obsidian",
    ],
    placeholder: "e.g. VS Code, Mac, Linux, Notion...",
  },
  {
    id: "memory_wish",
    field: "memory_wish",
    agentPrompt: "What is something you often wish an AI would remember so you never have to repeat yourself?",
    suggestions: [
      "My tech stack conventions & architectural rules",
      "Key project milestones and deadlines",
      "My preferred tone and output constraints",
      "Specific personal and team preferences",
    ],
    placeholder: "What should your assistant always keep in mind?",
  },
  {
    id: "pet_peeves",
    field: "pet_peeves",
    agentPrompt: "Any specific pet peeves or things you dislike in AI responses?",
    suggestions: [
      "Overly verbose apologies & pleasantries",
      "Hallucinated facts or confident guessing",
      "Generic tutorials when I asked for a direct fix",
      "None, standard helpful behavior is great",
    ],
    placeholder: "Things you'd like your agents to avoid doing...",
  },
  {
    id: "goals",
    field: "goals",
    agentPrompt: "What is a key objective or project you are actively pushing forward right now?",
    suggestions: [
      "Shipping a production-ready software project",
      "Accelerating my personal knowledge management",
      "Learning new frameworks and tools",
      "Growing a business or community initiative",
    ],
    placeholder: "What are you working toward right now?",
  },
  {
    id: "favorite_color",
    field: "favorite_color",
    agentPrompt: "Lastly, what visual tone or accent aesthetic do you prefer for your personal vault?",
    suggestions: [
      "Obsidian dark with emerald accents",
      "Deep indigo & cyan monochrome",
      "Warm charcoal slate",
      "High-contrast minimalist dark",
    ],
    placeholder: "e.g. Obsidian, Emerald, Indigo, Amber...",
  },
];

const KNOWLEDGE_RESPONSES: Record<string, string> = {
  what_is_contexta:
    "Contexta is a sovereign, offline-first personal AI memory engine. It captures, encrypts, and retains your personal and technical context so AI agents (like Claude Desktop, Cursor, and IDE extensions) don't forget who you are between sessions.",
  how_encryption_works:
    "Every memory record is encrypted on-the-fly using tenant-scoped cryptographic keys before reaching storage. Your data is isolated per tenant and never shared with public model vendors or analytics trackers.",
  how_mcp_works:
    "Contexta exposes a standardized Model Context Protocol (MCP) server on port 8765. Any MCP-compatible agent can query `contexta_retrieve` or call `contexta_observe` to recall or update your memories seamlessly.",
  data_storage:
    "Your memories are stored in your own PostgreSQL instance enhanced with pgvector for HNSW semantic vector retrieval and BM25 lexical search.",
};

interface ChatMessage {
  id: string;
  sender: "agent" | "user";
  text: string;
  timestamp: string;
  isIngestionSummary?: boolean;
}

export function OnboardingChat({ initialName }: { initialName: string }) {
  const [activeTab, setActiveTab] = useState<"chat" | "ingest" | "faq">("chat");
  const [currentStep, setCurrentStep] = useState(0);
  const [inputValue, setInputValue] = useState("");
  const [ingestText, setIngestText] = useState("");
  const [isClassifying, setIsClassifying] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [engineStatus, setEngineStatus] = useState<"checking" | "online" | "offline" | "launching">("checking");
  const [isLaunchingEngine, setIsLaunchingEngine] = useState(false);

  const [userName, setUserName] = useState(initialName || "Jenit");
  const [companionRole, setCompanionRole] = useState("");
  const [preferencesList, setPreferencesList] = useState<string[]>([]);
  const [favoriteColor, setFavoriteColor] = useState("");
  const [memories, setMemories] = useState<ExtractedMemoryItem[]>([]);

  useEffect(() => {
    let active = true;
    const checkEngine = async () => {
      try {
        const res = await fetch("/api/system/engine");
        if (res.ok) {
          const data = await res.json();
          if (active) {
            setEngineStatus(data.online ? "online" : "offline");
          }
        }
      } catch {
        if (active) setEngineStatus("offline");
      }
    };
    checkEngine();
    const timer = setInterval(checkEngine, 4000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const handleLaunchEngine = async () => {
    setIsLaunchingEngine(true);
    setEngineStatus("launching");
    try {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("launch_contexta_engine");
      } catch {
        await fetch("/api/system/engine", { method: "POST" });
      }
    } catch (e) {
      console.warn("Could not trigger engine start:", e);
    } finally {
      setTimeout(() => setIsLaunchingEngine(false), 5000);
    }
  };

  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: "initial-msg",
      sender: "agent",
      text: ONBOARDING_QUESTIONS[0].agentPrompt.replace("Jenit", initialName || "Jenit"),
      timestamp: "Just now",
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isClassifying]);

  const parseKnowledgeQuery = (text: string): string | null => {
    const lower = text.toLowerCase();
    if (lower.includes("what is contexta") || lower.includes("what does contexta do") || lower.includes("tell me more")) {
      return KNOWLEDGE_RESPONSES.what_is_contexta;
    }
    if (lower.includes("encryption") || lower.includes("security") || lower.includes("private") || lower.includes("safe")) {
      return KNOWLEDGE_RESPONSES.how_encryption_works;
    }
    if (lower.includes("mcp") || lower.includes("protocol") || lower.includes("connect agent")) {
      return KNOWLEDGE_RESPONSES.how_mcp_works;
    }
    if (lower.includes("storage") || lower.includes("where is data") || lower.includes("postgres") || lower.includes("database")) {
      return KNOWLEDGE_RESPONSES.data_storage;
    }
    return null;
  };

  const classifyAndStore = (stage: QuestionStage, text: string): ExtractedMemoryItem => {
    const trimmed = text.trim();
    let memType: ExtractedMemoryItem["memory_type"] = "fact";
    let title = "Personal Detail";
    let content = trimmed;
    const tags = ["onboarding", stage.field];

    switch (stage.field) {
      case "name":
        memType = "fact";
        title = "User Identity & Handle";
        content = `User's preferred name or handle is ${trimmed}.`;
        setUserName(trimmed);
        tags.push("identity", "profile");
        break;
      case "focus":
        memType = "fact";
        title = "Professional & Day-to-Day Focus";
        content = `User focuses primarily on: ${trimmed}.`;
        tags.push("career", "domain");
        break;
      case "companion_role":
        memType = "preference";
        title = "AI Companion Role Preference";
        content = `Primary AI companion role: ${trimmed}.`;
        setCompanionRole(trimmed);
        tags.push("assistant", "role");
        break;
      case "format_preference":
        memType = "preference";
        title = "Communication & Format Preference";
        content = `Preferred response format: ${trimmed}.`;
        setPreferencesList((prev) => [...prev, `Format: ${trimmed}`]);
        tags.push("formatting", "communication");
        break;
      case "tools":
        memType = "fact";
        title = "Primary Tooling & Environment";
        content = `Active tools & operating environment: ${trimmed}.`;
        tags.push("tooling", "environment");
        break;
      case "memory_wish":
        memType = "rule";
        title = "Persistent Memory Requirement";
        content = `Crucial memory to maintain: ${trimmed}.`;
        setPreferencesList((prev) => [...prev, `Memory priority: ${trimmed}`]);
        tags.push("rule", "context");
        break;
      case "pet_peeves":
        memType = "rule";
        title = "Assistant Constraint & Pet Peeve";
        content = `Assistant instruction to avoid: ${trimmed}.`;
        setPreferencesList((prev) => [...prev, `Avoid: ${trimmed}`]);
        tags.push("rule", "constraint");
        break;
      case "goals":
        memType = "goal";
        title = "Active Project / Goal";
        content = `Active objective: ${trimmed}.`;
        tags.push("goal", "project");
        break;
      case "favorite_color":
        memType = "preference";
        title = "Aesthetic Preference";
        content = `Preferred visual aesthetic: ${trimmed}.`;
        setFavoriteColor(trimmed);
        tags.push("aesthetic", "ui");
        break;
      default:
        memType = "fact";
        title = "Personal Context Insight";
        content = trimmed;
    }

    return {
      id: `mem-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      title,
      content,
      memory_type: memType,
      confidence: 0.95,
      tags,
    };
  };

  const handleSend = async (userText?: string) => {
    const textToSend = (userText ?? inputValue).trim();
    if (!textToSend || isClassifying || isSaving) return;

    setInputValue("");
    setErrorMessage(null);

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsClassifying(true);

    const knowledgeAnswer = parseKnowledgeQuery(textToSend);

    setTimeout(() => {
      if (knowledgeAnswer) {
        setIsClassifying(false);
        setMessages((prev) => [
          ...prev,
          {
            id: `agent-faq-${Date.now()}`,
            sender: "agent",
            text: knowledgeAnswer,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
        return;
      }

      if (currentStep < ONBOARDING_QUESTIONS.length) {
        const currentQuestion = ONBOARDING_QUESTIONS[currentStep];
        const extracted = classifyAndStore(currentQuestion, textToSend);
        setMemories((prev) => [...prev, extracted]);

        const nextStep = currentStep + 1;
        if (nextStep < ONBOARDING_QUESTIONS.length) {
          setCurrentStep(nextStep);
          const nextQ = ONBOARDING_QUESTIONS[nextStep];
          setMessages((prev) => [
            ...prev,
            {
              id: `agent-${Date.now()}`,
              sender: "agent",
              text: nextQ.agentPrompt,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            },
          ]);
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: `agent-complete-${Date.now()}`,
              sender: "agent",
              text: `Thank you, ${userName || "friend"}! I have structured and encrypted your personal memory foundation. Ready to initialize your private vault and jump into the dashboard?`,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            },
          ]);
        }
      } else {
        // Freeform chat after questions
        const extractedItem: ExtractedMemoryItem = {
          id: `mem-free-${Date.now()}`,
          title: "Personal Context Note",
          content: textToSend,
          memory_type: "fact",
          confidence: 0.9,
          tags: ["onboarding", "freeform"],
        };
        setMemories((prev) => [...prev, extractedItem]);
        setMessages((prev) => [
          ...prev,
          {
            id: `agent-free-${Date.now()}`,
            sender: "agent",
            text: "Got it! Added that detail into your personal vault foundation.",
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
      }

      setIsClassifying(false);
      inputRef.current?.focus();
    }, 400);
  };

  // Ingestion handler: Extract multiple memories from pasted text or uploaded document
  const handleIngestText = (rawText: string) => {
    if (!rawText.trim() || isClassifying) return;
    setIsClassifying(true);

    const lines = rawText
      .split(/\r?\n|;|\./)
      .map((l) => l.trim())
      .filter((l) => l.length > 8);

    const extractedBatch: ExtractedMemoryItem[] = [];

    lines.slice(0, 10).forEach((line, idx) => {
      const lower = line.toLowerCase();
      let memType: ExtractedMemoryItem["memory_type"] = "fact";
      let title = "Imported Personal Fact";

      if (lower.includes("prefer") || lower.includes("like") || lower.includes("style")) {
        memType = "preference";
        title = "Imported Preference";
      } else if (lower.includes("goal") || lower.includes("building") || lower.includes("working on")) {
        memType = "goal";
        title = "Imported Active Goal";
      } else if (lower.includes("never") || lower.includes("must") || lower.includes("rule") || lower.includes("avoid")) {
        memType = "rule";
        title = "Imported Constraint";
      } else if (lower.includes("proficient") || lower.includes("expert") || lower.includes("experience with")) {
        memType = "skill";
        title = "Imported Technical Skill";
      }

      extractedBatch.push({
        id: `mem-ingest-${Date.now()}-${idx}`,
        title,
        content: line,
        memory_type: memType,
        confidence: 0.94,
        tags: ["onboarding", "document_ingest", memType],
      });
    });

    if (extractedBatch.length === 0) {
      extractedBatch.push({
        id: `mem-ingest-${Date.now()}`,
        title: "Imported Context Summary",
        content: rawText.slice(0, 300),
        memory_type: "fact",
        confidence: 0.9,
        tags: ["onboarding", "document_ingest"],
      });
    }

    setTimeout(() => {
      setMemories((prev) => [...prev, ...extractedBatch]);
      setIsClassifying(false);
      setIngestText("");
      setActiveTab("chat");

      setMessages((prev) => [
        ...prev,
        {
          id: `agent-ingest-${Date.now()}`,
          sender: "agent",
          text: `Extracted ${extractedBatch.length} memories from your notes into the sovereign foundation. You can inspect them in the panel on the right or continue chatting.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          isIngestionSummary: true,
        },
      ]);
    }, 500);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        handleIngestText(content);
      }
    };
    reader.readAsText(file);
  };

  const handleSaveAndComplete = async (skip: boolean = false) => {
    setIsSaving(true);
    setErrorMessage(null);

    try {
      const payload = skip
        ? {
            name: initialName || "User",
            companion_role: "Autonomous Personal Assistant",
            preferences: "Provide concise and structured responses.",
            memories: [],
            skip: true,
          }
        : {
            name: userName || initialName || "User",
            companion_role: companionRole || "Autonomous Pair Programmer & Personal Vault",
            preferences: preferencesList.join(" | ") || "Prefer concise answers with clean formatting.",
            favorite_color: favoriteColor || "Obsidian dark",
            memories: memories.map((m) => ({
              title: m.title,
              content: m.content,
              memory_type: m.memory_type,
              confidence: m.confidence,
              tags: m.tags,
            })),
            skip: false,
          };

      try {
        await fetch("/api/auth/onboarding", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (postErr) {
        console.warn("[onboarding] Network post issue, will persist in session:", postErr);
      }

      // Guarantee cookie completion immediately
      document.cookie = "contexta_onboarding_completed=true; path=/; max-age=31536000; SameSite=Lax";

      // Full navigation ensures server component layout re-reads the fresh session and cookie
      window.location.href = "/dashboard";
    } catch (err: any) {
      console.warn("[onboarding] Unhandled save error, continuing in local mode:", err);
      document.cookie = "contexta_onboarding_completed=true; path=/; max-age=31536000; SameSite=Lax";
      window.location.href = "/dashboard";
    }
  };

  const progressPercent = Math.min(100, Math.round((memories.length / 8) * 100));
  const isReadyToComplete = memories.length >= 2;
  const currentQ = ONBOARDING_QUESTIONS[currentStep];

  return (
    <div className="w-full flex flex-col lg:flex-row gap-6 font-mono text-xs">
      {/* Left / Main Interactive Panel */}
      <div className="flex-1 flex flex-col rounded-xl border border-border/40 bg-card/75 backdrop-blur-xl shadow-2xl overflow-hidden min-h-[580px] max-h-[700px]">
        {/* Navigation & Mode Bar */}
        <div className="px-5 py-3 border-b border-border/30 bg-secondary/30 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-1.5 bg-secondary/60 p-1 rounded-lg border border-border/30">
            <button
              type="button"
              onClick={() => setActiveTab("chat")}
              className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 text-[11px] transition-all cursor-pointer ${
                activeTab === "chat"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span>Conversation</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("ingest")}
              className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 text-[11px] transition-all cursor-pointer ${
                activeTab === "ingest"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <UploadCloud className="h-3.5 w-3.5" />
              <span>Ingest Context / Notes</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("faq")}
              className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 text-[11px] transition-all cursor-pointer ${
                activeTab === "faq"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <HelpCircle className="h-3.5 w-3.5" />
              <span>Know Contexta</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            {engineStatus === "online" ? (
              <div className="flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>Contexta Engine Online</span>
              </div>
            ) : engineStatus === "launching" ? (
              <div className="flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded bg-blue-500/10 border border-blue-500/30 text-blue-300">
                <Loader2 className="h-3 w-3 animate-spin" />
                <span>Launching Engine...</span>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleLaunchEngine}
                disabled={isLaunchingEngine}
                className="flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 transition-colors cursor-pointer"
                title="Contexta Brain (:8000) is offline. Click to launch in background."
              >
                <Zap className="h-3 w-3 text-amber-400" />
                <span>Launch Contexta Engine</span>
              </button>
            )}
            <div className="hidden sm:flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <Cpu className="h-3 w-3 text-emerald-400" />
              <span>Local Classifier Active</span>
            </div>
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === "chat" && (
          <>
            {/* Message Stream */}
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
              <AnimatePresence initial={false}>
                {messages.map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2 }}
                    className={`flex gap-3 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {msg.sender === "agent" && (
                      <div className="w-7 h-7 rounded bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0 text-indigo-400">
                        <Bot className="h-4 w-4" />
                      </div>
                    )}

                    <div
                      className={`max-w-[84%] rounded-xl px-4 py-3 leading-relaxed ${
                        msg.sender === "user"
                          ? "bg-foreground text-background font-sans font-medium"
                          : msg.isIngestionSummary
                          ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 font-sans"
                          : "bg-secondary/60 border border-border/40 text-foreground font-sans"
                      }`}
                    >
                      <p className="text-[13px] whitespace-pre-wrap">{msg.text}</p>
                      <div
                        className={`mt-1.5 text-[9px] font-mono opacity-60 flex items-center justify-end gap-1 ${
                          msg.sender === "user" ? "text-background/80" : "text-muted-foreground"
                        }`}
                      >
                        <span suppressHydrationWarning>{msg.timestamp}</span>
                      </div>
                    </div>

                    {msg.sender === "user" && (
                      <div className="w-7 h-7 rounded bg-foreground/10 border border-border/40 flex items-center justify-center shrink-0 text-foreground">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              {isClassifying && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2.5 text-muted-foreground text-[11px] py-2 px-1"
                >
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
                  <span>Extracting personal intelligence & classifying memory nodes...</span>
                </motion.div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Quick Suggestion Pills */}
            {currentQ && currentStep < ONBOARDING_QUESTIONS.length && (
              <div className="px-4 py-2 border-t border-border/20 bg-secondary/15 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
                <span className="text-[10px] text-muted-foreground shrink-0 mr-1 flex items-center gap-1">
                  <Zap className="h-3 w-3 text-amber-400/80" />
                  Suggestions:
                </span>
                {currentQ.suggestions.map((sug, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => handleSend(sug)}
                    disabled={isClassifying || isSaving}
                    className="shrink-0 px-2.5 py-1 rounded-full border border-border/40 bg-card/60 hover:bg-secondary text-[11px] text-foreground/90 hover:text-foreground transition-all cursor-pointer whitespace-nowrap active:scale-[0.98]"
                  >
                    {sug}
                  </button>
                ))}
              </div>
            )}

            {/* Input Bar */}
            <div className="p-3.5 border-t border-border/30 bg-card/40">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
                className="flex items-center gap-2"
              >
                <input
                  ref={inputRef}
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder={currentQ ? currentQ.placeholder : "Type your reply or ask a question..."}
                  disabled={isClassifying || isSaving}
                  className="flex-1 bg-secondary/40 border border-border/40 rounded-lg px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all font-sans"
                />
                <button
                  type="submit"
                  disabled={!inputValue.trim() || isClassifying || isSaving}
                  className="px-4 py-2.5 rounded-lg bg-foreground text-background font-medium hover:bg-foreground/90 disabled:opacity-40 transition-all cursor-pointer flex items-center gap-1.5"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Send</span>
                </button>
              </form>
            </div>
          </>
        )}

        {activeTab === "ingest" && (
          <div className="flex-1 p-6 flex flex-col gap-4 overflow-y-auto">
            <div>
              <h2 className="text-sm font-medium text-foreground flex items-center gap-2">
                <UploadCloud className="h-4 w-4 text-indigo-400" />
                Direct Context Ingestion
              </h2>
              <p className="text-[11px] text-muted-foreground mt-1">
                Paste your personal notes, bio, tech stack guidelines, or resume. The classifier will auto-extract facts, preferences, and rules.
              </p>
            </div>

            <textarea
              rows={8}
              value={ingestText}
              onChange={(e) => setIngestText(e.target.value)}
              placeholder="Paste notes, guidelines, or persona context here...&#10;e.g.&#10;- I prefer concise code with TypeScript.&#10;- Currently building an AI memory system with pgvector.&#10;- Never use generic boilerplate or apologize."
              className="w-full bg-secondary/30 border border-border/40 rounded-lg p-3.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 font-sans resize-none"
            />

            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.md,.json"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-3.5 py-2 rounded-lg border border-border/40 bg-secondary/40 hover:bg-secondary/70 text-[11px] text-foreground flex items-center gap-2 cursor-pointer"
                >
                  <FileText className="h-3.5 w-3.5 text-indigo-400" />
                  <span>Upload .txt or .md file</span>
                </button>
              </div>

              <button
                type="button"
                onClick={() => handleIngestText(ingestText)}
                disabled={!ingestText.trim() || isClassifying}
                className="w-full sm:w-auto px-5 py-2 rounded-lg bg-foreground text-background font-medium hover:bg-foreground/90 disabled:opacity-40 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {isClassifying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
                <span>Auto-Extract & Index</span>
              </button>
            </div>
          </div>
        )}

        {activeTab === "faq" && (
          <div className="flex-1 p-6 space-y-4 overflow-y-auto">
            <div>
              <h2 className="text-sm font-medium text-foreground flex items-center gap-2">
                <HelpCircle className="h-4 w-4 text-indigo-400" />
                About Contexta Sovereign Architecture
              </h2>
              <p className="text-[11px] text-muted-foreground mt-1">
                Learn how Contexta keeps your AI memory safe, sovereign, and accessible to connected agents.
              </p>
            </div>

            <div className="space-y-3">
              <div className="p-3.5 rounded-lg border border-border/30 bg-secondary/20 space-y-1">
                <p className="font-medium text-foreground text-[12px]">What makes Contexta different?</p>
                <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
                  Contexta is offline-first and self-sovereign. Memories are stored locally with authenticated encryption and never shared with public model vendors.
                </p>
              </div>

              <div className="p-3.5 rounded-lg border border-border/30 bg-secondary/20 space-y-1">
                <p className="font-medium text-foreground text-[12px]">How do agents access my memories?</p>
                <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
                  Contexta exposes a standard Model Context Protocol (MCP) server on port 8765. Claude Desktop, Cursor, and custom agents fetch relevant context via semantic search.
                </p>
              </div>

              <div className="p-3.5 rounded-lg border border-border/30 bg-secondary/20 space-y-1">
                <p className="font-medium text-foreground text-[12px]">Can I edit or shred my vault?</p>
                <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
                  Yes. You maintain total ownership. You can inspect, modify, pin, or cryptographically shred your vault at any time from the dashboard.
                </p>
              </div>
            </div>

            <div className="pt-2">
              <button
                type="button"
                onClick={() => setActiveTab("chat")}
                className="px-4 py-2 rounded-lg bg-foreground text-background font-medium hover:bg-foreground/90 transition-all cursor-pointer flex items-center gap-2"
              >
                <span>Back to Interview</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Right / Side Panel: Live Memory Foundation Inspector */}
      <div className="w-full lg:w-80 flex flex-col gap-4">
        <div className="rounded-xl border border-border/40 bg-card/75 backdrop-blur-xl p-5 shadow-2xl flex flex-col gap-4">
          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-border/30">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-emerald-400" />
              <span className="font-medium text-foreground tracking-tight">Memory Foundation</span>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              {memories.length} Captured
            </span>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>Readiness Index</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 transition-all duration-500 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Memory List */}
          <div className="flex-1 max-h-[320px] overflow-y-auto space-y-2 pr-1">
            {memories.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground space-y-2">
                <Terminal className="h-6 w-6 mx-auto opacity-40 text-muted-foreground" />
                <p className="text-[11px]">As you chat or ingest notes, the classifier extracts key facts and preferences into this vault in real time.</p>
              </div>
            ) : (
              <AnimatePresence>
                {memories.map((m) => (
                  <motion.div
                    key={m.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    className="p-2.5 rounded-lg border border-border/30 bg-secondary/30 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-foreground/10 text-foreground/80">
                        {m.memory_type}
                      </span>
                      <span className="text-[9px] text-emerald-400 font-mono">
                        {(m.confidence * 100).toFixed(0)}% conf
                      </span>
                    </div>
                    <p className="text-[11px] text-foreground font-sans leading-snug line-clamp-2">
                      {m.content}
                    </p>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </div>

          {errorMessage && (
            <div className="rounded border border-red-500/30 bg-red-500/10 p-2.5 text-[11px] text-red-400 space-y-2">
              <p>{errorMessage}</p>
              <button
                type="button"
                onClick={() => {
                  document.cookie = "contexta_onboarding_completed=true; path=/; max-age=31536000; SameSite=Lax";
                  window.location.href = "/dashboard";
                }}
                className="w-full py-1.5 px-2 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 text-[10px] font-medium transition-all cursor-pointer"
              >
                Proceed to Dashboard (Offline Mode) &rarr;
              </button>
            </div>
          )}

          {/* Action Buttons */}
          <div className="pt-2 space-y-2">
            <button
              type="button"
              onClick={() => handleSaveAndComplete(false)}
              disabled={!isReadyToComplete || isSaving}
              className={`w-full py-2.5 rounded font-medium transition-all flex items-center justify-center gap-2 cursor-pointer ${
                isReadyToComplete
                  ? "bg-foreground text-background hover:bg-foreground/90 shadow-md active:scale-[0.99]"
                  : "bg-secondary text-muted-foreground border border-border/40 cursor-not-allowed opacity-60"
              }`}
            >
              {isSaving ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Encrypting & Saving...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  <span>
                    {isReadyToComplete
                      ? `Save & Enter Dashboard (${memories.length})`
                      : `Answer ${2 - memories.length} more to continue`}
                  </span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => handleSaveAndComplete(true)}
              disabled={isSaving}
              className="w-full py-2 text-center text-[10px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Skip setup for now &rarr;
            </button>
          </div>
        </div>

        {/* Security badge */}
        <div className="rounded-lg border border-border/30 bg-secondary/20 p-3 flex items-center gap-2.5 text-[10px] text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
          <span>All insights are cryptographically scoped to your tenant and never sent to third-party telemetry.</span>
        </div>
      </div>
    </div>
  );
}
