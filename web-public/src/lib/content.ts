export interface FAQItem {
  question: string;
  answer: string;
  id: string;
}

export interface FeatureItem {
  title: string;
  description: string;
  badge?: string;
  icon: string;
}

export interface PricingPlan {
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  ctaText: string;
  ctaHref: string;
  badge?: string;
  popular?: boolean;
}

export interface PricingComparisonRow {
  name: string;
  price: string;
  memories: string;
  observations: string;
  retrievals: string;
  projects: string;
  schemas: string;
  support: string;
  popular?: boolean;
}

export const problemComparison = {
  problems: [
    {
      title: "Exploding Token Costs",
      desc: "Shoveling entire chat histories into context windows spikes LLM API costs and degrades response quality."
    },
    {
      title: "High Latency SaaS APIs",
      desc: "Third-party memory services add extra roundtrips, putting memory retrieval at 150ms+ bottleneck speeds."
    },
    {
      title: "Data Leakage & Privacy Risks",
      desc: "Sending proprietary user interactions to external closed APIs violates GDPR/SOC2 compliance."
    }
  ],
  solutions: [
    {
      title: "Up to 80% Token Savings",
      desc: "Intelligently extracts, compresses, and scores memories, bringing token usage down by up to 80%."
    },
    {
      title: "Sub-100ms Managed Retrieval",
      desc: "Managed cloud retrieval with global edge deployment and 24/7 operations. Sub-100ms p99 even at 1M memories."
    },
    {
      title: "BYOK & Private by Default",
      desc: "Bring your own OpenAI, Anthropic, or DeepSeek key — memories never touch our LLM pipeline. EU/US regions, or self-host in your VPC."
    }
  ]
};

export const featuresList: FeatureItem[] = [
  {
    title: "Truth Maintenance",
    description: "Contradictions resolved automatically. Old facts are versioned, never deleted. Your agent stops flip-flopping.",
    badge: "Unique",
    icon: "ShieldCheck"
  },
  {
    title: "Sensitive Data Redaction",
    description: "Passwords, API keys, JWTs, OTPs and card numbers are redacted at ingestion — secrets can never enter the memory store.",
    badge: "At Ingestion",
    icon: "Lock"
  },
  {
    title: "Memory Explainability",
    description: "Every memory ships with full lineage: source observation, scoring breakdown, supersession history. Ask why it remembered.",
    icon: "SearchCheck"
  },
  {
    title: "Token-Aware Context Planner",
    description: "Set a token budget; Contexta allocates across projects, goals, preferences, and events with configurable weights.",
    icon: "SlidersHorizontal"
  },
  {
    title: "Three-Layer Tenant Isolation",
    description: "Repository scope, Postgres row-level security, and CI cross-tenant tests. No missing-WHERE-clause data leaks.",
    icon: "Shield"
  },
  {
    title: "Cluster-Aware Hybrid Retrieval",
    description: "Semantic + keyword + graph expansion with importance weighting in a single pass. Sub-100ms p99 at 1M memories.",
    icon: "Network"
  },
  {
    title: "Bring Your Own Key",
    description: "Use your OpenAI, Anthropic, or DeepSeek keys. Pay one platform fee; we never resell tokens.",
    icon: "KeyRound"
  },
  {
    title: "Any Agent Framework",
    description: "Adapters for OpenAI, Anthropic, LangChain, LlamaIndex, and Vercel AI SDK. Plus a generic protocol for custom loops.",
    icon: "Boxes"
  }
];

export const sdkCodes = {
  python: `from contexta_client import Contexta

# Initialize Contexta Cloud
memory = Contexta(
    api_key="ctx_live_99f2e8",
    api_url="https://api.contexta.dev"
)

# 1. Observe interaction
memory.observe(
    user_id="user_123",
    messages=[
        {"role": "user", "content": "I prefer historic hotels & matcha."},
        {"role": "assistant", "content": "I will remember that."}
    ]
)

# 2. Retrieve personalized context
ctx = memory.context(
    user_id="user_123",
    token_budget=1500
)

# 3. Augment LLM system prompt
system_prompt = f"You are a helpful guide.\\n\\n{ctx.to_system_prompt()}"`,
  typescript: `import { Contexta } from "@contexta/client";

// Initialize Contexta Cloud
const memory = new Contexta({
  apiKey: "ctx_live_99f2e8",
  apiUrl: "https://api.contexta.dev"
});

// 1. Observe conversation details
await memory.observe({
  userId: "user_123",
  messages: [
    { role: "user", content: "I prefer historic hotels & matcha." }
  ]
});

// 2. Retrieve structured context
const ctx = await memory.context({
  userId: "user_123"
});

// 3. Inject into system prompt
const systemPrompt = \`Helpful guide.\\n\\n\${ctx.toSystemPrompt()}\`;`
};

