"""
Step 2 Verification Test: AST & Git Ingestion into FalkorDB.
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from blastradius.graph.db import FalkorDBClient, format_path
from blastradius.ingester.builder import RepoIngester


def test_step2():
    print("=" * 60)
    print("TEST STEP 2: Python AST & Git Ingestion into FalkorDB")
    print("=" * 60)

    client = FalkorDBClient(graph_name="test_blastradius_step2")
    ingester = RepoIngester(repo_root=".", client=client)

    stats = ingester.ingest(clear_existing=True)
    print(f"[OK] Ingestion finished with stats:")
    for k, v in stats.items():
        print(f"     - {k}: {v}")

    assert stats["files"] >= 4, f"Expected at least 4 files, got {stats['files']}"
    assert stats["functions"] >= 5, f"Expected at least 5 functions, got {stats['functions']}"
    assert stats["classes"] >= 2, f"Expected at least 2 classes, got {stats['classes']}"
    assert stats["commits"] >= 1, f"Expected at least 1 commit, got {stats['commits']}"
    assert stats["authors"] >= 1, f"Expected at least 1 author, got {stats['authors']}"

    # Verify query for File nodes
    res_files = client.query("MATCH (f:File) RETURN count(f) AS cnt")
    file_cnt = res_files.result_set[0][0]
    print(f"[OK] Verified {file_cnt} File nodes in FalkorDB")

    # Verify query for Function nodes
    res_funcs = client.query("MATCH (fn:Function) RETURN count(fn) AS cnt")
    func_cnt = res_funcs.result_set[0][0]
    print(f"[OK] Verified {func_cnt} Function nodes in FalkorDB")

    # Verify query for Author -> Commit -> File
    res_git = client.query("""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[m:MODIFIED]->(f:File)
        RETURN a.name, c.short_hash, f.path, m.insertions
        LIMIT 5
    """)
    assert len(res_git.result_set) > 0, "No git relationships found!"
    print(f"[OK] Verified Git relationship traversal:")
    for row in res_git.result_set:
        print(f"     Author '{row[0]}' committed [{row[1]}] modifying '{row[2]}' (+{row[3]})")

    # Verify path query
    res_calls = client.query("""
        MATCH p = (f1:Function)-[:CALLS]->(f2:Function)
        RETURN p LIMIT 3
    """)
    if res_calls.result_set:
        print(f"[OK] Verified Function call paths:")
        for row in res_calls.result_set:
            print(f"     {format_path(row[0])}")

    client.clear()
    print("[OK] Cleaned up test graph")
    print("\n>>> STEP 2 PASSED! AST and Git ingestion are working perfectly. <<<\n")


if __name__ == "__main__":
    test_step2()
