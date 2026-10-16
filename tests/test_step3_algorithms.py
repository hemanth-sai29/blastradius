"""
Step 3 Verification Test: Graph Algorithms & Explainability.
Tests Blast Radius, Shortest Path, Centrality Hubs, Test Discovery, and Reviewer Recs.
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
from blastradius.ingester.builder import RepoIngester
from blastradius.graph.algorithms import GraphAlgorithms


def test_step3():
    print("=" * 60)
    print("TEST STEP 3: Graph Algorithms & Impact Reasoning")
    print("=" * 60)

    client = FalkorDBClient(graph_name="test_blastradius_step3")
    ingester = RepoIngester(repo_root=".", client=client)

    print("[*] Ingesting codebase into test graph...")
    stats = ingester.ingest(clear_existing=True)
    print(f"[OK] Ingestion done: {stats['files']} files, {stats['functions']} functions, {stats['calls']} calls")

    algo = GraphAlgorithms(client=client)

    # 1. Test Blast Radius for a core function
    target_fn = "connect"
    print(f"\n[*] Calculating Blast Radius for '{target_fn}'...")
    blast_res = algo.calculate_blast_radius(target_fn, max_depth=3)
    print(f"[OK] Blast Radius Impact Score: {blast_res.impact_score}/100")
    print(f"     Impacted functions: {blast_res.total_impacted_functions}")
    print(f"     Impacted files: {blast_res.total_impacted_files}")
    for fn in blast_res.impacted_functions[:3]:
        print(f"     -> [Depth {fn.depth}] {fn.full_name} via {fn.path_explanation}")

    # 2. Test Blast Radius for a core file
    target_file = "blastradius/graph/db.py"
    print(f"\n[*] Calculating Blast Radius for file '{target_file}'...")
    file_blast = algo.calculate_blast_radius(target_file, max_depth=3)
    print(f"[OK] File Impact Score: {file_blast.impact_score}/100")
    print(f"     Impacted functions: {file_blast.total_impacted_functions}")
    print(f"     Impacted files: {file_blast.total_impacted_files}")

    # 3. Test Shortest Path
    print("\n[*] Finding Shortest Path between functions...")
    src = "blastradius/config.py:_detect_falkordb_host"
    dst = "blastradius/config.py:_is_port_open"
    sp_res = algo.find_shortest_path(src, dst)
    print(f"[OK] Shortest path found: {sp_res.found} ({sp_res.hops} hops)")
    print(f"     Path: {sp_res.path_explanation}")
    assert sp_res.found, f"Shortest path between {src} and {dst} not found!"

    # 4. Test Centrality / Hubs
    print("\n[*] Finding Top Central Hubs in codebase...")
    hubs = algo.get_top_central_hubs(limit=5)
    print(f"[OK] Retrieved {len(hubs)} hubs:")
    for h in hubs:
        print(f"     - {h.symbol} (Score: {h.hub_score}, in: {h.in_degree}, out: {h.out_degree})")
    assert len(hubs) > 0, "No hubs found in codebase!"

    # 5. Test Test Discovery
    print(f"\n[*] Discovering Tests for '{target_file}'...")
    test_cov = algo.discover_tests(target_file)
    print(f"[OK] Covered: {test_cov.is_covered}, Tests found: {len(test_cov.test_functions)}")
    for t in test_cov.test_functions:
        print(f"     - Test: {t}")

    # 6. Test Reviewer Recommendations
    print(f"\n[*] Recommending Reviewers for [{target_file}]...")
    reviewers = algo.recommend_reviewers([target_file], limit=3)
    print(f"[OK] Recommended Reviewers: {len(reviewers)}")
    for r in reviewers:
        print(f"     - {r.author_name} <{r.author_email}> (Score: {r.score}, Commits: {r.commits_count})")
    assert len(reviewers) > 0, "No reviewers recommended!"

    client.clear()
    print("\n[OK] Cleaned up test graph")
    print("\n>>> STEP 3 PASSED! All graph algorithms and explainability verified. <<<\n")


if __name__ == "__main__":
    test_step3()
