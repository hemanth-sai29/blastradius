"""
agent.py - Autonomous Code Graph LLM Agent powered by Model Context Protocol (MCP).

Connects to the official MCP server (server.py) and answers questions about the codebase.
Key Capabilities:
1. Picks the right tool(s) per question dynamically based on intent.
2. Calls more than one tool when questions require multi-angle reasoning.
3. Always returns:
   - (1) A plain-language answer.
   - (2) The exact multi-hop graph path(s) traversed.
   - (3) The list of tools called and the exact rationale for calling each.
4. Refuses to hallucinate: If the graph has no record or connecting path,
   it explicitly states that the graph has no answer rather than guessing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from server import create_server
from blastradius.graph.db import FalkorDBClient, db_client
from memory import memory_manager as default_memory_manager, UserMemoryManager

logger = logging.getLogger("blastradius.agent")


@dataclass
class ToolCallRecord:
    """Record of a tool invoked by the agent and the reasoning behind it."""
    tool: str
    arguments: dict[str, Any]
    why: str

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "arguments": self.arguments, "why": self.why}


@dataclass
class ReviewerEvidence:
    """Represents a recommended reviewer accompanied by concrete graph evidence."""
    name: str
    email: str
    score: float
    role: str
    graph_evidence: str
    paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "email": self.email,
            "score": self.score,
            "role": self.role,
            "graph_evidence": self.graph_evidence,
            "paths": self.paths,
        }


@dataclass
class ActionItem:
    """An individual action triggered by repository graph conditions."""
    action_type: str  # "RISK_FLAG", "SUGGEST_REVIEWERS", "GENERATE_PR_COMMENT"
    description: str
    status: str       # "PREVIEW (DRY RUN)" or "EXECUTED"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "description": self.description,
            "status": self.status,
            "payload": self.payload,
        }


@dataclass
class ActionReport:
    """Comprehensive report produced by graph-triggered actions with dry run preview."""
    target_function: str
    risk_level: str   # "HIGH RISK", "MEDIUM RISK", "LOW RISK"
    risk_badge: str   # "🚨 HIGH RISK", "🟡 MEDIUM RISK", "🟢 LOW RISK"
    risk_reason: str
    affected_functions: list[str]
    affected_files: list[str]
    best_reviewers: list[ReviewerEvidence]
    paths: list[str]
    markdown_comment: str
    dry_run: bool
    actions: list[ActionItem]
    execution_result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_function": self.target_function,
            "risk_level": self.risk_level,
            "risk_badge": self.risk_badge,
            "risk_reason": self.risk_reason,
            "affected_functions": self.affected_functions,
            "affected_files": self.affected_files,
            "best_reviewers": [r.to_dict() for r in self.best_reviewers],
            "paths": self.paths,
            "markdown_comment": self.markdown_comment,
            "dry_run": self.dry_run,
            "actions": [a.to_dict() for a in self.actions],
            "execution_result": self.execution_result,
        }

    def format_preview(self) -> str:
        """Renders dry-run preview or live execution confirmation."""
        sep = "=" * 70
        sub_sep = "-" * 70
        mode_header = "[DRY RUN PREVIEW - NO CHANGES COMMITTED]" if self.dry_run else "[ACTION EXECUTED]"

        output = [
            sep,
            f"{mode_header} Autonomous Code Graph Action Pipeline",
            f"Target Function: '{self.target_function}' | Mode: {'DRY RUN' if self.dry_run else 'EXECUTED'}",
            sep,
            "",
            "[ACTION 1: RISK ASSESSMENT]",
            f"• Risk Level: {self.risk_badge}",
            f"• Reason:     {self.risk_reason}",
            f"• Impacted:   {len(self.affected_functions)} function(s) across {len(self.affected_files)} file(s)",
            "",
            sub_sep,
            f"[ACTION 2: 2 BEST SUGGESTED REVIEWERS (WITH GRAPH EVIDENCE)]",
        ]

        if self.best_reviewers:
            for i, rev in enumerate(self.best_reviewers[:2], start=1):
                output.append(f"• Reviewer {i}: {rev.name} <{rev.email}> ({rev.role})")
                output.append(f"  Score:    {rev.score}")
                output.append(f"  Evidence: {rev.graph_evidence}")
        else:
            output.append("• No code authors or ownership records found in graph.")

        output.extend([
            "",
            sub_sep,
            "[ACTION 3: READY-TO-POST GITHUB PR COMMENT (MARKDOWN)]",
            sub_sep,
            self.markdown_comment,
            sub_sep,
        ])

        if self.dry_run:
            output.extend([
                "",
                "[DRY RUN NOTICE]:",
                "Actions are in DRY RUN mode by default. No external comments were posted.",
                "To execute these actions live (e.g. write to pr_comment.md),",
                "pass '--execute' or call 'run_pr_actions(..., dry_run=False)'.",
            ])
        else:
            output.extend([
                "",
                f"[EXECUTION CONFIRMED]: {self.execution_result or 'Actions executed successfully.'}",
            ])

        output.append(sep)
        return "\n".join(output)


@dataclass
class AgentResponse:
    """
    Standardized agent response contract:
    1. Plain-language answer
    2. Exact graph path(s) used
    3. List of tools called and why
    4. Optional action report (with dry run preview)
    5. User memory recalls and tracked code areas
    """
    question: str
    answer: str
    paths: list[str] = field(default_factory=list)
    tools_called: list[ToolCallRecord] = field(default_factory=list)
    has_answer: bool = True
    action_report: ActionReport | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
    memory_recalls: list[str] = field(default_factory=list)
    finding_id: str | None = None
    touched_areas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "paths": self.paths,
            "tools_called": [t.to_dict() for t in self.tools_called],
            "has_answer": self.has_answer,
            "action_report": self.action_report.to_dict() if self.action_report else None,
            "raw_data": self.raw_data,
            "memory_recalls": self.memory_recalls,
            "finding_id": self.finding_id,
            "touched_areas": self.touched_areas,
        }

    def format_output(self) -> str:
        """Renders a clean, human-readable terminal response."""
        sep = "=" * 70
        sub_sep = "-" * 70
        output = [
            sep,
            f"QUESTION: {self.question}",
            sep,
            "",
            "1. PLAIN-LANGUAGE ANSWER:",
            self.answer,
            "",
            sub_sep,
            f"2. EXACT GRAPH PATHS TRAVERSED ({len(self.paths)} path(s)):",
        ]

        if self.paths:
            for i, p in enumerate(self.paths, start=1):
                output.append(f"   [{i}] {p}")
        else:
            output.append("   [None] No graph edges were traversed for this query.")

        output.extend([
            "",
            sub_sep,
            f"3. TOOLS CALLED & REASONING ({len(self.tools_called)} tool(s)):",
        ])

        if self.tools_called:
            for t in self.tools_called:
                output.append(f"   • Tool: {t.tool}")
                output.append(f"     Args: {json.dumps(t.arguments, ensure_ascii=False)}")
                output.append(f"     Why:  {t.why}")
        else:
            output.append("   • No tools were called.")

        output.append(sep)

        if self.action_report:
            output.extend(["", self.action_report.format_preview()])

        return "\n".join(output)


class CodeGraphAgent:
    """
    Autonomous LLM agent interfacing with the official MCP server.
    Analyzes user intent, dispatches single or composite multi-tool queries,
    extracts graph paths, and synthesizes grounded answers without guessing.
    """

    def __init__(
        self,
        mcp_server=None,
        client: FalkorDBClient | None = None,
        read_only: bool = True,
        memory_manager: UserMemoryManager | None = None,
    ):
        self.client = client or db_client
        self.server = mcp_server or create_server(client=self.client, read_only=read_only)
        self.memory_manager = memory_manager or default_memory_manager
        self._tools_cache: dict[str, Any] | None = None

    async def _get_tool_descriptions(self) -> dict[str, str]:
        """Loads registered MCP tool names and descriptions."""
        if self._tools_cache is None:
            tools = await self.server.list_tools()
            self._tools_cache = {t.name: getattr(t, "description", "") for t in tools}
        return self._tools_cache

    def _extract_quoted_or_named_entities(self, text: str) -> list[str]:
        """Extracts candidate symbol or file names enclosed in quotes or backticks."""
        matches = re.findall(r"['\"`]([^'\"`]+)['\"`]", text)
        if matches:
            return matches
        # Fallback to tokens ending with .py or containing :
        tokens = text.split()
        candidates = []
        for token in tokens:
            cleaned = token.strip("?,.:;()[]{}")
            if cleaned.endswith(".py") or ":" in cleaned or "/" in cleaned or "_" in cleaned:
                candidates.append(cleaned)
        return candidates

    def plan_tools(self, question: str) -> list[tuple[str, dict[str, Any], str]]:
        """
        Plans which MCP tool(s) to invoke based on user intent.
        Returns a list of tuples: (tool_name, arguments, rationale).
        Can select multiple tools if the question contains multi-angle requirements.
        """
        q = question.lower().strip()
        entities = self._extract_quoted_or_named_entities(question)
        planned: list[tuple[str, dict[str, Any], str]] = []

        # Intent detection triggers
        wants_impact = any(
            w in q
            for w in [
                "break",
                "impact",
                "blast radius",
                "downstream",
                "ripple",
                "caller",
                "affect",
                "change function",
                "modify",
            ]
        )
        wants_reviewers = any(
            w in q
            for w in [
                "review",
                "reviewer",
                "who should review",
                "owner",
                "owns",
                "author",
                "expert",
                "who wrote",
            ]
        )
        wants_origin = any(
            w in q
            for w in [
                "origin",
                "provenance",
                "where did",
                "come from",
                "commit",
                "introduce",
                "ticket",
                "issue",
                "fixes #",
                "why was",
            ]
        )
        wants_path = any(
            w in q
            for w in [
                "shortest path",
                "path between",
                "how does",
                "connect to",
                "call chain",
                "reach",
                "dependency between",
            ]
        )
        wants_critical = any(
            w in q
            for w in [
                "critical",
                "bottleneck",
                "centrality",
                "riskiest",
                "highest coupling",
                "fan-in",
                "hubs",
                "top nodes",
            ]
        )
        wants_clusters = any(
            w in q
            for w in [
                "cluster",
                "community",
                "module structure",
                "package boundary",
                "architecture grouping",
                "modular",
            ]
        )

        # ----------------------------------------------------------------------
        # 1. Shortest Path Tool Plan
        # ----------------------------------------------------------------------
        if wants_path and len(entities) >= 2:
            planned.append(
                (
                    "shortest_path",
                    {"source": entities[0], "target": entities[1]},
                    f"To trace the shortest multi-hop dependency path connecting '{entities[0]}' and '{entities[1]}'.",
                )
            )

        # ----------------------------------------------------------------------
        # 2. Impact Analysis Tool Plan
        # ----------------------------------------------------------------------
        if wants_impact and entities:
            # Extract depth if specified (e.g. 'depth 4' or 'depth=2')
            depth_match = re.search(r"depth\s*[:=]?\s*(\d+)", q)
            depth_val = int(depth_match.group(1)) if depth_match else 3
            depth_val = max(1, min(depth_val, 10))
            symbol = entities[0]
            planned.append(
                (
                    "impact_analysis",
                    {"function_name": symbol, "depth": depth_val},
                    f"To calculate downstream blast radius and identify affected callers/modules for '{symbol}'.",
                )
            )

        # ----------------------------------------------------------------------
        # 3. Suggest Reviewers Tool Plan
        # ----------------------------------------------------------------------
        if wants_reviewers and entities:
            # If impact was also planned, reuse or pick the appropriate target
            target = entities[0] if entities else "blastradius/graph/db.py"
            # Avoid duplicate reviewer calls
            if not any(t[0] == "suggest_reviewers" for t in planned):
                planned.append(
                    (
                        "suggest_reviewers",
                        {"file_or_function": target},
                        f"To identify code owners and expert contributors qualified to review changes to '{target}'.",
                    )
                )

        # ----------------------------------------------------------------------
        # 4. Explain Origin Tool Plan
        # ----------------------------------------------------------------------
        if wants_origin and entities:
            target = entities[0]
            planned.append(
                (
                    "explain_origin",
                    {"function_name": target},
                    f"To trace the historical provenance, introducing commits, and issue tickets for '{target}'.",
                )
            )

        # ----------------------------------------------------------------------
        # 5. Critical Nodes Tool Plan
        # ----------------------------------------------------------------------
        if wants_critical:
            # Extract top_n if present
            top_match = re.search(r"top\s*(\d+)", q)
            top_val = int(top_match.group(1)) if top_match else 5
            top_val = max(1, min(top_val, 50))
            planned.append(
                (
                    "critical_nodes",
                    {"top_n": top_val},
                    f"To identify top {top_val} architectural bottlenecks and high-centrality hubs based on caller coupling.",
                )
            )

        # ----------------------------------------------------------------------
        # 6. Find Clusters Tool Plan
        # ----------------------------------------------------------------------
        if wants_clusters:
            planned.append(
                (
                    "find_clusters",
                    {},
                    "To detect module communities and architectural groupings across files and functions.",
                )
            )

        # ----------------------------------------------------------------------
        # Fallback: If no intent triggered yet an entity was found, default to impact
        # ----------------------------------------------------------------------
        if not planned and entities:
            planned.append(
                (
                    "impact_analysis",
                    {"function_name": entities[0], "depth": 3},
                    f"Defaulting to downstream blast radius inspection for target symbol '{entities[0]}'.",
                )
            )

        # Fallback: If no entities found but critical hubs mentioned
        if not planned and ("hub" in q or "important" in q or "central" in q):
            planned.append(
                (
                    "critical_nodes",
                    {"top_n": 5},
                    "To surface the most central hub functions in the graph repository.",
                )
            )

        return planned

    async def ask(self, question: str, user_id: str = "default_user") -> AgentResponse:
        """
        Processes a natural language question about the repository:
        1. Formulates tool plan (single or multi-tool).
        2. Recalls relevant user memory from the user's isolated FalkorDB graph.
        3. Executes tools via the MCP server.
        4. Aggregates multi-hop graph paths.
        5. Detects if the graph lacks data and refuses to guess.
        6. Formulates a complete, plain-language answer incorporating memory.
        7. Stores interaction in the user's memory graph.
        """
        entities = self._extract_quoted_or_named_entities(question)

        # 0. Recall relevant past interactions from user memory
        memory_items = self.memory_manager.get_relevant_memories(
            user_id=user_id,
            current_question=question,
            current_areas=entities,
        )
        memory_recall_phrases = [m.recall_phrase for m in memory_items if m.recall_phrase]

        plan = self.plan_tools(question)

        if not plan:
            return AgentResponse(
                question=question,
                answer=(
                    "The graph agent could not identify any code symbols or relevant graph queries "
                    "from the question. Please mention a function, file, or architectural concept "
                    "(e.g., 'What breaks if connect is modified?' or 'Who owns git_loader.py?')."
                ),
                paths=[],
                tools_called=[],
                has_answer=False,
                memory_recalls=memory_recall_phrases,
            )

        all_paths: list[str] = []
        tools_called_records: list[ToolCallRecord] = []
        raw_results: dict[str, Any] = {}
        empty_results_count = 0

        # Execute each planned tool in sequence
        for tool_name, args, rationale in plan:
            tools_called_records.append(
                ToolCallRecord(tool=tool_name, arguments=args, why=rationale)
            )

            try:
                res = await self.server.call_tool(tool_name, args)
                # Parse MCP CallToolResult structured_content or text
                data = getattr(res, "structured_content", None)
                if not data and getattr(res, "content", None):
                    first_content = res.content[0]
                    text_val = getattr(first_content, "text", "")
                    try:
                        data = json.loads(text_val)
                    except Exception:
                        data = {"raw_text": text_val}

                raw_results[tool_name] = data

                # Accumulate graph paths
                if isinstance(data, dict):
                    tool_paths = data.get("path", [])
                    for p in tool_paths:
                        if p and p not in all_paths:
                            all_paths.append(p)

                    # Check for empty findings
                    ans = data.get("answer", {})
                    if self._is_empty_tool_result(tool_name, ans):
                        empty_results_count += 1

            except Exception as e:
                logger.error(f"Error calling tool '{tool_name}' with args {args}: {e}")
                raw_results[tool_name] = {"error": str(e)}
                empty_results_count += 1

        # Synthesize plain-language answer
        answer_text, has_answer = self._synthesize_answer(
            question=question,
            tools_called=tools_called_records,
            raw_results=raw_results,
            paths=all_paths,
            empty_count=empty_results_count,
        )

        # Prepend contextual memory recall if user investigated this area before
        if memory_recall_phrases:
            memory_block = "\n".join(f"💡 Memory Recall: {p}" for p in memory_recall_phrases)
            answer_text = f"{memory_block}\n\n{answer_text}"

        # Check if question requested PR review / action
        action_report = None
        q_lower = question.lower()
        wants_pr_action = any(
            w in q_lower
            for w in [
                "action",
                "pr comment",
                "pr review",
                "review pr",
                "risk level",
                "flag",
                "github comment",
                "dry run",
                "assess pr",
            ]
        )
        if wants_pr_action:
            target = entities[0] if entities else "connect"
            action_report = await self.run_pr_actions(target, dry_run=True, user_id=user_id)

        # Determine all touched areas for memory graph storage
        touched_areas = list(dict.fromkeys(entities))
        for p in all_paths:
            for m in re.finditer(r"\[(?:Function|File):([^\]]+)\]", p):
                touched_areas.append(m.group(1))
        touched_areas = list(dict.fromkeys(touched_areas))

        # Store interaction in user's isolated memory graph
        record = self.memory_manager.record_query(
            user_id=user_id,
            question=question,
            answer=answer_text,
            touched_areas=touched_areas,
            paths=all_paths,
        )
        finding_id = record.get("finding_id")

        return AgentResponse(
            question=question,
            answer=answer_text,
            paths=all_paths,
            tools_called=tools_called_records,
            has_answer=has_answer,
            action_report=action_report,
            raw_data=raw_results,
            memory_recalls=memory_recall_phrases,
            finding_id=finding_id,
            touched_areas=touched_areas,
        )

    async def run_pr_actions(
        self,
        target_function: str,
        dry_run: bool = True,
        output_file: str | None = None,
        user_id: str = "default_user",
    ) -> ActionReport:
        """

        Executes autonomous actions triggered by repository graph findings:
        1. If changed function has a high blast radius (many callers), flags it as HIGH RISK.
        2. Suggests the 2 best reviewers with graph evidence for each.
        3. Generates a ready-to-post GitHub PR comment in Markdown.
        4. Runs in 'dry run' mode by default and provides a preview.
        """
        clean_target = target_function.strip("'\"` ")

        # 1. Execute impact_analysis tool
        impact_data: dict[str, Any] = {}
        try:
            res_impact = await self.server.call_tool(
                "impact_analysis", {"function_name": clean_target, "depth": 3}
            )
            impact_data = getattr(res_impact, "structured_content", None) or {}
            if not impact_data and getattr(res_impact, "content", None):
                try:
                    impact_data = json.loads(res_impact.content[0].text)
                except Exception:
                    impact_data = {}
        except Exception as e:
            logger.warning(f"Could not execute impact_analysis for '{clean_target}': {e}")
            impact_data = {
                "error": str(e),
                "answer": {"target": clean_target, "affected_functions": [], "affected_files": []},
            }

        # 2. Execute suggest_reviewers tool
        rev_data: dict[str, Any] = {}
        try:
            res_reviewers = await self.server.call_tool(
                "suggest_reviewers", {"file_or_function": clean_target}
            )
            rev_data = getattr(res_reviewers, "structured_content", None) or {}
            if not rev_data and getattr(res_reviewers, "content", None):
                try:
                    rev_data = json.loads(res_reviewers.content[0].text)
                except Exception:
                    rev_data = {}
        except Exception as e:
            logger.warning(f"Could not execute suggest_reviewers for '{clean_target}': {e}")
            rev_data = {
                "error": str(e),
                "answer": {"target": clean_target, "reviewers": []},
            }

        # Collect paths
        all_paths: list[str] = []
        for p in impact_data.get("path", []) + rev_data.get("path", []):
            if p and p not in all_paths:
                all_paths.append(p)

        impact_ans = impact_data.get("answer", {})
        affected_funcs = impact_ans.get("affected_functions", [])
        affected_files = impact_ans.get("affected_files", [])

        # Action 1: Evaluate blast radius & flag HIGH RISK if many callers
        caller_count = len(affected_funcs)
        file_count = len(affected_files)

        if caller_count >= 2 or file_count >= 2:
            risk_level = "HIGH RISK"
            risk_badge = "🚨 HIGH RISK"
            risk_reason = (
                f"High blast radius triggered: modifying '{clean_target}' affects "
                f"{caller_count} downstream caller(s) across {file_count} dependent file(s)."
            )
        elif caller_count == 1:
            risk_level = "MEDIUM RISK"
            risk_badge = "🟡 MEDIUM RISK"
            risk_reason = f"Moderate blast radius: modifying '{clean_target}' affects 1 downstream caller."
        else:
            risk_level = "LOW RISK"
            risk_badge = "🟢 LOW RISK"
            risk_reason = f"Low blast radius: modifying '{clean_target}' has no downstream callers recorded in graph."

        # Action 2: Suggest 2 best reviewers with concrete graph evidence for each
        raw_revs = rev_data.get("answer", {}).get("reviewers", [])
        best_reviewers: list[ReviewerEvidence] = []
        for r in raw_revs[:2]:
            name = r.get("name", "Unknown")
            email = r.get("email", "")
            score = float(r.get("score", 0.0))
            role = r.get("role", "Contributor")
            commits = r.get("commits", 0)
            lines = r.get("lines_changed", 0)

            rev_paths = [p for p in all_paths if name in p or email in p]

            if "Owner" in role:
                evidence = (
                    f"Designated Code Owner via graph edge (Author:{name})-[:OWNS]->(File) "
                    f"[ownership score: {score:.1f}, {commits} commit(s), {lines} lines changed]."
                )
            else:
                evidence = (
                    f"Frequent Contributor via graph chain (Author:{name})-[:AUTHORED]->(Commit)-[:MODIFIED_BY]->(File) "
                    f"[{commits} commit(s) touching blast zone, {lines} lines changed, score: {score:.1f}]."
                )

            best_reviewers.append(
                ReviewerEvidence(
                    name=name,
                    email=email,
                    score=score,
                    role=role,
                    graph_evidence=evidence,
                    paths=rev_paths,
                )
            )

        # Action 3: Generate ready-to-post GitHub PR comment in markdown
        markdown_comment = self._build_pr_comment_markdown(
            target_function=clean_target,
            risk_level=risk_level,
            risk_badge=risk_badge,
            risk_reason=risk_reason,
            affected_functions=affected_funcs,
            affected_files=affected_files,
            best_reviewers=best_reviewers,
            paths=all_paths,
            dry_run=dry_run,
        )

        status_str = "PREVIEW (DRY RUN)" if dry_run else "EXECUTED"
        actions = [
            ActionItem(
                action_type="FLAG_RISK",
                description=f"Flag PR as {risk_badge} based on blast radius analysis.",
                status=status_str,
                payload={"risk_level": risk_level, "reason": risk_reason, "caller_count": caller_count},
            ),
            ActionItem(
                action_type="SUGGEST_REVIEWERS",
                description=f"Suggest top {len(best_reviewers)} reviewers with concrete graph evidence.",
                status=status_str,
                payload={"reviewers": [r.to_dict() for r in best_reviewers]},
            ),
            ActionItem(
                action_type="GENERATE_PR_COMMENT",
                description="Generate ready-to-post GitHub PR comment in Markdown.",
                status=status_str,
                payload={"length": len(markdown_comment), "target_file": output_file or "pr_comment.md"},
            ),
        ]

        # Handle live execution when dry_run is False
        execution_result = None
        if not dry_run:
            out_file = output_file or "pr_comment.md"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(markdown_comment)
            execution_result = f"Successfully wrote ready-to-post GitHub PR comment to '{out_file}'."
            for a in actions:
                a.status = "EXECUTED"

        return ActionReport(
            target_function=clean_target,
            risk_level=risk_level,
            risk_badge=risk_badge,
            risk_reason=risk_reason,
            affected_functions=affected_funcs,
            affected_files=affected_files,
            best_reviewers=best_reviewers,
            paths=all_paths,
            markdown_comment=markdown_comment,
            dry_run=dry_run,
            actions=actions,
            execution_result=execution_result,
        )

    def _build_pr_comment_markdown(
        self,
        target_function: str,
        risk_level: str,
        risk_badge: str,
        risk_reason: str,
        affected_functions: list[str],
        affected_files: list[str],
        best_reviewers: list[ReviewerEvidence],
        paths: list[str],
        dry_run: bool,
    ) -> str:
        """Constructs an aesthetic, ready-to-post GitHub PR Markdown comment."""
        lines = [
            "## 💥 BlastRadius PR Impact & Risk Assessment",
            "",
            "> **Autonomous multi-hop graph analysis powered by FalkorDB.**",
            "",
            "| 🚦 Risk Tier | 🧩 Downstream Callers | 📁 Dependent Files | 👥 Best Reviewers | 🛡️ Status |",
            "| :---: | :---: | :---: | :---: | :---: |",
            f"| **{risk_badge}** | `{len(affected_functions)}` callers | `{len(affected_files)}` files | `{len(best_reviewers)}` suggested | {'🟡 Preview (Dry Run)' if dry_run else '✅ Ready to Post'} |",
            "",
            "---",
            "",
            "### ⚠️ Risk Assessment",
            f"- **Level**: `{risk_level}`",
            f"- **Trigger**: {risk_reason}",
            "",
            f"### 📁 Target Modified Function",
            f"- `{target_function}`",
            "",
            f"### 🧩 Affected Functions in Blast Zone ({len(affected_functions)})",
        ]

        if affected_functions:
            for fn in affected_functions[:10]:
                lines.append(f"- 🔴 `{fn}`")
            if len(affected_functions) > 10:
                lines.append(f"  *(+{len(affected_functions) - 10} additional callers)*")
        else:
            lines.append("- *(No downstream functions affected)*")

        lines.extend(["", "### 👥 2 Best Suggested Reviewers (with Graph Evidence)"])
        if best_reviewers:
            for i, r in enumerate(best_reviewers[:2], start=1):
                lines.append(f"{i}. **{r.name}** (`{r.email}`) — *{r.role}* (Score: `{r.score}`)")
                lines.append(f"   > **Graph Evidence**: `{r.graph_evidence}`")
        else:
            lines.append("- *(No author or ownership records found in graph)*")

        if paths:
            lines.extend([
                "",
                "---",
                "",
                "<details>",
                f"<summary>🔍 <b>Multi-Hop Graph Path(s) Traversed ({len(paths)} paths)</b></summary>",
                "",
                "```text",
            ])
            for p in paths[:15]:
                lines.append(p)
            if len(paths) > 15:
                lines.append(f"... and {len(paths) - 15} more path(s)")
            lines.extend(["```", "</details>"])

        lines.extend([
            "",
            "### 📋 Reviewer Checklist",
            f"- [ ] Verify regression tests for {len(affected_functions)} affected downstream caller(s)",
            f"- [ ] Inspect cross-module boundary contracts for {len(affected_files)} dependent file(s)",
            f"- [ ] Obtain review sign-off from suggested domain expert(s)",
            "",
            "---",
            f"*Generated by [BlastRadius](https://github.com/falkordb/falkordb) Code Graph Agent • {'Dry Run Mode' if dry_run else 'Live Execution'}*",
        ])
        return "\n".join(lines)

    def _is_empty_tool_result(self, tool_name: str, answer_dict: dict[str, Any]) -> bool:
        """Determines if a tool result indicates that the graph contains no matching data."""
        if not answer_dict or not isinstance(answer_dict, dict):
            return True

        if tool_name == "impact_analysis":
            return (
                answer_dict.get("total_affected_functions", 0) == 0
                and answer_dict.get("total_affected_files", 0) == 0
            )
        if tool_name == "suggest_reviewers":
            return len(answer_dict.get("reviewers", [])) == 0
        if tool_name == "explain_origin":
            return (
                len(answer_dict.get("commits", [])) == 0
                and len(answer_dict.get("authors", [])) == 0
            )
        if tool_name == "shortest_path":
            return not answer_dict.get("connected", False)
        if tool_name == "critical_nodes":
            return len(answer_dict.get("critical_nodes", [])) == 0
        if tool_name == "find_clusters":
            return len(answer_dict.get("clusters", [])) == 0
        return False

    def _synthesize_answer(
        self,
        question: str,
        tools_called: list[ToolCallRecord],
        raw_results: dict[str, Any],
        paths: list[str],
        empty_count: int,
    ) -> tuple[str, bool]:
        """Synthesizes a grounded, honest plain-language explanation without guessing."""
        # 1. Total emptiness check
        if empty_count == len(tools_called) and not paths:
            # If the single tool was shortest_path, provide the specific disconnection message
            if len(tools_called) == 1 and tools_called[0].tool == "shortest_path":
                sp_ans = raw_results.get("shortest_path", {}).get("answer", {})
                src = sp_ans.get("source", "source")
                dst = sp_ans.get("target", "target")
                msg = (
                    f"• [Shortest Path]: The graph contains NO path connecting '{src}' and '{dst}'. "
                    f"They operate in disconnected subgraphs or one of the symbols does not exist in FalkorDB."
                )
                return msg, False

            targets = self._extract_quoted_or_named_entities(question)
            target_str = f"'{targets[0]}'" if targets else "the specified query"
            msg = (
                f"The graph database has NO answer for {target_str}. "
                f"No matching nodes, edges, or historical records were found in FalkorDB. "
                f"Rather than guessing or hallucinating details, the agent confirms that {target_str} "
                f"is either unreferenced in the repository graph or does not exist."
            )
            return msg, False

        # 2. Multi-tool synthesis
        sections: list[str] = []

        for record in tools_called:
            tool_name = record.tool
            tool_data = raw_results.get(tool_name, {})
            ans = tool_data.get("answer", {}) if isinstance(tool_data, dict) else {}

            if "error" in tool_data:
                sections.append(f"• [{tool_name}] Error executing query: {tool_data['error']}")
                continue

            if tool_name == "impact_analysis":
                func = ans.get("target", "target")
                tot_fn = ans.get("total_affected_functions", 0)
                tot_fl = ans.get("total_affected_files", 0)
                depth = ans.get("max_depth", 3)
                if tot_fn == 0 and tot_fl == 0:
                    sections.append(
                        f"• [Downstream Impact]: Modifying '{func}' has no recorded downstream callers "
                        f"or dependent files within depth {depth}."
                    )
                else:
                    fns = ", ".join(ans.get("affected_functions", [])[:5])
                    files = ", ".join(ans.get("affected_files", [])[:3])
                    more_fn = f" (+{tot_fn - 5} more)" if tot_fn > 5 else ""
                    sections.append(
                        f"• [Downstream Impact]: Modifying '{func}' risks breaking {tot_fn} function(s) "
                        f"across {tot_fl} file(s) within depth {depth}. Key callers include: {fns}{more_fn}. "
                        f"Dependent modules: {files}."
                    )

            elif tool_name == "suggest_reviewers":
                target = ans.get("target", "target")
                revs = ans.get("reviewers", [])
                if not revs:
                    sections.append(
                        f"• [Reviewers]: The graph has no ownership or commit author history for '{target}'."
                    )
                else:
                    top_revs = [f"{r['name']} ({r['email']}, score: {r['score']})" for r in revs[:3]]
                    sections.append(
                        f"• [Suggested Reviewers]: For changes to '{target}', recommended reviewers are: "
                        f"{'; '.join(top_revs)}."
                    )

            elif tool_name == "explain_origin":
                fn = ans.get("function", "target")
                commits = ans.get("commits", [])
                authors = ans.get("authors", [])
                issues = ans.get("issues", [])
                if not commits and not authors:
                    sections.append(
                        f"• [Origin Provenance]: The graph has no record of introducing commits or authors for '{fn}'."
                    )
                else:
                    auth_names = ", ".join(a["name"] for a in authors) or "Unknown author"
                    commits_desc = ", ".join(c["short_hash"] for c in commits[:3])
                    issues_desc = (
                        f"resolving issue(s) {', '.join(i['id'] for i in issues)}"
                        if issues
                        else "with no linked issue tickets"
                    )
                    sections.append(
                        f"• [Origin Provenance]: '{fn}' was authored by {auth_names} across "
                        f"{len(commits)} commit(s) ({commits_desc}), {issues_desc}."
                    )

            elif tool_name == "shortest_path":
                src = ans.get("source", "source")
                dst = ans.get("target", "target")
                connected = ans.get("connected", False)
                hops = ans.get("hops", -1)
                if not connected:
                    sections.append(
                        f"• [Shortest Path]: The graph contains NO path connecting '{src}' and '{dst}'. "
                        f"They operate in disconnected subgraphs or one of the symbols does not exist."
                    )
                else:
                    sections.append(
                        f"• [Shortest Path]: '{src}' connects to '{dst}' in {hops} hop(s)."
                    )

            elif tool_name == "critical_nodes":
                nodes = ans.get("critical_nodes", [])
                if not nodes:
                    sections.append("• [Critical Hubs]: No high-centrality hubs found in the current graph.")
                else:
                    hub_summaries = [
                        f"{n['name']} (score: {n['centrality_score']}, in-callers: {n['in_degree']})"
                        for n in nodes[:3]
                    ]
                    sections.append(
                        f"• [Critical Hubs]: The highest-risk architectural bottlenecks are: "
                        f"{', '.join(hub_summaries)}."
                    )

            elif tool_name == "find_clusters":
                clusters = ans.get("clusters", [])
                tot = ans.get("total_clusters", 0)
                sections.append(
                    f"• [Module Clusters]: Detected {tot} community clusters grouping files "
                    f"and functions by import and call boundaries."
                )

        final_answer = "\n".join(sections)
        return final_answer, True


# ------------------------------------------------------------------------------
# CLI Runner
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Autonomous FalkorDB Code Graph Agent using MCP."
    )
    parser.add_argument(
        "question",
        type=str,
        nargs="?",
        default="What breaks if I change FalkorDBClient.connect and who should review it?",
        help="Question to ask about the codebase repository graph.",
    )
    parser.add_argument(
        "--action",
        choices=["ask", "review"],
        default="ask",
        help="Mode of operation: 'ask' to query the graph, 'review' to run PR action pipeline.",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target function for review action (e.g. 'connect' or 'verify_token').",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute actions live instead of running in dry run preview mode (default: dry run).",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="pr_comment.md",
        help="Output Markdown file path for generated PR comment when --execute is used.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the response formatted as JSON instead of human-readable text.",
    )
    args = parser.parse_args()

    agent = CodeGraphAgent()
    is_dry_run = not args.execute

    if args.action == "review" or args.target:
        target = args.target or args.question
        report = asyncio.run(
            agent.run_pr_actions(target, dry_run=is_dry_run, output_file=args.output_file)
        )
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(report.format_preview())
    else:
        response = asyncio.run(agent.ask(args.question))
        if args.json:
            print(json.dumps(response.to_dict(), indent=2))
        else:
            print(response.format_output())


if __name__ == "__main__":
    main()
