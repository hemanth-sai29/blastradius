"""
web_app.py - FastAPI Web Application & Interactive Code Graph Explorer.

Features:
- Chat interface powered by CodeGraphAgent.
- Interactive Cytoscape.js code graph view with dynamic path highlighting.
- Tool Calls side panel showing MCP tools invoked, arguments, and rationales.
- PR Risk Assessment Action preview with badge, reviewer evidence, and markdown comment viewer.
- Clean design with modern dark mode by default (and light mode toggle).
- "Try an Example" button preloading the 5 sample questions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agent import CodeGraphAgent, AgentResponse, ActionReport
from server import create_server
from blastradius.graph.db import FalkorDBClient, db_client
from memory import memory_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("blastradius.web_app")

app = FastAPI(
    title="💥 BlastRadius — Interactive Code Graph & MCP Agent",
    description="Autonomous multi-hop code impact analysis with live Cytoscape.js path visualization.",
    version="1.0.0",
)

# CORS middleware for local frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static folder exists
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize global agent instance (with fallback if FalkorDB is offline)
try:
    _conn = db_client.connect()
    _conn.query("RETURN 1")
    agent = CodeGraphAgent()
    logger.info("Connected to live FalkorDB instance for CodeGraphAgent.")
except Exception as _e:
    from tests.test_agent import AgentTestMockClient
    mock_c = AgentTestMockClient()
    agent = CodeGraphAgent(client=mock_c)
    logger.info(f"Using AgentTestMockClient for CodeGraphAgent fallback: {_e}")

# ------------------------------------------------------------------------------
# 5 Preset Example Questions
# ------------------------------------------------------------------------------
PRESET_EXAMPLES = [
    {
        "id": 1,
        "title": "Downstream Blast Radius",
        "icon": "💥",
        "category": "Single-Tool Impact",
        "question": "What could break if I modify function 'connect' in blastradius/graph/db.py?",
        "hint": "Calculates downstream blast radius across multi-hop callers and dependent files.",
    },
    {
        "id": 2,
        "title": "Code Provenance & Issues",
        "icon": "🧭",
        "category": "Single-Tool Origin",
        "question": "Where did 'load_history' come from, who wrote it, and what issues did it resolve?",
        "hint": "Traces provenance back to git commits, authors, and linked issue tickets (#123).",
    },
    {
        "id": 3,
        "title": "Impact & Reviewers",
        "icon": "👥",
        "category": "Multi-Tool PR",
        "question": "What breaks if I change 'verify_token' and who should review it?",
        "hint": "Combines blast radius evaluation with git ownership scoring for review suggestions.",
    },
    {
        "id": 4,
        "title": "Shortest Path & Bottlenecks",
        "icon": "🎯",
        "category": "Multi-Tool Architecture",
        "question": "How does 'api/routes.py:login_route' connect to 'auth/jwt.py:verify_token', and what are the critical bottlenecks in the repo?",
        "hint": "Finds multi-hop call hops and surfaces high-fan-in architectural hubs.",
    },
    {
        "id": 5,
        "title": "Zero-Hallucination Refusal",
        "icon": "🛡️",
        "category": "Honest Refusal",
        "question": "What breaks if I modify 'legacy_billing_migration_v0'?",
        "hint": "Demonstrates honest refusal when the graph contains no matching data.",
    },
]

# ------------------------------------------------------------------------------
# Baseline Graph Repository Fallback
# ------------------------------------------------------------------------------
BASELINE_GRAPH = {
    "nodes": [
        {"id": "blastradius/config.py", "label": "config.py", "type": "File", "group": "config"},
        {"id": "blastradius/config.py:_detect_falkordb_host", "label": "_detect_falkordb_host", "type": "Function", "file": "blastradius/config.py", "group": "config"},
        {"id": "blastradius/config.py:_is_port_open", "label": "_is_port_open", "type": "Function", "file": "blastradius/config.py", "group": "config"},
        {"id": "blastradius/graph/db.py", "label": "db.py", "type": "File", "group": "graph"},
        {"id": "blastradius/graph/db.py:FalkorDBClient.connect", "label": "connect", "type": "Function", "file": "blastradius/graph/db.py", "group": "graph"},
        {"id": "blastradius/graph/db.py:FalkorDBClient.query", "label": "query", "type": "Function", "file": "blastradius/graph/db.py", "group": "graph"},
        {"id": "blastradius/graph/db.py:FalkorDBClient.init_schema", "label": "init_schema", "type": "Function", "file": "blastradius/graph/db.py", "group": "graph"},
        {"id": "blastradius/graph/algorithms.py", "label": "algorithms.py", "type": "File", "group": "algorithms"},
        {"id": "blastradius/graph/algorithms.py:GraphAlgorithms.calculate_blast_radius", "label": "calculate_blast_radius", "type": "Function", "file": "blastradius/graph/algorithms.py", "group": "algorithms"},
        {"id": "blastradius/graph/algorithms.py:GraphAlgorithms.find_shortest_path", "label": "find_shortest_path", "type": "Function", "file": "blastradius/graph/algorithms.py", "group": "algorithms"},
        {"id": "server.py", "label": "server.py (MCP)", "type": "File", "group": "server"},
        {"id": "server.py:impact_analysis", "label": "impact_analysis", "type": "Function", "file": "server.py", "group": "server"},
        {"id": "server.py:suggest_reviewers", "label": "suggest_reviewers", "type": "Function", "file": "server.py", "group": "server"},
        {"id": "agent.py", "label": "agent.py (Agent)", "type": "File", "group": "agent"},
        {"id": "agent.py:CodeGraphAgent.ask", "label": "ask", "type": "Function", "file": "agent.py", "group": "agent"},
        {"id": "agent.py:CodeGraphAgent.run_pr_actions", "label": "run_pr_actions", "type": "Function", "file": "agent.py", "group": "agent"},
        {"id": "git_loader.py", "label": "git_loader.py", "type": "File", "group": "git"},
        {"id": "git_loader.py:GitLoader.load_history", "label": "load_history", "type": "Function", "file": "git_loader.py", "group": "git"},
        {"id": "Author:Seenu", "label": "Seenu (Dev)", "type": "Author", "group": "author"},
        {"id": "Commit:5db75a5", "label": "Commit: 5db75a5", "type": "Commit", "group": "commit"},
        {"id": "Issue:#123", "label": "Issue: #123", "type": "Issue", "group": "issue"},
        {"id": "auth/service.py", "label": "auth/service.py", "type": "File", "group": "auth"},
        {"id": "auth/jwt.py", "label": "auth/jwt.py", "type": "File", "group": "auth"},
        {"id": "api/routes.py", "label": "api/routes.py", "type": "File", "group": "api"},
        {"id": "auth/service.py:login", "label": "login", "type": "Function", "file": "auth/service.py", "group": "auth"},
        {"id": "auth/jwt.py:verify_token", "label": "verify_token", "type": "Function", "file": "auth/jwt.py", "group": "auth"},
        {"id": "api/routes.py:login_route", "label": "login_route", "type": "Function", "file": "api/routes.py", "group": "api"},
        {"id": "Author:Alice Smith", "label": "Alice Smith", "type": "Author", "group": "author"},
        {"id": "Author:Bob Jones", "label": "Bob Jones", "type": "Author", "group": "author"},
    ],
    "edges": [
        {"id": "e_cfg_port", "source": "blastradius/config.py:_detect_falkordb_host", "target": "blastradius/config.py:_is_port_open", "label": "CALLS"},
        {"id": "e_db_conn", "source": "blastradius/graph/db.py:FalkorDBClient.query", "target": "blastradius/graph/db.py:FalkorDBClient.connect", "label": "CALLS"},
        {"id": "e_db_schema", "source": "blastradius/graph/db.py:FalkorDBClient.init_schema", "target": "blastradius/graph/db.py:FalkorDBClient.connect", "label": "CALLS"},
        {"id": "e_algo_blast", "source": "blastradius/graph/algorithms.py:GraphAlgorithms.calculate_blast_radius", "target": "blastradius/graph/db.py:FalkorDBClient.query", "label": "CALLS"},
        {"id": "e_algo_path", "source": "blastradius/graph/algorithms.py:GraphAlgorithms.find_shortest_path", "target": "blastradius/graph/db.py:FalkorDBClient.query", "label": "CALLS"},
        {"id": "e_server_imp", "source": "server.py:impact_analysis", "target": "blastradius/graph/algorithms.py:GraphAlgorithms.calculate_blast_radius", "label": "CALLS"},
        {"id": "e_agent_ask", "source": "agent.py:CodeGraphAgent.ask", "target": "server.py:impact_analysis", "label": "CALLS"},
        {"id": "e_agent_act", "source": "agent.py:CodeGraphAgent.run_pr_actions", "target": "server.py:suggest_reviewers", "label": "CALLS"},
        {"id": "e_git_auth", "source": "Author:Seenu", "target": "Commit:5db75a5", "label": "AUTHORED"},
        {"id": "e_git_mod", "source": "Commit:5db75a5", "target": "git_loader.py", "label": "MODIFIED_BY"},
        {"id": "e_git_fix", "source": "Commit:5db75a5", "target": "Issue:#123", "label": "FIXES"},
        {"id": "e_route_login", "source": "api/routes.py:login_route", "target": "auth/service.py:login", "label": "CALLS"},
        {"id": "e_login_verify", "source": "auth/service.py:login", "target": "auth/jwt.py:verify_token", "label": "CALLS"},
        {"id": "e_alice_owns", "source": "Author:Alice Smith", "target": "auth/service.py", "label": "OWNS"},
        {"id": "e_bob_auth", "source": "Author:Bob Jones", "target": "auth/jwt.py:verify_token", "label": "CONTRIBUTED"},
    ],
}


def parse_paths_to_graph_elements(paths: list[str]) -> dict[str, list[dict[str, Any]]]:
    """
    Parses serialized path strings (e.g. '[Function:A] --(CALLS)--> [Function:B]')
    into Cytoscape node and edge objects with highlighted=True.
    """
    nodes_map: dict[str, dict[str, Any]] = {}
    edges_list: list[dict[str, Any]] = []

    for path_str in paths:
        if not path_str or not isinstance(path_str, str):
            continue

        # Extract nodes: [Label:name]
        node_matches = list(re.finditer(r"\[(\w+):([^\]]+)\]", path_str))
        # Extract edge relations: --(REL)-->
        rel_matches = list(re.finditer(r"--\((\w+)\)-->", path_str))

        extracted_nodes: list[dict[str, Any]] = []
        for match in node_matches:
            node_type = match.group(1)
            raw_id = match.group(2).strip()

            label = raw_id
            if ":" in raw_id:
                label = raw_id.split(":")[-1]
            elif "/" in raw_id:
                label = raw_id.split("/")[-1]

            node_obj = {
                "id": raw_id,
                "label": label,
                "type": node_type,
                "full_name": raw_id,
                "highlighted": True,
            }
            nodes_map[raw_id] = node_obj
            extracted_nodes.append(node_obj)

        for i, rel_match in enumerate(rel_matches):
            if i < len(extracted_nodes) - 1:
                src = extracted_nodes[i]["id"]
                tgt = extracted_nodes[i + 1]["id"]
                rel_label = rel_match.group(1)
                edge_id = f"hl_{src}__{rel_label}__{tgt}_{i}"
                edges_list.append(
                    {
                        "id": edge_id,
                        "source": src,
                        "target": tgt,
                        "label": rel_label,
                        "highlighted": True,
                    }
                )

    return {"nodes": list(nodes_map.values()), "edges": edges_list}


# ------------------------------------------------------------------------------
# API Models
# ------------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str
    mode: str = "ask"  # "ask" or "review"
    execute: bool = False
    output_file: str = "pr_comment.md"
    user_id: str = "default_user"


class UsefulMarkRequest(BaseModel):
    user_id: str = "default_user"
    finding_id: str
    useful: bool = True


# ------------------------------------------------------------------------------
# API Routes
# ------------------------------------------------------------------------------
@app.get("/")
async def serve_index():
    """Serves the single-page frontend application."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>BlastRadius Web UI Initializing...</h1>")


