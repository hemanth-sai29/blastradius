"""
tests/test_agent.py - Comprehensive verification suite for agent.py.

Verifies:
1. Single-tool dispatch (e.g. impact_analysis, explain_origin).
2. Multi-tool composite dispatch (e.g. impact + suggest_reviewers, shortest_path + critical_nodes).
3. Contract enforcement: (1) plain-language answer, (2) exact graph paths, (3) tools called & why.
4. Zero-hallucination / honest negative answers when the graph has no data.
"""

import os
import sys
import pytest

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent import CodeGraphAgent, AgentResponse
from server import create_server
from tests.test_tools import (
    MockFalkorDBClient,
    MockQueryResult,
    MockPath,
    MockPathNode,
    MockPathEdge,
)


class AgentTestMockClient(MockFalkorDBClient):
    """Extends MockFalkorDBClient to return empty results for non-existent and disconnected symbols."""

    def query(self, cypher: str, params: dict | None = None):
        params = params or {}
        q = cypher.strip()

        # Handle nonexistent symbol queries
        for val in params.values():
            if "nonexistent" in str(val) or "unconnected" in str(val):
                return MockQueryResult([])

        # Handle importers query for nonexistent targets
        if "MATCH p = (importer:File)-[:IMPORTS*" in q:
            name = params.get("name", "")
            if name and name not in ["login", "verify_token", "auth/service.py:login"]:
                return MockQueryResult([])

        # Provide 2 distinct reviewers for suggest_reviewers history query
        if "MATCH p = (a:Author)-[:AUTHORED]->(cm:Commit)-[m:MODIFIED|MODIFIED_BY]->(f)" in q:
            target = params.get("target", "")
            if "nonexistent" not in str(target):
                p_auth1 = MockPath(
                    [
                        MockPathNode(["Author"], {"name": "Alice Smith", "email": "alice@company.com"}),
                        MockPathNode(["Commit"], {"hash": "c101", "short_hash": "c101"}),
                        MockPathNode(["File"], {"path": "auth/service.py"}),
                    ],
                    [MockPathEdge("AUTHORED"), MockPathEdge("MODIFIED_BY")],
                )
                p_auth2 = MockPath(
                    [
                        MockPathNode(["Author"], {"name": "Bob Jones", "email": "bob@company.com"}),
                        MockPathNode(["Commit"], {"hash": "c102", "short_hash": "c102"}),
                        MockPathNode(["File"], {"path": "auth/jwt.py"}),
                    ],
                    [MockPathEdge("AUTHORED"), MockPathEdge("MODIFIED_BY")],
                )
                return MockQueryResult([
                    ["Alice Smith", "alice@company.com", 3, 105, p_auth1],
                    ["Bob Jones", "bob@company.com", 2, 80, p_auth2],
                ])

        return super().query(cypher, params)


@pytest.fixture
def mock_agent():
    """Builds a CodeGraphAgent backed by the in-memory AgentTestMockClient."""
    mock_client = AgentTestMockClient()
    server = create_server(client=mock_client, read_only=True)
    return CodeGraphAgent(mcp_server=server, client=mock_client, read_only=True)


@pytest.mark.anyio
async def test_agent_single_tool_impact(mock_agent):
    """Verifies single-tool dispatch for impact analysis."""
    question = "What breaks if I change 'login'?"
    resp: AgentResponse = await mock_agent.ask(question)

    assert resp.has_answer is True
    assert len(resp.tools_called) == 1
    assert resp.tools_called[0].tool == "impact_analysis"
    assert "login" in resp.tools_called[0].arguments["function_name"]
    assert "Downstream Impact" in resp.answer
    assert len(resp.paths) > 0
    assert any("[Function:auth/service.py:login]" in p for p in resp.paths)


@pytest.mark.anyio
async def test_agent_single_tool_origin(mock_agent):
    """Verifies single-tool dispatch for explain_origin."""
    question = "Where did function 'login' come from and who introduced it?"
    resp: AgentResponse = await mock_agent.ask(question)

    assert resp.has_answer is True
    assert len(resp.tools_called) == 1
    assert resp.tools_called[0].tool == "explain_origin"
    assert "Alice Smith" in resp.answer
    assert "Origin Provenance" in resp.answer
    assert len(resp.paths) > 0


@pytest.mark.anyio
async def test_agent_multi_tool_impact_and_reviewers(mock_agent):
    """Verifies multi-tool dispatch when question asks about both impact and reviewers."""
    question = "What breaks if I change 'verify_token' and who should review it?"
    resp: AgentResponse = await mock_agent.ask(question)

    assert resp.has_answer is True
    assert len(resp.tools_called) == 2
    tool_names = [t.tool for t in resp.tools_called]
    assert "impact_analysis" in tool_names
    assert "suggest_reviewers" in tool_names

    # Check that both answers are synthesized
    assert "Downstream Impact" in resp.answer
    assert "Suggested Reviewers" in resp.answer

    # Check graph paths collected across both tools
    assert len(resp.paths) >= 2

    # Check rationale recorded for each tool
    for record in resp.tools_called:
        assert len(record.why) > 10


