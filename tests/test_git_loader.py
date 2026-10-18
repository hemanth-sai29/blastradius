"""
Verification Test for git_loader.py using GitPython and FalkorDB.

Verifies:
1. Extraction of last commits using GitPython.
2. Creation of Commit and Author nodes.
3. Creation of AUTHORED and MODIFIED_BY edges.
4. Detection of 'fixes #123' message -> Issue node & FIXES edge.
5. Computation of OWNS edges from author to most-changed files.
6. Printing top owners for sample files.
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

from blastradius.graph.db import FalkorDBClient
from git_loader import GitLoader


def test_git_loader():
    print("=" * 60)
    print("TEST: GitLoader with GitPython & FalkorDB Graph")
    print("=" * 60)

    # Use a dedicated test graph
    test_client = FalkorDBClient(graph_name="test_blastradius_git_loader")
    test_client.clear()

    loader = GitLoader(repo_path=".", client=test_client, max_commits=500)
    stats = loader.load_history(clear_graph=False)

    print(f"\n[OK] GitLoader ran successfully:")
    for k, v in stats.items():
        print(f"     - {k}: {v}")

    assert stats["commits"] > 0, "Should have loaded at least 1 commit"
    assert stats["authors"] > 0, "Should have loaded at least 1 author"
    assert stats["files"] > 0, "Should have loaded files"
    assert stats["modified_edges"] > 0, "Should have MODIFIED_BY edges"
    assert stats["owns_edges"] > 0, "Should have computed OWNS edges"

    # 1. Verify AUTHORED edges
    res_auth = test_client.query(
        "MATCH (a:Author)-[:AUTHORED]->(c:Commit) RETURN count(c)"
    )
    authored_count = res_auth.result_set[0][0]
    print(f"[OK] Verified {authored_count} AUTHORED relationships.")
    assert authored_count > 0, "Should have AUTHORED edges"

    # 2. Verify MODIFIED_BY edges
    res_mod = test_client.query(
        "MATCH (c:Commit)-[m:MODIFIED_BY]->(f:File) RETURN count(m), sum(m.lines)"
    )
    mod_count, total_lines = res_mod.result_set[0]
    print(f"[OK] Verified {mod_count} MODIFIED_BY relationships (total lines: {total_lines}).")
    assert mod_count > 0, "Should have MODIFIED_BY edges"

    # 3. Verify Issue #123 and FIXES edge
    res_fixes = test_client.query(
        """
        MATCH (c:Commit)-[:FIXES]->(i:Issue)
        RETURN c.short_hash, c.message, i.id, i.number
        """
    )
    print(f"[OK] Verified FIXES relationships ({len(res_fixes.result_set)} found):")
    issue_found = False
    for row in res_fixes.result_set:
        c_short, c_msg, i_id, i_num = row
        print(f"     - Commit [{c_short}] FIXES Issue {i_id}: '{c_msg}'")
        if i_id == "#123":
            issue_found = True

    assert issue_found, "Commit mentioning 'fixes #123' must be connected to Issue #123 via FIXES!"

    # 4. Verify OWNS edges
    res_owns = test_client.query(
        """
        MATCH (a:Author)-[o:OWNS]->(f:File)
        RETURN a.name, f.path, o.commits, o.lines_changed, o.score
        ORDER BY o.score DESC
        LIMIT 5
        """
    )
    print(f"[OK] Verified OWNS relationships. Top 5 author-file ownerships:")
    for row in res_owns.result_set:
        print(f"     - {row[0]} OWNS '{row[1]}' (commits: {row[2]}, lines: {row[3]}, score: {row[4]})")
    assert len(res_owns.result_set) > 0, "Should have computed OWNS edges"

    # 5. Print top owners for 3 sample files
    print("\n[*] Testing print_top_owners_for_sample_files:")
    loader.print_top_owners_for_sample_files(sample_limit=3, top_n=5)

    # Clean up test graph
    test_client.clear()
    print("[OK] Cleaned up test graph.")
    print("\n>>> GIT LOADER TEST PASSED! All requirements verified. <<<\n")


if __name__ == "__main__":
    test_git_loader()