@app.get("/api/examples")
async def get_examples():
    """Returns the 5 preset example questions."""
    return {"examples": PRESET_EXAMPLES}


@app.get("/api/graph")
async def get_graph():
    """Returns the repository code graph elements for Cytoscape.js visualization."""
    # Attempt to query live FalkorDB graph if available
    try:
        cypher = """
        MATCH (a)-[r]->(b)
        RETURN labels(a)[0] AS a_type,
               COALESCE(a.full_name, a.path, a.name, a.id, a.hash) AS a_id,
               type(r) AS rel_type,
               labels(b)[0] AS b_type,
               COALESCE(b.full_name, b.path, b.name, b.id, b.hash) AS b_id
        LIMIT 100
        """
        res = db_client.query(cypher)
        if res and res.result_set:
            nodes_map: dict[str, dict[str, Any]] = {}
            edges_list: list[dict[str, Any]] = []

            for row in res.result_set:
                a_type, a_id, rel, b_type, b_id = row[0], str(row[1]), row[2], row[3], str(row[4])

                # Node A
                if a_id not in nodes_map:
                    nodes_map[a_id] = {
                        "id": a_id,
                        "label": a_id.split(":")[-1] if ":" in a_id else a_id.split("/")[-1],
                        "type": a_type or "Node",
                    }
                # Node B
                if b_id not in nodes_map:
                    nodes_map[b_id] = {
                        "id": b_id,
                        "label": b_id.split(":")[-1] if ":" in b_id else b_id.split("/")[-1],
                        "type": b_type or "Node",
                    }

                edges_list.append(
                    {
                        "id": f"e_{a_id}_{rel}_{b_id}",
                        "source": a_id,
                        "target": b_id,
                        "label": rel,
                    }
                )

            if len(nodes_map) > 0:
                return {"nodes": list(nodes_map.values()), "edges": edges_list}
    except Exception as e:
        logger.warning(f"Could not fetch live graph from FalkorDB: {e}. Using baseline graph.")

    return BASELINE_GRAPH


