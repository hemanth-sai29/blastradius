"""
memory.py - Per-User Graph Memory System for BlastRadius.

Provides isolated memory graphs in FalkorDB for each user (graph name = user_id).
Stores:
1. Past questions: (u:User)-[:ASKED]->(q:Question)
2. Code areas asked about: (q:Question)-[:TOUCHED_AREA]->(c:CodeArea)
3. Findings produced: (q:Question)-[:PRODUCED]->(f:Finding)
4. Useful marks: (u:User)-[:MARKED_USEFUL]->(f:Finding)
5. Finding relations: (f:Finding)-[:RELATES_TO]->(c:CodeArea)

When a user asks a new question, the agent recalls past investigations
(e.g., "Last time you asked about request.py, and this change touches it").
Also provides graph elements for the "Show My Memory Graph" Cytoscape view.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from blastradius.config import config
from blastradius.graph.db import FalkorDBClient

logger = logging.getLogger(__name__)


def sanitize_graph_name(user_id: str) -> str:
    """
    Sanitizes a user ID into a valid FalkorDB graph name.
    FalkorDB graph names can contain alphanumeric characters and underscores.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", user_id.strip())
    if not cleaned:
        return "user_default"
    # Ensure it starts with a letter or underscore
    if cleaned[0].isdigit():
        cleaned = f"u_{cleaned}"
    return cleaned


@dataclass
class MemoryRecallItem:
    """Represents a recalled past interaction relevant to the current query."""
    code_area: str
    past_question: str
    past_timestamp: str
    finding_summary: str
    marked_useful: bool = False
    recall_phrase: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code_area": self.code_area,
            "past_question": self.past_question,
            "past_timestamp": self.past_timestamp,
            "finding_summary": self.finding_summary,
            "marked_useful": self.marked_useful,
            "recall_phrase": self.recall_phrase,
        }


