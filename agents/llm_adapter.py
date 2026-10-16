"""LLM Adapter Interface (Part B, Phase B0).

Strict adherence to Section 0 Rule 5:
- The LLM never issues a verdict.
- Verdicts come only from declared policy evaluated in Cypher.
- The model chooses among tools offered to it and drafts text.
- It never sees a tool the gate has not unlocked.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol


class LLMAdapterProtocol(Protocol):
    """Protocol for LLM interactions in Part B agents."""

    def draft_missing_link_question(
        self,
        missing_evidence_role: str,
        entity_id: str,
        context_facts: List[str],
    ) -> str:
        """Draft a specific question for a human naming the missing link using only graph facts."""
        ...

    def choose_tool(
        self,
        unlocked_tools: List[str],
        instruction: str,
        context_data: Dict[str, Any],
    ) -> Optional[str]:
        """Choose a tool strictly from unlocked_tools. Never receives locked tools."""
        ...

    def draft_notice_text(
        self,
        target_role: str,
        target_id: str,
        causal_summary: str,
    ) -> str:
        """Draft notice copy for human approval based on stored causal path."""
        ...

    def rank_permitted_procedures(
        self,
        permitted_procedure_ids: List[str],
        context_summary: Dict[str, Any],
    ) -> List[str]:
        """Rank permitted procedures based on procedural context."""
        ...


class DeterministicLLMAdapter:
    """Deterministic implementation of the LLM adapter for offline runs."""

    def draft_missing_link_question(
        self,
        missing_evidence_role: str,
        entity_id: str,
        context_facts: List[str],
    ) -> str:
        facts_summary = "; ".join(context_facts) if context_facts else "no prior records"
        return (
            f"Missing required link for {entity_id}: required role '{missing_evidence_role}' "
            f"cannot be verified. Known facts: [{facts_summary}]. "
            f"Please verify or supply independent records for {entity_id}."
        )

    def choose_tool(
        self,
        unlocked_tools: List[str],
        instruction: str,
        context_data: Dict[str, Any],
    ) -> Optional[str]:
        if not unlocked_tools:
            return None
        # Deterministically select first permitted tool matching instruction, or first unlocked
        for tool in unlocked_tools:
            if tool.lower() in instruction.lower():
                return tool
        return unlocked_tools[0]

    def draft_notice_text(
        self,
        target_role: str,
        target_id: str,
        causal_summary: str,
    ) -> str:
        return (
            f"Attention {target_role} ({target_id}): Causal investigation indicates "
            f"exposure via: {causal_summary}. Pending review and disposition."
        )

    def rank_permitted_procedures(
        self,
        permitted_procedure_ids: List[str],
        context_summary: Dict[str, Any],
    ) -> List[str]:
        # Return procedures preserving input order or sorted by key
        return list(permitted_procedure_ids)


StubLLMAdapter = DeterministicLLMAdapter
