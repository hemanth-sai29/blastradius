"""
Step 4 Verification Test: Official MCP Server Tools.
Tests registration, tool execution, and MCP communication.
"""

import sys
import os
import asyncio
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from blastradius.mcp_server.server import create_mcp_server


async def async_test_step4():
    print("=" * 60)
    print("TEST STEP 4: Official MCP Server Protocol & Tools")
    print("=" * 60)

    server = create_mcp_server()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    print(f"[OK] MCP Server instantiated. Registered tools ({len(tool_names)}):")
    for name in tool_names:
        print(f"     - {name}")

    expected_tools = [
        "ingest_codebase",
        "get_blast_radius",
        "get_shortest_path",
        "get_central_hubs",
        "discover_tests",
        "recommend_reviewers",
        "query_graph",
    ]
    for exp in expected_tools:
        assert exp in tool_names, f"Expected MCP tool '{exp}' not found!"

    # 1. Test Ingestion Tool via MCP
    print("\n[*] Invoking MCP tool: 'ingest_codebase'...")
    res_ingest = await server.call_tool(
        "ingest_codebase", {"repo_path": ".", "clear_existing": True}
    )
    assert not res_ingest.is_error, f"MCP tool error: {res_ingest}"
    ingest_data = res_ingest.structured_content or json.loads(res_ingest.content[0].text)
    print(f"[OK] Ingestion tool returned: {ingest_data['status']}")
    print(f"     Stats: {ingest_data['stats']}")

    # 2. Test Blast Radius Tool via MCP
    print("\n[*] Invoking MCP tool: 'get_blast_radius' for 'connect'...")
    res_blast = await server.call_tool(
        "get_blast_radius", {"target_symbol": "connect", "max_depth": 3}
    )
    assert not res_blast.is_error, f"MCP tool error: {res_blast}"
    blast_data = res_blast.structured_content or json.loads(res_blast.content[0].text)
    print(f"[OK] Blast Radius tool returned impact score: {blast_data['impact_score']}/100")
    print(f"     Impacted functions: {blast_data['total_impacted_functions']}")

    # 3. Test Shortest Path Tool via MCP
    print("\n[*] Invoking MCP tool: 'get_shortest_path'...")
    res_sp = await server.call_tool(
        "get_shortest_path",
        {
            "source": "blastradius/config.py:_detect_falkordb_host",
            "target": "blastradius/config.py:_is_port_open",
        },
    )
    assert not res_sp.is_error, f"MCP tool error: {res_sp}"
    sp_data = res_sp.structured_content or json.loads(res_sp.content[0].text)
    print(f"[OK] Shortest Path tool returned: found={sp_data['found']}, hops={sp_data['hops']}")
    print(f"     Path: {sp_data['path_explanation']}")
    assert sp_data["found"], "Shortest path should be found!"

    # 4. Test Central Hubs Tool via MCP
    print("\n[*] Invoking MCP tool: 'get_central_hubs'...")
    res_hubs = await server.call_tool("get_central_hubs", {"limit": 3})
    assert not res_hubs.is_error, f"MCP tool error: {res_hubs}"
    hubs_data = res_hubs.structured_content or json.loads(res_hubs.content[0].text)
    # Could be list or dict wrapping list
    hub_list = hubs_data if isinstance(hubs_data, list) else hubs_data.get("result", [])
    print(f"[OK] Central Hubs tool returned {len(hub_list)} hubs:")
    for h in hub_list:
        print(f"     - {h['symbol']} (score: {h['hub_score']})")

    # 5. Test Reviewer Recommendation Tool via MCP
    print("\n[*] Invoking MCP tool: 'recommend_reviewers'...")
    res_recs = await server.call_tool(
        "recommend_reviewers", {"files": ["blastradius/graph/db.py"], "limit": 2}
    )
    assert not res_recs.is_error, f"MCP tool error: {res_recs}"
    recs_data = res_recs.structured_content or json.loads(res_recs.content[0].text)
    rec_list = recs_data if isinstance(recs_data, list) else recs_data.get("result", [])
    print(f"[OK] Recommend Reviewers returned {len(rec_list)} reviewers:")
    for r in rec_list:
        print(f"     - {r['author_name']} <{r['author_email']}> (score: {r['score']})")

    print("\n>>> STEP 4 PASSED! Official MCP Server successfully tested and verified. <<<\n")


def test_step4():
    asyncio.run(async_test_step4())


if __name__ == "__main__":
    test_step4()
