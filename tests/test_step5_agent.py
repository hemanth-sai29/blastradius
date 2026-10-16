"""
Step 5 Verification Test: AI Agent & Automated PR Risk Commentary.
Tests PR risk tier evaluation, Markdown report generation, and reasoning engine.
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
from blastradius.agent.pr_reviewer import PRReviewer
from blastradius.agent.reasoner import GraphReasoner


def test_step5():
    print("=" * 60)
    print("TEST STEP 5: AI Agent & Automated PR Risk Commentary")
    print("=" * 60)

    client = FalkorDBClient(graph_name="test_blastradius_step5")
    ingester = RepoIngester(repo_root=".", client=client)

    print("[*] Ingesting codebase into test graph...")
    stats = ingester.ingest(clear_existing=True)
    print(f"[OK] Ingestion complete: {stats['files']} files, {stats['functions']} functions")

    # 1. Test PR Risk Reviewer
    print("\n[*] Evaluating PR modifying ['blastradius/graph/db.py']...")
    reviewer = PRReviewer(client=client)
    report = reviewer.review_files(["blastradius/graph/db.py"])

    print(f"[OK] PR Risk Tier: {report.risk_badge}")
    print(f"     Overall Score: {report.overall_score}/100")
    print(f"     Impacted Functions: {report.total_impacted_functions}")
    print(f"     Dependent Files: {report.total_impacted_files}")
    print(f"     Critical Hubs: {len(report.critical_hubs_affected)}")
    print(f"     Covered Tests: {len(report.covered_tests)}")
    print(f"     Recommended Reviewers: {len(report.recommended_reviewers)}")

    assert report.overall_score > 0, "Overall score should be greater than 0"
    assert "## 💥 BlastRadius PR Risk Assessment" in report.markdown_comment
    assert "Risk Tier" in report.markdown_comment
    assert "Suggested Reviewers" in report.markdown_comment

    print("\n--- SAMPLE GENERATED PR COMMENT SNIPPET ---")
    comment_lines = report.markdown_comment.splitlines()
    for line in comment_lines[:25]:
        print(line)
    print("... [snip] ...")
    print("------------------------------------------")

    # 2. Test Multi-Hop Reasoner
    print("\n[*] Testing GraphReasoner architectural diagnosis...")
    reasoner = GraphReasoner(client=client)
    diagnosis = reasoner.diagnose_architectural_smells()
    print(f"[OK] Diagnosis found {len(diagnosis['critical_hubs'])} hubs, "
          f"{len(diagnosis['circular_imports'])} circular imports, "
          f"{len(diagnosis['orphan_functions'])} orphan functions.")

    explanation = reasoner.explain_symbol_impact("connect")
    print(f"[OK] Generated plain-text explanation for 'connect':\n{explanation[:200]}...")

    client.clear()
    print("\n[OK] Cleaned up test graph")
    print("\n>>> STEP 5 PASSED! Agent reasoning and PR commentary verified. <<<\n")


if __name__ == "__main__":
    test_step5()