class InMemoryUserMemoryGraph:
    """
    In-memory isolated graph store for a single user.
    Used when FalkorDB is offline, in test environments, or as a cache.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.nodes: dict[str, dict[str, Any]] = {}  # id -> {id, label, type, ...}
        self.edges: list[dict[str, Any]] = []  # {id, source, target, label, ...}

        # Initialize User node
        self.user_node_id = f"User:{user_id}"
        self.nodes[self.user_node_id] = {
            "id": self.user_node_id,
            "label": f"User: {user_id}",
            "type": "User",
            "user_id": user_id,
        }

    def record_query(
        self,
        question: str,
        answer: str,
        touched_areas: list[str],
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        q_id = f"q_{uuid.uuid4().hex[:8]}"
        f_id = f"f_{uuid.uuid4().hex[:8]}"

        # Clean answer snippet for summary
        clean_summary = answer.strip().replace("\n", " ")
        if len(clean_summary) > 160:
            clean_summary = clean_summary[:157] + "..."

        # 1. Question node
        self.nodes[q_id] = {
            "id": q_id,
            "label": question[:32] + ("..." if len(question) > 32 else ""),
            "full_text": question,
            "type": "Question",
            "timestamp": ts,
        }

        # User -> ASKED -> Question
        self.edges.append({
            "id": f"e_asked_{q_id}",
            "source": self.user_node_id,
            "target": q_id,
            "label": "ASKED",
        })

        # 2. Finding node
        self.nodes[f_id] = {
            "id": f_id,
            "label": "Finding" if not paths else f"Finding ({len(paths)} paths)",
            "summary": clean_summary,
            "full_text": answer,
            "paths": paths or [],
            "type": "Finding",
            "marked_useful": False,
            "timestamp": ts,
        }

        # Question -> PRODUCED -> Finding
        self.edges.append({
            "id": f"e_prod_{f_id}",
            "source": q_id,
            "target": f_id,
            "label": "PRODUCED",
        })

        # 3. CodeArea nodes and relationships
        unique_areas = list(dict.fromkeys(touched_areas))
        for area in unique_areas:
            area_id = f"Area:{area}"
            if area_id not in self.nodes:
                area_type = "File" if area.endswith(".py") else "Function"
                self.nodes[area_id] = {
                    "id": area_id,
                    "label": area.split(":")[-1] if ":" in area else area.split("/")[-1],
                    "name": area,
                    "type": "CodeArea",
                    "code_type": area_type,
                }

            # Question -> TOUCHED_AREA -> CodeArea
            self.edges.append({
                "id": f"e_touch_{q_id}_{len(self.edges)}",
                "source": q_id,
                "target": area_id,
                "label": "TOUCHED_AREA",
            })

            # Finding -> RELATES_TO -> CodeArea
            self.edges.append({
                "id": f"e_rel_{f_id}_{len(self.edges)}",
                "source": f_id,
                "target": area_id,
                "label": "RELATES_TO",
            })

        return {
            "user_id": self.user_id,
            "question_id": q_id,
            "finding_id": f_id,
            "touched_areas": unique_areas,
            "timestamp": ts,
        }

    def mark_finding_useful(self, finding_id: str, useful: bool = True) -> bool:
        if finding_id not in self.nodes:
            return False

        self.nodes[finding_id]["marked_useful"] = useful
        if useful:
            self.nodes[finding_id]["label"] = self.nodes[finding_id]["label"].replace(" ⭐", "") + " ⭐"
            # Add MARKED_USEFUL edge if not already present
            edge_id = f"e_useful_{self.user_node_id}_{finding_id}"
            if not any(e["id"] == edge_id for e in self.edges):
                self.edges.append({
                    "id": edge_id,
                    "source": self.user_node_id,
                    "target": finding_id,
                    "label": "MARKED_USEFUL",
                })
        else:
            self.nodes[finding_id]["label"] = self.nodes[finding_id]["label"].replace(" ⭐", "")
            edge_id = f"e_useful_{self.user_node_id}_{finding_id}"
            self.edges = [e for e in self.edges if e["id"] != edge_id]

        return True

    def find_relevant_memories(
        self, current_question: str, current_areas: list[str]
    ) -> list[MemoryRecallItem]:
        recalls: list[MemoryRecallItem] = []
        seen_keys = set()

        clean_q = current_question.lower()
        search_areas = [a.lower() for a in current_areas]

        # Scan code areas in memory
        for node_id, node in self.nodes.items():
            if node.get("type") != "CodeArea":
                continue

            area_name = node.get("name", "")
            area_lower = area_name.lower()
            area_short = (
                area_name.split(":")[-1].lower() if ":" in area_name else area_name.split("/")[-1].lower()
            )

            # Match if current areas match or current question mentions this area
            is_matched = (
                area_lower in search_areas
                or any(sa in area_lower or area_lower in sa for sa in search_areas if sa)
                or area_short in clean_q
                or area_lower in clean_q
            )

            if is_matched:
                # Find past questions that touched this area
                questions_touching = []
                for e in self.edges:
                    if e["label"] == "TOUCHED_AREA" and e["target"] == node_id:
                        q_node = self.nodes.get(e["source"])
                        if q_node:
                            questions_touching.append(q_node)

                for q_node in questions_touching:
                    # Find finding for this question
                    finding_summary = ""
                    marked_useful = False
                    for e in self.edges:
                        if e["label"] == "PRODUCED" and e["source"] == q_node["id"]:
                            f_node = self.nodes.get(e["target"])
                            if f_node:
                                finding_summary = f_node.get("summary", "")
                                marked_useful = f_node.get("marked_useful", False)
                                break

                    key = (area_name, q_node["id"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        q_text = q_node.get("full_text", q_node.get("label", ""))

                        if marked_useful:
                            phrase = (
                                f"Last time you asked about '{area_name}', and you marked this finding as useful: "
                                f"\"{finding_summary}\". This change touches it."
                            )
                        else:
                            phrase = (
                                f"Last time you asked about '{area_name}' (in: \"{q_text}\"), and this change touches it."
                            )

                        recalls.append(
                            MemoryRecallItem(
                                code_area=area_name,
                                past_question=q_text,
                                past_timestamp=q_node.get("timestamp", ""),
                                finding_summary=finding_summary,
                                marked_useful=marked_useful,
                                recall_phrase=phrase,
                            )
                        )

        return recalls

    def get_graph_elements(self) -> dict[str, list[dict[str, Any]]]:
        """Returns nodes and edges formatted for Cytoscape.js rendering."""
        cytoscape_nodes = []
        for n_id, n_data in self.nodes.items():
            cytoscape_nodes.append({
                "group": "nodes",
                "data": {
                    "id": n_id,
                    "label": n_data.get("label", n_id),
                    "type": n_data.get("type", "Node"),
                    "code_type": n_data.get("code_type", ""),
                    "full_text": n_data.get("full_text", ""),
                    "summary": n_data.get("summary", ""),
                    "timestamp": n_data.get("timestamp", ""),
                    "marked_useful": n_data.get("marked_useful", False),
                },
            })

        cytoscape_edges = []
        for e in self.edges:
            cytoscape_edges.append({
                "group": "edges",
                "data": {
                    "id": e["id"],
                    "source": e["source"],
                    "target": e["target"],
                    "label": e["label"],
                },
            })

        return {"nodes": cytoscape_nodes, "edges": cytoscape_edges}


class UserMemoryManager:
    """
    Manages per-user FalkorDB graph memory instances.
    Each user gets their own dedicated graph (graph name = user_id).
    Supports live FalkorDB queries as well as automatic fallback to
    in-memory memory graph instances for high resilience and zero-crash tests.
    """

    def __init__(self, host: str = config.FALKORDB_HOST, port: int = config.FALKORDB_PORT):
        self.host = host
        self.port = port
        self._in_memory_stores: dict[str, InMemoryUserMemoryGraph] = {}
        self._falkordb_clients: dict[str, FalkorDBClient] = {}
        self._is_falkordb_live: bool | None = None

    def _check_falkordb_live(self) -> bool:
        if self._is_falkordb_live is not None:
            return self._is_falkordb_live
        try:
            test_c = FalkorDBClient(host=self.host, port=self.port, graph_name="test_ping")
            test_c.connect().query("RETURN 1")
            self._is_falkordb_live = True
        except Exception:
            self._is_falkordb_live = False
        return self._is_falkordb_live

    def get_falkordb_client_for_user(self, user_id: str) -> FalkorDBClient:
        """Returns or creates a FalkorDB client targeting the user's specific graph name."""
        graph_name = sanitize_graph_name(user_id)
        if graph_name not in self._falkordb_clients:
            self._falkordb_clients[graph_name] = FalkorDBClient(
                host=self.host, port=self.port, graph_name=graph_name
            )
        return self._falkordb_clients[graph_name]

    def get_in_memory_store(self, user_id: str) -> InMemoryUserMemoryGraph:
        """Returns or creates the in-memory graph memory for a user."""
        graph_name = sanitize_graph_name(user_id)
        if graph_name not in self._in_memory_stores:
            self._in_memory_stores[graph_name] = InMemoryUserMemoryGraph(graph_name)
        return self._in_memory_stores[graph_name]

    def init_user_schema(self, user_id: str) -> None:
        """Initializes schema and indices on the user's FalkorDB graph."""
        if not self._check_falkordb_live():
            return
        try:
            client = self.get_falkordb_client_for_user(user_id)
            g = client.connect()
            g.query("CREATE INDEX FOR (u:User) ON (u.id)")
            g.query("CREATE INDEX FOR (q:Question) ON (q.id)")
            g.query("CREATE INDEX FOR (c:CodeArea) ON (c.name)")
            g.query("CREATE INDEX FOR (f:Finding) ON (f.id)")
        except Exception as e:
            logger.debug(f"User schema initialization notice for '{user_id}': {e}")

    def record_query(
        self,
        user_id: str,
        question: str,
        answer: str,
        touched_areas: list[str],
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Stores an interaction in the user's graph memory.
        Updates both in-memory store and live FalkorDB graph (if online).
        """
        clean_user = sanitize_graph_name(user_id)
        # Always update in-memory store first
        mem_store = self.get_in_memory_store(clean_user)
        result = mem_store.record_query(question, answer, touched_areas, paths)

        # Attempt to persist to live FalkorDB if available
        if self._check_falkordb_live():
            try:
                client = self.get_falkordb_client_for_user(clean_user)
                ts = result["timestamp"]
                q_id = result["question_id"]
                f_id = result["finding_id"]

                client.query(
                    """
                    MERGE (u:User {id: $user_id})
                    CREATE (q:Question {id: $q_id, text: $question, timestamp: $ts})
                    CREATE (f:Finding {id: $f_id, text: $answer, timestamp: $ts, marked_useful: false})
                    MERGE (u)-[:ASKED]->(q)
                    MERGE (q)-[:PRODUCED]->(f)
                    """,
                    {
                        "user_id": clean_user,
                        "q_id": q_id,
                        "question": question,
                        "answer": answer,
                        "ts": ts,
                        "f_id": f_id,
                    },
                )

                for area in result["touched_areas"]:
                    client.query(
                        """
                        MATCH (q:Question {id: $q_id}), (f:Finding {id: $f_id}), (u:User {id: $user_id})
                        MERGE (c:CodeArea {name: $area})
                        MERGE (q)-[:TOUCHED_AREA]->(c)
                        MERGE (f)-[:RELATES_TO]->(c)
                        MERGE (u)-[inv:INVESTIGATED]->(c)
                        ON CREATE SET inv.count = 1, inv.last_seen = $ts
                        ON MATCH SET inv.count = inv.count + 1, inv.last_seen = $ts
                        """,
                        {
                            "q_id": q_id,
                            "f_id": f_id,
                            "user_id": clean_user,
                            "area": area,
                            "ts": ts,
                        },
                    )
            except Exception as e:
                logger.warning(f"Could not sync memory to FalkorDB for user '{user_id}': {e}")

        return result

    def mark_finding_useful(self, user_id: str, finding_id: str, useful: bool = True) -> bool:
        """Marks or unmarks a finding as useful in the user's memory graph."""
        clean_user = sanitize_graph_name(user_id)
        mem_store = self.get_in_memory_store(clean_user)
        success = mem_store.mark_finding_useful(finding_id, useful)

        if self._check_falkordb_live():
            try:
                client = self.get_falkordb_client_for_user(clean_user)
                if useful:
                    client.query(
                        """
                        MATCH (u:User {id: $user_id}), (f:Finding {id: $f_id})
                        SET f.marked_useful = true
                        MERGE (u)-[:MARKED_USEFUL]->(f)
                        """,
                        {"user_id": clean_user, "f_id": finding_id},
                    )
                else:
                    client.query(
                        """
                        MATCH (u:User {id: $user_id})-[r:MARKED_USEFUL]->(f:Finding {id: $f_id})
                        SET f.marked_useful = false
                        DELETE r
                        """,
                        {"user_id": clean_user, "f_id": finding_id},
                    )
            except Exception as e:
                logger.warning(f"Could not update marked_useful in FalkorDB: {e}")

        return success

    def get_relevant_memories(
        self, user_id: str, current_question: str, current_areas: list[str]
    ) -> list[MemoryRecallItem]:
        """
        Retrieves relevant memory items for a user given their new question and touched areas.
        Synthesizes human-friendly recall phrases.
        """
        clean_user = sanitize_graph_name(user_id)
        mem_store = self.get_in_memory_store(clean_user)
        return mem_store.find_relevant_memories(current_question, current_areas)

    def get_memory_graph(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """
        Retrieves the complete memory graph for a user formatted for Cytoscape.js.
        """
        clean_user = sanitize_graph_name(user_id)
        mem_store = self.get_in_memory_store(clean_user)
        return mem_store.get_graph_elements()

    def get_memory_summary(self, user_id: str) -> dict[str, Any]:
        """Returns statistics and high-level summary of the user's memory graph."""
        clean_user = sanitize_graph_name(user_id)
        mem_store = self.get_in_memory_store(clean_user)

        total_questions = sum(1 for n in mem_store.nodes.values() if n.get("type") == "Question")
        total_areas = sum(1 for n in mem_store.nodes.values() if n.get("type") == "CodeArea")
        useful_findings = sum(
            1 for n in mem_store.nodes.values() if n.get("type") == "Finding" and n.get("marked_useful")
        )

        areas_list = [n.get("name") for n in mem_store.nodes.values() if n.get("type") == "CodeArea"]

        return {
            "user_id": user_id,
            "graph_name": clean_user,
            "total_questions": total_questions,
            "total_areas": total_areas,
            "useful_findings": useful_findings,
            "tracked_areas": areas_list,
        }

    def clear_memory(self, user_id: str) -> None:
        """Clears memory for a specific user."""
        clean_user = sanitize_graph_name(user_id)
        if clean_user in self._in_memory_stores:
            del self._in_memory_stores[clean_user]

        if self._check_falkordb_live():
            try:
                client = self.get_falkordb_client_for_user(clean_user)
                client.clear()
            except Exception as e:
                logger.warning(f"Could not clear FalkorDB memory for '{user_id}': {e}")


# Global memory manager singleton instance
memory_manager = UserMemoryManager()
