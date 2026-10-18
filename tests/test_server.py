"""
tests/test_server.py - Tests for the official MCP Server (server.py).

Verifies:
1. Registration of all 6 tools in the MCP server.
2. Presence of clear LLM-targeted descriptions for autonomous selection.
3. Input validation enforcement via Pydantic & parameter checks.
4. Tool invocation returning standard {"answer": ..., "path": [...]} format.
5. Read-only operation guarantees.
"""

import os
import sys
import pytest
from pydantic import ValidationError

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import create_server
from tests.test_tools import MockFalkorDBClient


@pytest.fixture
def mcp_server_instance():
    """Instantiates the MCP server configured with a mock graph client."""
    mock_client = MockFalkorDBClient()
    return create_server(client=mock_client, read_only=True)


@pytest.mark.anyio
async def test_tools_registration(mcp_server_instance):
    """Verifies that all 6 tools from tools.py are properly registered on the MCP server."""
    tools = await mcp_server_instance.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = [
        "impact_analysis",
        "suggest_reviewers",
        "explain_origin",
        "shortest_path",
        "critical_nodes",
        "find_clusters",
    ]

    for expected in expected_tools:
        assert expected in tool_names, f"Tool '{expected}' should be registered on MCP server."

    assert len(tool_names) == 6


@pytest.mark.anyio
async def test_tool_descriptions_for_llm(mcp_server_instance):
    """Verifies that all tools provide clear, descriptive guidance for LLMs."""
    tools = await mcp_server_instance.list_tools()
    tools_by_name = {t.name: t for t in tools}

    # Verify impact_analysis description
    ia = tools_by_name["impact_analysis"]
    assert "what could break" in ia.description.lower() or "blast radius" in ia.description.lower()

    # Verify suggest_reviewers description
    sr = tools_by_name["suggest_reviewers"]
    assert "review" in sr.description.lower() or "owner" in sr.description.lower()

    # Verify explain_origin description
    eo = tools_by_name["explain_origin"]
    assert "where a function came from" in eo.description.lower() or "commits" in eo.description.lower()

    # Verify shortest_path description
    sp = tools_by_name["shortest_path"]
    assert "how two code elements are connected" in sp.description.lower() or "path" in sp.description.lower()

    # Verify critical_nodes description
    cn = tools_by_name["critical_nodes"]
    assert "critical" in cn.description.lower() or "bottlenecks" in cn.description.lower()

    # Verify find_clusters description
    fc = tools_by_name["find_clusters"]
    assert "modular" in fc.description.lower() or "clusters" in fc.description.lower()


@pytest.mark.anyio
async def test_input_validation(mcp_server_instance):
    """Verifies that invalid parameters are rejected with validation errors."""
    # 1. Depth exceeds maximum (10)
    with pytest.raises(Exception):
        await mcp_server_instance.call_tool("impact_analysis", {"function_name": "login", "depth": 99})

    # 2. Depth less than minimum (1)
    with pytest.raises(Exception):
        await mcp_server_instance.call_tool("impact_analysis", {"function_name": "login", "depth": 0})

    # 3. Empty function name
    with pytest.raises(Exception):
        await mcp_server_instance.call_tool("impact_analysis", {"function_name": "   ", "depth": 3})

    # 4. Empty targets for shortest_path
    with pytest.raises(Exception):
        await mcp_server_instance.call_tool("shortest_path", {"source": "", "target": "auth/jwt.py"})


@pytest.mark.anyio
async def test_tool_execution_contracts(mcp_server_instance):
    """Verifies end-to-end execution of all 6 MCP tools returning standard JSON format."""
    # 1. impact_analysis
    res_ia = await mcp_server_instance.call_tool("impact_analysis", {"function_name": "verify_token", "depth": 2})
    data_ia = res_ia.structured_content or res_ia.content[0].text
    assert "answer" in data_ia
    assert "path" in data_ia
    assert isinstance(data_ia["path"], list)

    # 2. suggest_reviewers
    res_sr = await mcp_server_instance.call_tool("suggest_reviewers", {"file_or_function": "auth/service.py"})
    data_sr = res_sr.structured_content or res_sr.content[0].text
    assert "answer" in data_sr
    assert "path" in data_sr
    assert len(data_sr["answer"]["reviewers"]) > 0

    # 3. explain_origin
    res_eo = await mcp_server_instance.call_tool("explain_origin", {"function_name": "login"})
    data_eo = res_eo.structured_content or res_eo.content[0].text
    assert "answer" in data_eo
    assert "path" in data_eo
    assert len(data_eo["answer"]["issues"]) > 0

    # 4. shortest_path
    res_sp = await mcp_server_instance.call_tool(
        "shortest_path", {"source": "api/routes.py:login_route", "target": "auth/jwt.py:verify_token"}
    )
    data_sp = res_sp.structured_content or res_sp.content[0].text
    assert "answer" in data_sp
    assert data_sp["answer"]["connected"] is True

    # 5. critical_nodes
    res_cn = await mcp_server_instance.call_tool("critical_nodes", {"top_n": 3})
    data_cn = res_cn.structured_content or res_cn.content[0].text
    assert "answer" in data_cn
    assert len(data_cn["answer"]["critical_nodes"]) > 0

    # 6. find_clusters
    res_fc = await mcp_server_instance.call_tool("find_clusters", {})
    data_fc = res_fc.structured_content or res_fc.content[0].text
    assert "answer" in data_fc
    assert len(data_fc["answer"]["clusters"]) > 0


@pytest.mark.anyio
async def test_read_only_enforcement():
    """Verifies that the MCP server enforces read-only operation and blocks write Cypher queries."""
    from server import ReadOnlyGraphClient
    mock_client = MockFalkorDBClient()
    ro_client = ReadOnlyGraphClient(mock_client)

    # 1. Allowed read query
    read_res = ro_client.query("MATCH (n:Function) RETURN n")
    assert read_res is not None

    # 2. Blocked mutation query (CREATE)
    with pytest.raises(PermissionError, match="strictly READ-ONLY"):
        ro_client.query("CREATE (n:Function {name: 'hacked'})")

    # 3. Blocked mutation query (DELETE)
    with pytest.raises(PermissionError, match="strictly READ-ONLY"):
        ro_client.query("MATCH (n) DELETE n")

    # 4. Blocked mutation query (MERGE)
    with pytest.raises(PermissionError, match="strictly READ-ONLY"):
        ro_client.query("MERGE (a:Author {name: 'attacker'})")

