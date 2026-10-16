"""
Command-Line Interface (CLI) for BlastRadius.
Usage:
    blastradius ingest [--repo PATH]
    blastradius blast <SYMBOL> [--depth N]
    blastradius path <SOURCE> <TARGET>
    blastradius hubs [--limit N]
    blastradius tests <SYMBOL>
    blastradius review [--files FILE1,FILE2]
    blastradius diagnose
    blastradius serve-mcp
"""

import argparse
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from blastradius.agent.pr_reviewer import PRReviewer
from blastradius.agent.reasoner import GraphReasoner
from blastradius.graph.algorithms import GraphAlgorithms
from blastradius.graph.db import db_client
from blastradius.ingester.builder import RepoIngester
from blastradius.mcp_server.server import mcp_server


def cmd_ingest(args):
    print(f"[*] Ingesting repository: {args.repo}...")
    ingester = RepoIngester(repo_root=args.repo, client=db_client)
    stats = ingester.ingest(clear_existing=not args.keep)
    print("\n[OK] Ingestion complete:")
    for k, v in stats.items():
        print(f"     - {k}: {v}")


def cmd_blast(args):
    algo = GraphAlgorithms(client=db_client)
    print(f"[*] Calculating blast radius for '{args.symbol}' (max_depth={args.depth})...")
    res = algo.calculate_blast_radius(args.symbol, max_depth=args.depth)
    print(f"\n💥 Blast Radius Impact Score: {res.impact_score}/100")
    print(f"📁 Impacted Files: {res.total_impacted_files}")
    for f in res.impacted_files:
        print(f"   - {f}")
    print(f"🧩 Impacted Functions: {res.total_impacted_functions}")
    for fn in res.impacted_functions[:10]:
        print(f"   - [Depth {fn.depth}] {fn.full_name}")
        if fn.path_explanation:
            print(f"     path: {fn.path_explanation}")
    if res.critical_hubs_affected:
        print("\n⚠️ Critical Hubs Affected:")
        for h in res.critical_hubs_affected:
            print(f"   - 🔴 {h}")


def cmd_path(args):
    algo = GraphAlgorithms(client=db_client)
    print(f"[*] Tracing shortest path from '{args.source}' to '{args.target}'...")
    res = algo.find_shortest_path(args.source, args.target)
    if res.found:
        print(f"\n[OK] Path found in {res.hops} hop(s):")
        print(f"     {res.path_explanation}")
    else:
        print(f"\n[!] No path found: {res.path_explanation}")


def cmd_hubs(args):
    algo = GraphAlgorithms(client=db_client)
    hubs = algo.get_top_central_hubs(limit=args.limit)
    print(f"\n🎯 Top {len(hubs)} Central Hub Functions:")
    print(f"{'Symbol':<50} {'In-Deg':<8} {'Out-Deg':<8} {'Score':<8}")
    print("-" * 76)
    for h in hubs:
        print(f"{h.symbol:<50} {h.in_degree:<8} {h.out_degree:<8} {h.hub_score:<8.1f}")


def cmd_tests(args):
    algo = GraphAlgorithms(client=db_client)
    res = algo.discover_tests(args.symbol)
    print(f"\n🧪 Test Discovery for '{args.symbol}':")
    print(f"Covered: {'✅ Yes' if res.is_covered else '❌ No'}")
    if res.test_functions:
        print(f"Associated Tests ({len(res.test_functions)}):")
        for t in res.test_functions:
            print(f"  - {t}")


def cmd_review(args):
    files = [f.strip() for f in args.files.split(",") if f.strip()]
    if not files:
        print("[!] No files provided for review. Use --files path/to/a.py,path/to/b.py")
        return

    reviewer = PRReviewer(client=db_client)
    report = reviewer.review_files(files)
    print("\n" + "=" * 60)
    print(f"PR RISK REPORT: {report.risk_badge} ({report.overall_score}/100)")
    print("=" * 60)
    print(report.markdown_comment)

    if args.output:
        Path(args.output).write_text(report.markdown_comment, encoding="utf-8")
        print(f"\n[OK] Markdown comment saved to: {args.output}")


def cmd_diagnose(args):
    reasoner = GraphReasoner(client=db_client)
    res = reasoner.diagnose_architectural_smells()
    print("\n🔍 Architectural Diagnosis:")
    print(f"Top Hubs: {len(res['critical_hubs'])}")
    for h in res["critical_hubs"]:
        print(f"  - {h['symbol']} (score: {h['score']})")
    print(f"\nCircular Imports: {len(res['circular_imports'])}")
    for c in res["circular_imports"]:
        print(f"  - {c['file_a']} <--> {c['file_b']}")
    print(f"\nOrphan / Uncalled Functions: {len(res['orphan_functions'])}")
    for o in res["orphan_functions"][:5]:
        print(f"  - {o['function']} in {o['file']}")


def cmd_serve_mcp(args):
    print("[*] Starting BlastRadius Official MCP Server (stdio mode)...")
    try:
        asyncio.run(mcp_server.run_stdio_async())
    except (KeyboardInterrupt, SystemExit):
        pass


def main():
    parser = argparse.ArgumentParser(
        prog="blastradius",
        description="💥 BlastRadius: AI Agent for Multi-Hop Code Impact Analysis powered by FalkorDB",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest repository into FalkorDB")
    p_ingest.add_argument("--repo", default=".", help="Repository root path")
    p_ingest.add_argument(
        "--keep", action="store_true", help="Keep existing graph instead of clearing"
    )
    p_ingest.set_defaults(func=cmd_ingest)

    # Blast
    p_blast = subparsers.add_parser("blast", help="Calculate blast radius for a symbol")
    p_blast.add_argument("symbol", help="Function name or file path")
    p_blast.add_argument("--depth", type=int, default=4, help="Maximum traversal depth")
    p_blast.set_defaults(func=cmd_blast)

    # Path
    p_path = subparsers.add_parser("path", help="Find shortest path between two symbols")
    p_path.add_argument("source", help="Source function or file")
    p_path.add_argument("target", help="Target function or file")
    p_path.set_defaults(func=cmd_path)

    # Hubs
    p_hubs = subparsers.add_parser("hubs", help="Find top central hub functions")
    p_hubs.add_argument("--limit", type=int, default=10, help="Number of hubs to return")
    p_hubs.set_defaults(func=cmd_hubs)

    # Tests
    p_tests = subparsers.add_parser("tests", help="Discover tests covering a symbol")
    p_tests.add_argument("symbol", help="Function or file name")
    p_tests.set_defaults(func=cmd_tests)

    # Review
    p_review = subparsers.add_parser("review", help="Generate PR risk assessment")
    p_review.add_argument(
        "--files", required=True, help="Comma-separated list of modified files"
    )
    p_review.add_argument("--output", help="Optional path to save Markdown report")
    p_review.set_defaults(func=cmd_review)

    # Diagnose
    p_diag = subparsers.add_parser("diagnose", help="Diagnose architectural smells")
    p_diag.set_defaults(func=cmd_diagnose)

    # Serve MCP
    p_mcp = subparsers.add_parser("serve-mcp", help="Run official MCP server on stdio")
    p_mcp.set_defaults(func=cmd_serve_mcp)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
