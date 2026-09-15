"""Context assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contexta.core.context.planner import ContextItem, ContextPlanner
from contexta.core.schemas import ContextRequest
from contexta.models.memory import MemoryRecord


@dataclass
class BuiltContext:
    user_profile: dict[str, Any] = field(default_factory=dict)
    rules: list[dict[str, Any]] = field(default_factory=list)
    active_projects: list[dict[str, Any]] = field(default_factory=list)
    preferences: list[dict[str, Any]] = field(default_factory=list)
    goals: list[dict[str, Any]] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    """Assemble structured context from retrieved memories."""

    def __init__(self, planner: ContextPlanner | None = None) -> None:
        self._planner = planner or ContextPlanner()
        self._cache: dict[str, BuiltContext] = {}

    def build(
        self,
        request: ContextRequest,
        memories: list[MemoryRecord],
        *,
        cache_key: str | None = None,
        newest_memory_timestamp: str | None = None,
    ) -> BuiltContext:
        if cache_key and cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached.metadata.get("newest_memory_timestamp") == newest_memory_timestamp:
                return cached

        valid_memories = [
            memory
            for memory in memories
            if not memory.is_archived and memory.valid_to is None
        ]
        valid_memories.sort(key=lambda memory: memory.importance, reverse=True)

        context = BuiltContext()
        # Ensure user_profile is initialized
        context.user_profile = {}
        
        for memory in valid_memories:
            item = self._memory_payload(memory)
            
            # Dynamically aggregate user profile (soul) data
            if memory.memory_type == "profile" or any(t in ["profile", "identity", "onboarding"] for t in (memory.tags or [])):
                if memory.structured_data:
                    # Merge structured data into the profile
                    for k, v in memory.structured_data.items():
                        if v is not None:
                            context.user_profile[k] = v
                else:
                    # If no structured data, just add it to preferences/facts
                    context.preferences.append(item)

            if memory.memory_type in {"procedural", "rule"}:
                context.rules.append(item)
            elif memory.memory_type == "project":
                context.active_projects.append(item)
            elif memory.memory_type == "preference":
                context.preferences.append(item)
            elif memory.memory_type == "goal":
                context.goals.append(item)
            elif memory.memory_type in {"event", "episodic"}:
                context.recent_events.append(item)
            elif memory.memory_type not in {"profile"}:
                context.relevant_memories.append(item)

        if request.config.token_budget:
            allocation = self._planner.allocate(
                request.config.token_budget,
                custom_weights=request.config.custom_weights,
            )
            planner_items = [
                ContextItem(
                    category=self._category_for(memory),
                    token_count=max(1, len(memory.content.split())),
                    relevance=memory.importance,
                    payload=memory,
                )
                for memory in valid_memories
            ]
            _, allocation = self._planner.fill_budget(allocation, planner_items)
            context.metadata["token_usage"] = allocation.actual_usage

        context.metadata["newest_memory_timestamp"] = newest_memory_timestamp
        if cache_key:
            self._cache[cache_key] = context
        return context

    def _memory_payload(self, memory: MemoryRecord) -> dict[str, Any]:
        return {
            "id": str(memory.id),
            "type": memory.memory_type,
            "title": memory.title,
            "content": memory.content,
            "importance": memory.importance,
        }

    def _category_for(self, memory: MemoryRecord) -> str:
        return {
            "project": "projects",
            "goal": "goals",
            "preference": "preferences",
            "relationship": "relationships",
            "event": "episodic",
            "episodic": "episodic",
        }.get(memory.memory_type, "facts")

    def to_system_prompt(self, context: BuiltContext, *, format: str = "markdown") -> str:
        """Format the built context into a clean system prompt injection block."""
        if format.lower() == "xml":
            return self.to_xml(context)

        sections: list[str] = []

        # 1. Procedural Rules (top priority)
        if context.rules:
            rules_block = ["## Operating Rules & Behavioral Directives"]
            for r in context.rules:
                rules_block.append(f"- **{r['title']}**: {r['content']}")
            sections.append("\n".join(rules_block))

        # 2. User Profile (The Soul) & Preferences
        if context.user_profile or context.preferences:
            pref_block = ["## User Profile & Preferences (The Soul)"]
            if context.user_profile:
                pref_block.append("### Core Identity")
                for key, val in context.user_profile.items():
                    key_fmt = str(key).replace("_", " ").title()
                    pref_block.append(f"- **{key_fmt}**: {val}")
            
            if context.preferences:
                pref_block.append("### Preferences & Traits")
                for p in context.preferences:
                    pref_block.append(f"- {p['content']}")
            sections.append("\n".join(pref_block))

        # 3. Active Projects & Goals
        if context.active_projects or context.goals:
            proj_block = ["## Active Projects & Goals"]
            for pr in context.active_projects:
                proj_block.append(f"- **Project: {pr['title']}**: {pr['content']}")
            for g in context.goals:
                proj_block.append(f"- **Goal: {g['title']}**: {g['content']}")
            sections.append("\n".join(proj_block))

        # 4. Recent Events & Timeline
        if context.recent_events:
            events_block = ["## Recent Interaction History & Events"]
            for ev in context.recent_events:
                events_block.append(f"- {ev['content']}")
            sections.append("\n".join(events_block))

        # 5. Relevant Knowledge Facts
        if context.relevant_memories:
            facts_block = ["## Verified Knowledge & Facts"]
            for m in context.relevant_memories:
                facts_block.append(f"- {m['content']}")
            sections.append("\n".join(facts_block))

        return "\n\n".join(sections)

    def to_xml(self, context: BuiltContext) -> str:
        """Format the built context into structured XML tags."""
        xml_lines: list[str] = ["<agent_context>"]

        if context.rules:
            xml_lines.append("  <operating_rules>")
            for r in context.rules:
                xml_lines.append(f"    <rule title=\"{r['title']}\">{r['content']}</rule>")
            xml_lines.append("  </operating_rules>")

        if context.user_profile or context.preferences:
            xml_lines.append("  <user_profile>")
            if context.user_profile:
                xml_lines.append("    <core_identity>")
                for k, v in context.user_profile.items():
                    xml_lines.append(f"      <{k}>{v}</{k}>")
                xml_lines.append("    </core_identity>")
            
            if context.preferences:
                xml_lines.append("    <preferences>")
                for p in context.preferences:
                    xml_lines.append(f"      <preference>{p['content']}</preference>")
                xml_lines.append("    </preferences>")
            xml_lines.append("  </user_profile>")

        if context.active_projects or context.goals:
            xml_lines.append("  <active_projects_and_goals>")
            for pr in context.active_projects:
                xml_lines.append(f"    <project title=\"{pr['title']}\">{pr['content']}</project>")
            for g in context.goals:
                xml_lines.append(f"    <goal title=\"{g['title']}\">{g['content']}</goal>")
            xml_lines.append("  </active_projects_and_goals>")

        if context.recent_events:
            xml_lines.append("  <recent_history>")
            for ev in context.recent_events:
                xml_lines.append(f"    <event>{ev['content']}</event>")
            xml_lines.append("  </recent_history>")

        if context.relevant_memories:
            xml_lines.append("  <knowledge_facts>")
            for m in context.relevant_memories:
                xml_lines.append(f"    <fact>{m['content']}</fact>")
            xml_lines.append("  </knowledge_facts>")

        xml_lines.append("</agent_context>")
        return "\n".join(xml_lines)

