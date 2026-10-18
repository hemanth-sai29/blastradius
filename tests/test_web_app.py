"""
tests/test_web_app.py - Verification suite for FastAPI web backend and endpoints.

Verifies:
1. GET / serves the single-page frontend.
2. GET /api/examples returns the 5 sample questions with metadata.
3. GET /api/graph returns graph nodes and edges for Cytoscape.js.
4. POST /api/chat handles reasoning questions and formats highlighted graph paths.
5. POST /api/chat handles review mode and outputs PR action report.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web_app import app
from agent import CodeGraphAgent
from server import create_server
from tests.test_agent import AgentTestMockClient


@pytest.fixture
def client_with_mock_agent(monkeypatch):
    """Instantiates TestClient with agent backed by in-memory mock client."""
    mock_client = AgentTestMockClient()
    mock_server = create_server(client=mock_client, read_only=True)
    test_agent = CodeGraphAgent(mcp_server=mock_server, client=mock_client, read_only=True)

    # Monkeypatch the global agent instance in web_app
    import web_app
    monkeypatch.setattr(web_app, "agent", test_agent)

    return TestClient(app)


def test_index_page(client_with_mock_agent):
    """Verifies that GET / serves the HTML single-page frontend."""
    resp = client_with_mock_agent.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "BlastRadius" in resp.text
    assert "cy" in resp.text


def test_api_examples(client_with_mock_agent):
    """Verifies that GET /api/examples returns 5 preset examples."""
    resp = client_with_mock_agent.get("/api/examples")
    assert resp.status_code == 200
    data = resp.json()
    assert "examples" in data
    assert len(data["examples"]) == 5

    # Verify key questions are represented
    questions = [ex["question"] for ex in data["examples"]]
    assert any("connect" in q for q in questions)
    assert any("load_history" in q for q in questions)
    assert any("verify_token" in q for q in questions)
    assert any("login_route" in q for q in questions)
    assert any("legacy_billing_migration_v0" in q for q in questions)


def test_api_graph(client_with_mock_agent):
    """Verifies that GET /api/graph returns graph nodes and edges for Cytoscape."""
    resp = client_with_mock_agent.get("/api/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0


def test_api_chat_ask(client_with_mock_agent):
    """Verifies POST /api/chat with a standard question."""
    payload = {"question": "What breaks if I change 'verify_token' and who should review it?"}
    resp = client_with_mock_agent.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["has_answer"] is True
    assert "verify_token" in data["question"]
    assert len(data["tools_called"]) >= 1
    assert "highlighted_elements" in data
    assert len(data["highlighted_elements"]["nodes"]) > 0


def test_api_chat_review_action(client_with_mock_agent):
    """Verifies POST /api/chat with review action mode."""
    payload = {"question": "Review PR for function 'verify_token'", "mode": "review"}
    resp = client_with_mock_agent.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert "action_report" in data
    report = data["action_report"]
    assert report is not None
    assert report["risk_level"] == "HIGH RISK"
    assert "🚨 HIGH RISK" in report["risk_badge"]
    assert len(report["best_reviewers"]) == 2
    assert "Alice Smith" in report["best_reviewers"][0]["name"]
    assert "## 💥 BlastRadius PR Impact & Risk Assessment" in report["markdown_comment"]
    assert data["is_dry_run"] is True
