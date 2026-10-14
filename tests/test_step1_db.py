"""
Step 1 Verification Test: FalkorDB Connection & Path Formatting.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from blastradius.graph.db import FalkorDBClient, format_path


def test_step1():
    print("=" * 60)
    print("TEST STEP 1: FalkorDB Connection & Schema Setup")
    print("=" * 60)

    client = FalkorDBClient(graph_name="test_blastradius_step1")
    g = client.connect()
    print(f"[OK] Successfully connected to FalkorDB graph '{client.graph_name}'")

    client.clear()
    client.init_schema()
    print("[OK] Initialized schema and created indices")

    create_query = """
    CREATE (f1:File {path: 'auth/service.py', name: 'service.py', lines: 120})
    CREATE (fn1:Function {name: 'login', full_name: 'auth/service.py:login', lineno: 42})
    CREATE (fn2:Function {name: 'verify_token', full_name: 'auth/jwt.py:verify_token', lineno: 15})
    CREATE (f2:File {path: 'auth/jwt.py', name: 'jwt.py', lines: 80})
    CREATE (f1)-[:CONTAINS]->(fn1)
    CREATE (f2)-[:CONTAINS]->(fn2)
    CREATE (fn1)-[:CALLS]->(fn2)
    CREATE (f1)-[:IMPORTS]->(f2)
    """
    client.query(create_query)
    print("[OK] Inserted sample nodes and edges")

    path_query = """
    MATCH p = (source:Function {name: 'login'})-[:CALLS*1..3]->(target:Function)
    RETURN p, source.name, target.name
    """
    res = client.query(path_query)
    assert len(res.result_set) > 0, "Path query returned no results!"

    path_obj = res.result_set[0][0]
    formatted = format_path(path_obj)
    print(f"[OK] Query returned path:")
    print(f"     Raw: {path_obj}")
    print(f"     Formatted: {formatted}")
    assert "login" in formatted and "verify_token" in formatted and "CALLS" in formatted

    client.clear()
    print("[OK] Cleaned up test graph")
    print("\n>>> STEP 1 PASSED! FalkorDB is ready. <<<\n")


if __name__ == "__main__":
    test_step1()