export const pricingPlans: PricingPlan[] = [
  {
    name: "Free",
    price: "$0",
    period: "month",
    description: "For prototypes and small experiments. No credit card required.",
    features: [
      "10,000 memories",
      "25,000 observations / month",
      "100,000 retrievals / month",
      "1 project",
      "Community support",
      "30-day retention"
    ],
    ctaText: "Start free",
    ctaHref: "https://app.contexta.dev"
  },
  {
    name: "Hobby",
    price: "$19",
    period: "month",
    description: "For solo devs prototyping a single agent.",
    features: [
      "50,000 memories",
      "100,000 observations / month",
      "1,000,000 retrievals / month",
      "3 custom schemas",
      "3 custom policies",
      "1 project",
      "90-day retention"
    ],
    ctaText: "Start free",
    ctaHref: "https://app.contexta.dev"
  },
  {
    name: "Solo Pro",
    price: "$69",
    period: "month",
    description: "For an indie dev shipping a real product with real users.",
    features: [
      "250,000 memories",
      "500,000 observations / month",
      "5,000,000 retrievals / month",
      "10 custom schemas",
      "10 custom policies",
      "5 projects",
      "Nightly reflection",
      "1-year retention"
    ],
    ctaText: "Start free",
    ctaHref: "https://app.contexta.dev",
    badge: "Most Popular",
    popular: true
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "contact sales",
    description: "Dedicated single-tenant infrastructure for regulated, high-volume deployments.",
    features: [
      "Dedicated single-tenant infra",
      "VPC peering & private link",
      "BAA / SOC 2 report sharing",
      "Custom regions (US, EU, AP)",
      "99.99% uptime SLA",
      "Custom retention & audit policies"
    ],
    ctaText: "Contact Sales",
    ctaHref: "mailto:licensing@contexta.dev"
  }
];

export const pricingComparison: PricingComparisonRow[] = [
  {
    name: "Free",
    price: "$0",
    memories: "10,000",
    observations: "25,000",
    retrievals: "100,000",
    projects: "1",
    schemas: "—",
    support: "Community support · 30-day retention"
  },
  {
    name: "Hobby",
    price: "$19",
    memories: "50,000",
    observations: "100,000",
    retrievals: "1,000,000",
    projects: "1",
    schemas: "3 schemas · 3 policies",
    support: "Community support · 90-day retention"
  },
  {
    name: "Solo Pro",
    price: "$69",
    memories: "250,000",
    observations: "500,000",
    retrievals: "5,000,000",
    projects: "5",
    schemas: "10 schemas · 10 policies",
    support: "Nightly reflection · 1-year retention",
    popular: true
  },
  {
    name: "Team",
    price: "$499",
    memories: "2,000,000",
    observations: "5,000,000",
    retrievals: "50,000,000",
    projects: "20",
    schemas: "Unlimited schemas & policies",
    support: "SSO (Google, GitHub) · unlimited retention"
  },
  {
    name: "Enterprise",
    price: "Custom",
    memories: "Dedicated",
    observations: "Custom",
    retrievals: "Custom",
    projects: "Unlimited",
    schemas: "Unlimited",
    support: "VPC peering · BAA/SOC 2 · 99.99% SLA"
  }
];

export const faqList: FAQItem[] = [
  {
    id: "faq-1",
    question: "What is Contexta?",
    answer: "Contexta Cloud is a managed memory intelligence layer for AI agents. It acts as an external intelligence store that tracks user preferences, relationships, and history across multiple sessions. Instead of sending all chat history to LLMs, Contexta extracts relevant facts and injects only what is semantically and structurally needed, saving token costs and improving agent accuracy. The same engine is available to self-host under Apache 2.0."
  },
  {
    id: "faq-2",
    question: "How does it compare to closed-source SaaS memory solutions?",
    answer: "Contexta Cloud is managed for you, but private by default. Bring your own OpenAI, Anthropic, or DeepSeek key, and your memories never touch our LLM pipeline. We run storage, retrieval, reflection, and compliance on our side with sub-100ms p99 retrieval, EU/US regions, and 24/7 operations. Prefer full control? The open-source Community Edition self-hosts the same engine in your own VPC."
  },
  {
    id: "faq-3",
    question: "What is a 'Dream Cycle' in Contexta?",
    answer: "Dream Cycles represent the autonomous background optimization pipeline. While the write path is instant (observing conversations), worker tasks execute asynchronous 'dreaming' cycles. During these runs, Contexta merges duplicate facts, resolves conflicting information (e.g., if a user changes their preference), scores the importance of facts, and decays outdated data so your LLM context stays clutter-free."
  },
  {
    id: "faq-4",
    question: "Do I need an OpenAI or DeepSeek key to start using Contexta?",
    answer: "No. Contexta Cloud includes hosted extraction on the Free plan so you can build and test without any LLM key. For production, bring your own OpenAI, Anthropic, or DeepSeek key — your secrets never pass through our pipeline — or opt into managed extraction on Enterprise."
  },
  {
    id: "faq-5",
    question: "How is multi-tenancy enforced?",
    answer: "Contexta Cloud enforces three-layer tenant isolation: repository scope, Postgres row-level security, and CI cross-tenant tests. Every observe and retrieve query must supply a Tenant and User ID, ensuring a customer can never read or query another customer's memory graph."
  },
  {
    id: "faq-6",
    question: "What is the dual-licensing model?",
    answer: "Contexta Cloud is a managed SaaS with a single platform fee and BYOK — no hidden token markups. The same engine is free and open-source under the Apache 2.0 license for self-hosting, personal testing, and internal non-commercial setups. Contact licensing@contexta.dev for commercial license terms."
  },
  {
    id: "faq-7",
    question: "Is there a free tier?",
    answer: "Yes. The Free plan includes 10,000 memories, 25,000 observations and 100,000 retrievals per month, one project, and 30-day retention — no credit card required. Upgrade to Hobby ($19/mo) when your agents outgrow it."
  },
  {
    id: "faq-8",
    question: "Where is my data stored?",
    answer: "Contexta Cloud runs in US and EU regions — choose where your data lives at project creation. With BYOK, your LLM provider never sees your memory store, and vice versa. Enterprise plans add VPC peering and custom regions for full data-locality control."
  }
];
