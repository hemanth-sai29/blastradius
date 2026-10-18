"""
tests/test_memory.py - Verification suite for per-user graph memory system.

Verifies:
1. Isolated memory graph per user (graph name = user_id).
2. Question and CodeArea tracking in the user's graph.
3. Marking findings as useful with (User)-[:MARKED_USEFUL]->(Finding).
4. Contextual memory recall when a new question touches a previously investigated area
   (e.g., "last time you asked about request.py, and this change touches it").
5. "Show my memory graph" Cytoscape graph payload structure.
6. Web API endpoints (/api/memory/graph, /api/memory/useful, /api/memory/summary).
"""

import pytest
from fastapi.testclient import TestClient

from memory import UserMemoryManager, sanitize_graph_name
from agent import CodeGraphAgent
from tests.test_agent import AgentTestMockClient
from web_app import app


@pytest.fixture
def memory_mgr():
    """Provides a fresh UserMemoryManager instance."""
    return UserMemoryManager()


@pytest.fixture
def test_agent(memory_mgr):
    """Provides a CodeGraphAgent configured with isolated memory manager."""
    mock_client = AgentTestMockClient()
    return CodeGraphAgent(client=mock_client, read_only=True, memory_manager=memory_mgr)


@pytest.fixture
def api_client():
    return TestClient(app)


def test_sanitize_graph_name():
    assert sanitize_graph_name("alice") == "alice"
    assert sanitize_graph_name("user-123.test") == "user_123_test"
    assert sanitize_graph_name("9user") == "u_9user"
    assert sanitize_graph_name("") == "user_default"


def test_per_user_isolation(memory_mgr):
    """Verifies that each user has a completely separate memory graph."""
    # User Alice asks about request.py
    rec_alice = memory_mgr.record_query(
        user_id="alice",
        question="How does request.py handle headers?",
        answer="request.py parses incoming headers into RequestContext.",
        touched_areas=["request.py"],
    )

    # User Bob asks about db.py
    rec_bob = memory_mgr.record_query(
        user_id="bob",
        question="What database does db.py use?",
        answer="db.py connects to FalkorDB on port 6379.",
        touched_areas=["db.py"],
    )

    # Check Alice's memory graph
    alice_graph = memory_mgr.get_memory_graph("alice")
    alice_node_labels = [n["data"]["label"] for n in alice_graph["nodes"]]
    assert any("alice" in l.lower() for l in alice_node_labels)
    assert any("request.py" in l for l in alice_node_labels)
    assert not any("db.py" in l for l in alice_node_labels)

    # Check Bob's memory graph
    bob_graph = memory_mgr.get_memory_graph("bob")
    bob_node_labels = [n["data"]["label"] for n in bob_graph["nodes"]]
    assert any("bob" in l.lower() for l in bob_node_labels)
    assert any("db.py" in l for l in bob_node_labels)
    assert not any("request.py" in l for l in bob_node_labels)


def test_mark_finding_as_useful(memory_mgr):
    """Verifies marking and unmarking findings as useful."""
    rec = memory_mgr.record_query(
        user_id="alice",
        question="What breaks if connect changes?",
        answer="connect affects query and init_schema.",
        touched_areas=["connect", "blastradius/graph/db.py"],
    )
    finding_id = rec["finding_id"]

    # Initially not marked useful
    summary_before = memory_mgr.get_memory_summary("alice")
    assert summary_before["useful_findings"] == 0

    # Mark useful
    marked = memory_mgr.mark_finding_useful("alice", finding_id, useful=True)
    assert marked is True

    summary_after = memory_mgr.get_memory_summary("alice")
    assert summary_after["useful_findings"] == 1

    # Verify in Cytoscape graph elements
    graph = memory_mgr.get_memory_graph("alice")
    f_node = next(n for n in graph["nodes"] if n["data"]["id"] == finding_id)
    assert f_node["data"]["marked_useful"] is True
    assert "⭐" in f_node["data"]["label"]
    assert any(e["data"]["label"] == "MARKED_USEFUL" for e in graph["edges"])

    # Unmark useful
    unmarked = memory_mgr.mark_finding_useful("alice", finding_id, useful=False)
    assert unmarked is True
    assert memory_mgr.get_memory_summary("alice")["useful_findings"] == 0


@pytest.mark.anyio
async def test_agent_memory_recall_flow(test_agent, memory_mgr):
    """
    Verifies that when a user asks a new question touching an area they previously
    asked about, the agent recalls that context (e.g. 'last time you asked about request.py, and this change touches it').
    """
    user_id = "developer_dave"

    # Turn 1: User asks about login
    q1 = "What breaks if I modify 'login' in auth/service.py?"
    resp1 = await test_agent.ask(q1, user_id=user_id)
    assert resp1.has_answer is True
    assert len(resp1.memory_recalls) == 0  # No past memory yet
    assert resp1.finding_id is not None

    # Mark turn 1 finding as useful
    memory_mgr.mark_finding_useful(user_id, resp1.finding_id, useful=True)

    # Turn 2: User asks a new question touching login / auth/service.py
    q2 = "What breaks if I modify 'login' again?"
    resp2 = await test_agent.ask(q2, user_id=user_id)

    # Verify agent recalled memory from Turn 1
    assert len(resp2.memory_recalls) > 0
    recall_text = resp2.memory_recalls[0]
    assert "login" in recall_text
    assert "Last time you asked about" in recall_text
    assert "touches it" in recall_text
    assert "Memory Recall:" in resp2.answer

    # Verify a different user has NO recall
    resp_other = await test_agent.ask("What breaks if I modify 'login'?", user_id="other_user")
    assert len(resp_other.memory_recalls) == 0


def test_api_memory_endpoints(api_client):
    """Verifies all FastAPI memory REST endpoints."""
    user = "test_api_user"

    # 1. Send chat message to populate memory
    chat_payload = {
        "question": "What breaks if connect in blastradius/graph/db.py changes?",
        "user_id": user,
    }
    chat_res = api_client.post("/api/chat", json=chat_payload)
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["user_id"] == user
    assert "finding_id" in chat_data
    finding_id = chat_data["finding_id"]

    # 2. Get memory summary
    sum_res = api_client.get(f"/api/memory/summary?user_id={user}")
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert sum_data["total_questions"] >= 1
    assert sum_data["total_areas"] >= 1

    # 3. Mark finding as useful
    useful_payload = {"user_id": user, "finding_id": finding_id, "useful": True}
    useful_res = api_client.post("/api/memory/useful", json=useful_payload)
    assert useful_res.status_code == 200
    assert useful_res.json()["marked_useful"] is True

    # 4. Get memory graph for "Show My Memory Graph" view
    graph_res = api_client.get(f"/api/memory/graph?user_id={user}")
    assert graph_res.status_code == 200
    g_data = graph_res.json()
    assert g_data["user_id"] == user
    assert len(g_data["nodes"]) >= 3  # User, Question, CodeArea, Finding
    assert len(g_data["edges"]) >= 2
    node_types = [n["data"]["type"] for n in g_data["nodes"]]
    assert "User" in node_types
    assert "Question" in node_types
    assert "CodeArea" in node_types
    assert "Finding" in node_types

    # 5. Clear memory
    del_res = api_client.delete(f"/api/memory?user_id={user}")
    assert del_res.status_code == 200
    empty_sum = api_client.get(f"/api/memory/summary?user_id={user}").json()
    assert empty_sum["total_questions"] == 0