@app.post("/api/chat")
async def handle_chat(req: ChatRequest):
    """
    Handles user chat questions:
    - Runs agent reasoning across MCP tools.
    - Extracts multi-hop graph path(s) and marks them for Cytoscape highlight.
    - Formulates plain-language answer and tool rationales.
    """
    clean_q = req.question.strip()
    if not clean_q:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    is_dry_run = not req.execute

    # 1. Action Review mode
    if req.mode == "review" or any(w in clean_q.lower() for w in ["review pr", "action review", "assess pr"]):
        entities = agent._extract_quoted_or_named_entities(clean_q)
        target = entities[0] if entities else "verify_token"
        report: ActionReport = await agent.run_pr_actions(
            target, dry_run=is_dry_run, output_file=req.output_file, user_id=req.user_id
        )

        hl_elements = parse_paths_to_graph_elements(report.paths)

        return {
            "user_id": req.user_id,
            "question": clean_q,
            "answer": (
                f"Generated PR Action Assessment for '{target}'.\n"
                f"Risk Tier: {report.risk_badge}\n"
                f"Downstream Impact: {len(report.affected_functions)} caller(s) across {len(report.affected_files)} file(s).\n"
                f"Top Reviewers: {', '.join(r.name for r in report.best_reviewers)}."
            ),
            "paths": report.paths,
            "tools_called": [
                {
                    "tool": "impact_analysis",
                    "arguments": {"function_name": target, "depth": 3},
                    "why": "Evaluates downstream blast radius and affected callers.",
                },
                {
                    "tool": "suggest_reviewers",
                    "arguments": {"file_or_function": target},
                    "why": "Identifies code owners and frequent authors with graph evidence.",
                },
            ],
            "has_answer": True,
            "action_report": report.to_dict(),
            "highlighted_elements": hl_elements,
            "is_dry_run": is_dry_run,
            "memory_recalls": [],
            "finding_id": f"pr_{target}",
            "touched_areas": [target] + report.affected_files,
        }

    # 2. General Agent QA mode
    resp: AgentResponse = await agent.ask(clean_q, user_id=req.user_id)
    hl_elements = parse_paths_to_graph_elements(resp.paths)

    return {
        "user_id": req.user_id,
        "question": resp.question,
        "answer": resp.answer,
        "paths": resp.paths,
        "tools_called": [t.to_dict() for t in resp.tools_called],
        "has_answer": resp.has_answer,
        "action_report": resp.action_report.to_dict() if resp.action_report else None,
        "highlighted_elements": hl_elements,
        "is_dry_run": True,
        "memory_recalls": resp.memory_recalls,
        "finding_id": resp.finding_id,
        "touched_areas": resp.touched_areas,
    }