@pytest.mark.anyio
async def test_agent_multi_tool_path_and_critical_nodes(mock_agent):
    """Verifies multi-tool dispatch for shortest path tracing and critical bottlenecks."""
    question = (
        "How does 'api/routes.py:login_route' connect to 'auth/jwt.py:verify_token', "
        "and what are the critical bottlenecks in the repo?"
    )
    resp: AgentResponse = await mock_agent.ask(question)

    assert resp.has_answer is True
    assert len(resp.tools_called) == 2
    tool_names = [t.tool for t in resp.tools_called]
    assert "shortest_path" in tool_names
    assert "critical_nodes" in tool_names

    assert "Shortest Path" in resp.answer
    assert "Critical Hubs" in resp.answer
    assert len(resp.paths) > 0


@pytest.mark.anyio
async def test_agent_negative_answer_no_guessing(mock_agent):
    """Verifies that the agent refuses to guess when the graph has no answer for a symbol."""
    question = "What breaks if I modify 'nonexistent_ghost_function'?"
    resp: AgentResponse = await mock_agent.ask(question)

    assert resp.has_answer is False
    assert len(resp.tools_called) == 1
    assert resp.tools_called[0].tool == "impact_analysis"
    assert len(resp.paths) == 0

    # Must explicitly state that the graph has no answer instead of hallucinating
    assert "NO answer" in resp.answer
    assert "nonexistent_ghost_function" in resp.answer
    assert "Rather than guessing" in resp.answer


@pytest.mark.anyio
async def test_agent_disconnected_path_no_guessing(mock_agent):
    """Verifies that the agent reports no connecting path when symbols are disconnected."""
    question = "What is the shortest path between 'auth/service.py' and 'unconnected_subsystem'?"
    resp: AgentResponse = await mock_agent.ask(question)

    assert len(resp.tools_called) == 1
    assert resp.tools_called[0].tool == "shortest_path"
    assert "The graph contains NO path connecting" in resp.answer


@pytest.mark.anyio
async def test_action_high_risk_flagging(mock_agent):
    """Verifies that a function with high blast radius is flagged as HIGH RISK."""
    report = await mock_agent.run_pr_actions("verify_token", dry_run=True)

    assert report.risk_level == "HIGH RISK"
    assert "🚨 HIGH RISK" in report.risk_badge
    assert len(report.affected_functions) >= 2
    assert "High blast radius triggered" in report.risk_reason
    assert report.dry_run is True


@pytest.mark.anyio
async def test_action_suggest_2_reviewers_with_graph_evidence(mock_agent):
    """Verifies that the agent suggests exactly the 2 best reviewers with concrete graph evidence."""
    report = await mock_agent.run_pr_actions("verify_token", dry_run=True)

    assert len(report.best_reviewers) == 2
    rev1, rev2 = report.best_reviewers[0], report.best_reviewers[1]

    # Reviewer 1
    assert rev1.name == "Alice Smith"
    assert rev1.email == "alice@company.com"
    assert "OWNS" in rev1.graph_evidence or "AUTHORED" in rev1.graph_evidence
    assert rev1.score > 0

    # Reviewer 2
    assert rev2.name is not None
    assert len(rev2.graph_evidence) > 10

    # Ensure each reviewer contains concrete graph evidence
    for r in report.best_reviewers:
        assert len(r.graph_evidence) > 15
        assert "Author:" in r.graph_evidence or "OWNS" in r.graph_evidence or "Commit" in r.graph_evidence


@pytest.mark.anyio
async def test_action_markdown_pr_comment_generation(mock_agent):
    """Verifies generation of a ready-to-post GitHub PR comment in Markdown with all required sections."""
    report = await mock_agent.run_pr_actions("verify_token", dry_run=True)

    comment = report.markdown_comment
    assert "## 💥 BlastRadius PR Impact & Risk Assessment" in comment
    assert "🚨 HIGH RISK" in comment
    assert "Target Modified Function" in comment
    assert "Affected Functions in Blast Zone" in comment
    assert "2 Best Suggested Reviewers (with Graph Evidence)" in comment
    assert "Alice Smith" in comment
    assert "Graph Evidence" in comment
    assert "Multi-Hop Graph Path(s) Traversed" in comment
    assert "Reviewer Checklist" in comment


@pytest.mark.anyio
async def test_action_dry_run_default_preview(mock_agent):
    """Verifies that actions run in dry-run mode by default and output a complete preview."""
    report = await mock_agent.run_pr_actions("verify_token")

    assert report.dry_run is True
    preview = report.format_preview()
    assert "[DRY RUN PREVIEW" in preview
    assert "[ACTION 1: RISK ASSESSMENT]" in preview
    assert "[ACTION 2: 2 BEST SUGGESTED REVIEWERS (WITH GRAPH EVIDENCE)]" in preview
    assert "[ACTION 3: READY-TO-POST GITHUB PR COMMENT (MARKDOWN)]" in preview
    assert "DRY RUN NOTICE" in preview

    # Actions list should show PREVIEW status
    for action in report.actions:
        assert "PREVIEW" in action.status


@pytest.mark.anyio
async def test_action_execute_mode(mock_agent, tmp_path):
    """Verifies that passing dry_run=False executes the action and writes the comment file."""
    out_file = str(tmp_path / "test_pr_comment.md")
    report = await mock_agent.run_pr_actions("verify_token", dry_run=False, output_file=out_file)

    assert report.dry_run is False
    assert os.path.exists(out_file)

    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "## 💥 BlastRadius PR Impact & Risk Assessment" in content

    # All actions should have status EXECUTED
    for action in report.actions:
        assert action.status == "EXECUTED"

