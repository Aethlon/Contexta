"use client";

import { usePathname } from "next/navigation";
import { clsx } from "clsx";

const navigation = [
  { title: "Getting Started", items: [
    { href: "/quickstart", label: "Quickstart" },
  ]},
  { title: "Concepts", items: [
    { href: "/concepts", label: "Overview" },
    { href: "/concepts/observations", label: "Observations" },
    { href: "/concepts/memories", label: "Memories" },
    { href: "/concepts/retrieval", label: "Retrieval" },
  ]},
  { title: "Integration Guides", items: [
    { href: "/guide/openai", label: "OpenAI Assistants" },
    { href: "/guide/llamaindex", label: "LlamaIndex" },
    { href: "/guide/anthropic", label: "Anthropic Claude" },
    { href: "/guide/langchain", label: "LangChain" },
    { href: "/guide/custom-agent", label: "Custom Agent" },
  ]},
  { title: "Reference", items: [
    { href: "/reference/sdks", label: "SDK Overview" },
    { href: "/reference/api", label: "API Reference" },
    { href: "/reference/sdk-python", label: "Python SDK" },
    { href: "/reference/sdk-typescript", label: "TypeScript SDK" },
    { href: "/reference/cli", label: "CLI" },
  ]},
  { title: "Examples", items: [
    { href: "/examples/coding-agent", label: "Coding Agent" },
    { href: "/examples/tutor-agent", label: "Tutor Agent" },
    { href: "/examples/crm-agent", label: "CRM Agent" },
  ]},
  { title: "More", items: [
    { href: "/pricing", label: "Pricing" },
    { href: "/changelog", label: "Changelog" },
  ]},
];

function SidebarSection({ title, items, currentPath }: { title: string; items: { href: string; label: string }[]; currentPath: string }) {
  return (
    <div className="sidebar-section">
      <h3 className="sidebar-section-title">{title}</h3>
      <ul className="sidebar-section-items">
        {items.map((item) => (
          <li key={item.href}>
            <a
              href={item.href}
              className={clsx("sidebar-link", currentPath === item.href && "sidebar-link-active")}
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="docs-sidebar">
      <nav>
        {navigation.map((section) => (
          <SidebarSection key={section.title} title={section.title} items={section.items} currentPath={pathname} />
        ))}
      </nav>
    </aside>
  );
}