# ------------------------------------------------------------------------------
# Per-User Memory Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/memory/graph")
async def get_user_memory_graph(user_id: str = "default_user"):
    """
    Returns the user's isolated FalkorDB memory graph formatted for Cytoscape.js.
    Each user gets a dedicated graph (graph name = user_id).
    """
    clean_user = user_id.strip() or "default_user"
    graph_data = memory_manager.get_memory_graph(clean_user)
    summary = memory_manager.get_memory_summary(clean_user)
    return {
        "user_id": clean_user,
        "graph_name": summary.get("graph_name", clean_user),
        "nodes": graph_data.get("nodes", []),
        "edges": graph_data.get("edges", []),
        "summary": summary,
    }


@app.post("/api/memory/useful")
async def mark_finding_useful(req: UsefulMarkRequest):
    """
    Marks or unmarks a finding as useful in the user's isolated memory graph.
    Creates or removes (User)-[:MARKED_USEFUL]->(Finding) edge.
    """
    clean_user = req.user_id.strip() or "default_user"
    success = memory_manager.mark_finding_useful(
        user_id=clean_user,
        finding_id=req.finding_id,
        useful=req.useful,
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Finding '{req.finding_id}' not found in memory graph for user '{clean_user}'.",
        )
    return {
        "success": True,
        "user_id": clean_user,
        "finding_id": req.finding_id,
        "marked_useful": req.useful,
        "message": "Marked finding as useful in your personal memory graph." if req.useful else "Removed useful bookmark.",
    }


@app.get("/api/memory/summary")
async def get_user_memory_summary(user_id: str = "default_user"):
    """Returns memory metrics: total questions, tracked areas, useful bookmarks."""
    clean_user = user_id.strip() or "default_user"
    return memory_manager.get_memory_summary(clean_user)


@app.delete("/api/memory")
async def clear_user_memory(user_id: str = "default_user"):
    """Clears the memory graph for a user."""
    clean_user = user_id.strip() or "default_user"
    memory_manager.clear_memory(clean_user)
    return {"success": True, "message": f"Memory cleared for user '{clean_user}'."}



def run():
    """CLI starter for the web application."""
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    run()
