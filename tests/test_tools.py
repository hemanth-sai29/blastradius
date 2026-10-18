"""
tests/test_tools.py - Pytest Verification Suite for tools.py.

Tests all 6 Cypher graph tools on a small test graph:
1. impact_analysis
2. suggest_reviewers
3. explain_origin
4. shortest_path
5. critical_nodes
6. find_clusters
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

from blastradius.graph.db import FalkorDBClient
from tools import (
    impact_analysis,
    suggest_reviewers,
    explain_origin,
    shortest_path,
    critical_nodes,
    find_clusters,
)


class MockPathNode:
    def __init__(self, labels, properties, node_id=1):
        self.labels = labels
        self.properties = properties
        self.id = node_id


class MockPathEdge:
    def __init__(self, relation="CALLS"):
        self.relation = relation
        self.type = relation


class MockPath:
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges

    def nodes(self):
        return self._nodes

    def edges(self):
        return self._edges

    def __str__(self):
        parts = []
        for i, n in enumerate(self._nodes):
            name = (
                n.properties.get("full_name")
                or n.properties.get("path")
                or n.properties.get("name")
                or n.properties.get("id")
                or n.properties.get("hash")
                or str(n.id)
            )
            lbl = n.labels[0] if n.labels else "Node"
            parts.append(f"[{lbl}:{name}]")
            if i < len(self._edges):
                parts.append(f"--({self._edges[i].relation})-->")
        return " ".join(parts)


class MockQueryResult:
    def __init__(self, result_set):
        self.result_set = result_set


class MockFalkorDBClient:
    """
    In-memory graph mock simulating FalkorDB query results for a small test repository graph:
      File: auth/service.py, auth/jwt.py, api/routes.py, billing/payment.py
      Function: login_route -> login -> verify_token -> decode_token
      Function: checkout -> verify_token
      Author: Alice Smith, Bob Jones
      Commit: c101 (fixes #101), c102 (fixes #102)
      Issue: #101, #102
      OWNS: Alice OWNS auth/service.py, Bob OWNS auth/jwt.py
    """

    def __init__(self, graph_name: str = "mock_small_graph"):
        self.graph_name = graph_name

    def clear(self):
        pass

    def query(self, cypher: str, params: dict | None = None) -> MockQueryResult:
        params = params or {}
        q = cypher.strip()

        # 1. impact_analysis callers
        if "MATCH p = (caller:Function)-[:CALLS*" in q:
            name = params.get("name", "")
            if "verify_token" in name:
                p1 = MockPath(
                    [
                        MockPathNode(["Function"], {"full_name": "auth/service.py:login", "file_path": "auth/service.py"}),
                        MockPathNode(["Function"], {"full_name": "auth/jwt.py:verify_token", "file_path": "auth/jwt.py"}),
                    ],
                    [MockPathEdge("CALLS")],
                )
                p2 = MockPath(
                    [
                        MockPathNode(["Function"], {"full_name": "api/routes.py:login_route", "file_path": "api/routes.py"}),
                        MockPathNode(["Function"], {"full_name": "auth/service.py:login", "file_path": "auth/service.py"}),
                        MockPathNode(["Function"], {"full_name": "auth/jwt.py:verify_token", "file_path": "auth/jwt.py"}),
                    ],
                    [MockPathEdge("CALLS"), MockPathEdge("CALLS")],
                )
                return MockQueryResult([
                    ["auth/service.py:login", "auth/service.py", 1, p1],
                    ["api/routes.py:login_route", "api/routes.py", 2, p2],
                ])
            elif "login" in name:
                p = MockPath(
                    [
                        MockPathNode(["Function"], {"full_name": "api/routes.py:login_route", "file_path": "api/routes.py"}),
                        MockPathNode(["Function"], {"full_name": "auth/service.py:login", "file_path": "auth/service.py"}),
                    ],
                    [MockPathEdge("CALLS")],
                )
                return MockQueryResult([["api/routes.py:login_route", "api/routes.py", 1, p]])
            return MockQueryResult([])

        # 1b. impact_analysis importers
        if "MATCH p = (importer:File)-[:IMPORTS*" in q:
            p_imp = MockPath(
                [
                    MockPathNode(["File"], {"path": "api/routes.py"}),
                    MockPathNode(["File"], {"path": "auth/service.py"}),
                ],
                [MockPathEdge("IMPORTS")],
            )
            return MockQueryResult([["api/routes.py", 1, p_imp]])

        # 2. suggest_reviewers OWNS
        if "MATCH p = (a:Author)-[o:OWNS]->(f)" in q:
            p_owns = MockPath(
                [
                    MockPathNode(["Author"], {"name": "Alice Smith", "email": "alice@company.com"}),
                    MockPathNode(["File"], {"path": "auth/service.py"}),
                ],
                [MockPathEdge("OWNS")],
            )
            return MockQueryResult([
                ["Alice Smith", "alice@company.com", 32.5, 3, 25, p_owns]
            ])

        # 2b. suggest_reviewers history
        if "MATCH p = (a:Author)-[:AUTHORED]->(cm:Commit)-[m:MODIFIED|MODIFIED_BY]->(f)" in q:
            p_auth = MockPath(
                [
                    MockPathNode(["Author"], {"name": "Alice Smith", "email": "alice@company.com"}),
                    MockPathNode(["Commit"], {"hash": "c101", "short_hash": "c101"}),
                    MockPathNode(["File"], {"path": "auth/service.py"}),
                ],
                [MockPathEdge("AUTHORED"), MockPathEdge("MODIFIED_BY")],
            )
            return MockQueryResult([
                ["Alice Smith", "alice@company.com", 3, 105, p_auth]
            ])

        # 3. explain_origin
        if "MATCH p_cm = (cm:Commit)-[m:MODIFIED|MODIFIED_BY]->(f)" in q:
            p_cm = MockPath(
                [
                    MockPathNode(["Commit"], {"hash": "c101"}),
                    MockPathNode(["File"], {"path": "auth/service.py"}),
                    MockPathNode(["Function"], {"full_name": "auth/service.py:login"}),
                ],
                [MockPathEdge("MODIFIED_BY"), MockPathEdge("CONTAINS")],
            )
            p_auth = MockPath(
                [
                    MockPathNode(["Author"], {"email": "alice@company.com"}),
                    MockPathNode(["Commit"], {"hash": "c101"}),
                ],
                [MockPathEdge("AUTHORED")],
            )
            p_issue = MockPath(
                [
                    MockPathNode(["Commit"], {"hash": "c101"}),
                    MockPathNode(["Issue"], {"id": "#101"}),
                ],
                [MockPathEdge("FIXES")],
            )
            return MockQueryResult([
                [
                    "auth/service.py:login",
                    "auth/service.py",
                    "Alice Smith",
                    "alice@company.com",
                    "c101hash",
                    "c101",
                    "Implement login function (fixes #101)",
                    "#101",
                    "Authentication issue #101",
                    p_cm,
                    p_auth,
                    p_issue,
                ]
            ])

        # 4. shortest_path
        if "MATCH p = (src)-[:CALLS|IMPORTS|CONTAINS*1..8]->(dst)" in q or "MATCH p = (src)-[*1..8]-(dst)" in q:
            p_short = MockPath(
                [
                    MockPathNode(["Function"], {"full_name": "api/routes.py:login_route"}),
                    MockPathNode(["Function"], {"full_name": "auth/service.py:login"}),
                    MockPathNode(["Function"], {"full_name": "auth/jwt.py:verify_token"}),
                ],
                [MockPathEdge("CALLS"), MockPathEdge("CALLS")],
            )
            return MockQueryResult([[p_short, 2]])

        # 5. critical_nodes
        if "WITH fn, in_degree, out_degree, (in_degree * 3.0 + out_degree * 1.0) AS centrality_score" in q:
            p_crit = MockPath(
                [
                    MockPathNode(["Function"], {"full_name": "auth/service.py:login"}),
                    MockPathNode(["Function"], {"full_name": "auth/jwt.py:verify_token"}),
                ],
                [MockPathEdge("CALLS")],
            )
            return MockQueryResult([
                [
                    "auth/jwt.py:verify_token",
                    "verify_token",
                    "auth/jwt.py",
                    3,
                    1,
                    10.0,
                    [p_crit],
                ],
                [
                    "auth/service.py:login",
                    "login",
                    "auth/service.py",
                    1,
                    1,
                    4.0,
                    [p_crit],
                ],
            ])

        # 6. find_clusters
        if "MATCH (f:File)" in q and "imp_paths + call_paths AS related_paths" in q:
            p_imp = MockPath(
                [
                    MockPathNode(["File"], {"path": "auth/service.py"}),
                    MockPathNode(["File"], {"path": "auth/jwt.py"}),
                ],
                [MockPathEdge("IMPORTS")],
            )
            return MockQueryResult([
                [
                    "auth/service.py",
                    ["auth/jwt.py"],
                    ["login"],
                    [p_imp],
                ],
                [
                    "auth/jwt.py",
                    [],
                    ["verify_token", "decode_token"],
                    [],
                ],
                [
                    "api/routes.py",
                    ["auth/service.py"],
                    ["login_route"],
                    [p_imp],
                ],
            ])

        return MockQueryResult([])


@pytest.fixture
def small_test_graph():
    """
    Provides a small test graph client.
    Tests against FalkorDB if connected, otherwise uses MockFalkorDBClient.
    """
    # Check if FalkorDB is live
    live_client = FalkorDBClient(graph_name="test_tools_fixture")
    try:
        live_client.connect()
        # Ping test
        res = live_client.query("RETURN 1")
        if res and res.result_set:
            # Set up live small test graph
            live_client.clear()
            setup_cypher = """
            CREATE (f1:File {path: 'auth/service.py', name: 'service.py'})
            CREATE (f2:File {path: 'auth/jwt.py', name: 'jwt.py'})
            CREATE (f3:File {path: 'api/routes.py', name: 'routes.py'})
            CREATE (fn1:Function {name: 'login', full_name: 'auth/service.py:login', file_path: 'auth/service.py'})
            CREATE (fn2:Function {name: 'verify_token', full_name: 'auth/jwt.py:verify_token', file_path: 'auth/jwt.py'})
            CREATE (fn3:Function {name: 'login_route', full_name: 'api/routes.py:login_route', file_path: 'api/routes.py'})
            CREATE (f1)-[:CONTAINS]->(fn1)
            CREATE (f2)-[:CONTAINS]->(fn2)
            CREATE (f3)-[:CONTAINS]->(fn3)
            CREATE (f3)-[:IMPORTS]->(f1)
            CREATE (f1)-[:IMPORTS]->(f2)
            CREATE (fn3)-[:CALLS]->(fn1)
            CREATE (fn1)-[:CALLS]->(fn2)
            CREATE (a:Author {name: 'Alice Smith', email: 'alice@company.com'})
            CREATE (c:Commit {hash: 'c101hash', short_hash: 'c101', message: 'Initial login (fixes #101)'})
            CREATE (i:Issue {id: '#101', title: 'Issue 101'})
            CREATE (a)-[:AUTHORED]->(c)
            CREATE (c)-[:MODIFIED_BY {lines: 45}]->(f1)
            CREATE (c)-[:FIXES]->(i)
            CREATE (a)-[:OWNS {score: 30.5, commits: 3, lines_changed: 45}]->(f1)
            """
            live_client.query(setup_cypher)
            yield live_client
            live_client.clear()
            return
    except Exception:
        pass

    # Fallback to MockFalkorDBClient
    yield MockFalkorDBClient()


def test_impact_analysis(small_test_graph):
    """Verifies downstream blast radius over CALLS and IMPORTS in reverse."""
    res = impact_analysis("login", depth=3, client=small_test_graph)

    # 1. Format check
    assert isinstance(res, dict)
    assert "answer" in res
    assert "path" in res
    assert isinstance(res["path"], list)
    assert len(res["path"]) > 0

    # 2. Answer fields
    answer = res["answer"]
    assert answer["target"] == "login"
    assert "affected_functions" in answer
    assert "affected_files" in answer
    assert len(answer["affected_functions"]) > 0
    assert any("login_route" in fn for fn in answer["affected_functions"])

    # 3. Path inspection
    assert any("CALLS" in p for p in res["path"])


def test_suggest_reviewers(small_test_graph):
    """Verifies reviewer recommendations from OWNS and commit history."""
    res = suggest_reviewers("auth/service.py", client=small_test_graph)

    # 1. Format check
    assert isinstance(res, dict)
    assert "answer" in res
    assert "path" in res
    assert isinstance(res["path"], list)

    # 2. Reviewer data
    answer = res["answer"]
    assert answer["target"] == "auth/service.py"
    assert "reviewers" in answer
    assert len(answer["reviewers"]) > 0

    top_reviewer = answer["reviewers"][0]
    assert "name" in top_reviewer
    assert "email" in top_reviewer
    assert top_reviewer["email"] == "alice@company.com"

    # 3. Path check
    assert len(res["path"]) > 0
    assert any("alice@company.com" in p or "Author" in p for p in res["path"])


def test_explain_origin(small_test_graph):
    """Verifies origin tracing back to Commits, Issues ('fixes #101'), and Authors."""
    res = explain_origin("login", client=small_test_graph)

    # 1. Format check
    assert isinstance(res, dict)
    assert "answer" in res
    assert "path" in res

    # 2. Answer data
    answer = res["answer"]
    assert answer["function"] == "login"
    assert len(answer["authors"]) > 0
    assert answer["authors"][0]["email"] == "alice@company.com"

    assert len(answer["commits"]) > 0
    assert "c101" in answer["commits"][0]["hash"] or "c101" in answer["commits"][0]["short_hash"]

    assert len(answer["issues"]) > 0
    assert answer["issues"][0]["id"] == "#101"

    # 3. Path verification
    assert len(res["path"]) > 0
    assert any("Issue" in p or "FIXES" in p or "AUTHORED" in p for p in res["path"])


def test_shortest_path(small_test_graph):
    """Verifies shortest path between two code elements."""
    res = shortest_path("api/routes.py:login_route", "auth/jwt.py:verify_token", client=small_test_graph)

    # 1. Format check
    assert isinstance(res, dict)
    assert "answer" in res
    assert "path" in res

    # 2. Answer data
    answer = res["answer"]
    assert answer["connected"] is True
    assert answer["hops"] >= 1
    assert "login_route" in answer["source"]
    assert "verify_token" in answer["target"]

    # 3. Path verification
    assert len(res["path"]) > 0
    assert any("login" in res["path"][0] for _ in [1])


def test_critical_nodes(small_test_graph):
    """Verifies degree centrality / PageRank ranking for architectural risk."""
    res = critical_nodes(top_n=3, client=small_test_graph)

    # 1. Format check
    assert isinstance(res, dict)
    assert "answer" in res
    assert "path" in res

    # 2. Answer data
    answer = res["answer"]
    assert "critical_nodes" in answer
    assert len(answer["critical_nodes"]) > 0

    top_node = answer["critical_nodes"][0]
    assert "symbol" in top_node
    assert "centrality_score" in top_node
    assert "in_degree" in top_node
    assert "risk_tier" in top_node
    assert top_node["in_degree"] >= 1

    # 3. Path check
    assert len(res["path"]) > 0


def test_find_clusters(small_test_graph):
    """Verifies community detection grouping modules and dependency boundaries."""
    res = find_clusters(client=small_test_graph)

    # 1. Format check
    assert isinstance(res, dict)
    assert "answer" in res
    assert "path" in res

    # 2. Answer data
    answer = res["answer"]
    assert "clusters" in answer
    assert len(answer["clusters"]) > 0

    auth_cluster = None
    for c in answer["clusters"]:
        if "auth" in c["module"] or "auth" in c["cluster_id"]:
            auth_cluster = c
            break

    assert auth_cluster is not None
    assert len(auth_cluster["files"]) > 0
    assert any("auth/service.py" in f for f in auth_cluster["files"])
