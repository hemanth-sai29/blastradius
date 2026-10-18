"""
Official Model Context Protocol (MCP) Server for BlastRadius.
Exposes multi-hop code impact analysis, graph algorithms, and FalkorDB traversals
as standard MCP tools for AI agents.
"""

import asyncio
import logging
from typing import Any
from mcp.server.mcpserver import MCPServer

from blastradius.graph.algorithms import GraphAlgorithms
from blastradius.graph.db import db_client, format_path
from blastradius.ingester.builder import RepoIngester

logger = logging.getLogger(__name__)


def create_mcp_server(client: FalkorDBClient | None = None) -> MCPServer:
    """Builds and registers all BlastRadius graph tools into an MCPServer instance."""
    target_client = client or db_client
    server = MCPServer(
        name="blastradius",
        version="1.0.0",
        description="FalkorDB-powered graph tools for multi-hop code impact analysis and PR risk assessment",
    )

    algorithms = GraphAlgorithms(client=target_client)

    @server.tool()
    def ingest_codebase(repo_path: str = ".", clear_existing: bool = True) -> dict[str, Any]:
        """
        Ingests a Python repository's AST (files, classes, functions, calls, imports)
        and Git history (commits, authors, modifications) into FalkorDB.
        """
        ingester = RepoIngester(repo_root=repo_path, client=target_client)
        stats = ingester.ingest(clear_existing=clear_existing)
        return {"status": "success", "repo_path": repo_path, "stats": stats}

    @server.tool()
    def get_blast_radius(target_symbol: str, max_depth: int = 4) -> dict[str, Any]:
        """
        Calculates ripple effects and downstream impact score when a function or file is modified.
        Returns impacted functions, dependent files, critical hubs affected, and explainability paths.
        """
        res = algorithms.calculate_blast_radius(target_symbol, max_depth=max_depth)
        return {
            "target": res.target,
            "impact_score": res.impact_score,
            "total_impacted_functions": res.total_impacted_functions,
            "total_impacted_files": res.total_impacted_files,
            "impacted_functions": [
                {
                    "full_name": f.full_name,
                    "file_path": f.file_path,
                    "depth": f.depth,
                    "path_explanation": f.path_explanation,
                }
                for f in res.impacted_functions
            ],
            "impacted_files": res.impacted_files,
            "critical_hubs_affected": res.critical_hubs_affected,
            "missing_test_coverage": res.missing_test_coverage,
        }

    @server.tool()
    def get_shortest_path(source: str, target: str, max_depth: int = 6) -> dict[str, Any]:
        """
        Traces the shortest multi-hop call chain or import dependency between two code symbols.
        Returns hop count and step-by-step explainability chain.
        """
        res = algorithms.find_shortest_path(source, target, max_depth=max_depth)
        return {
            "source": res.source,
            "target": res.target,
            "found": res.found,
            "hops": res.hops,
            "path_explanation": res.path_explanation,
        }

    @server.tool()
    def get_central_hubs(limit: int = 10) -> list[dict[str, Any]]:
        """
        Discovers high-risk hub functions in the codebase with high incoming call coupling
        and high architectural centrality.
        """
        hubs = algorithms.get_top_central_hubs(limit=limit)
        return [
            {
                "symbol": h.symbol,
                "file_path": h.file_path,
                "in_degree": h.in_degree,
                "out_degree": h.out_degree,
                "hub_score": h.hub_score,
            }
            for h in hubs
        ]

    @server.tool()
    def discover_tests(target_symbol: str) -> dict[str, Any]:
        """
        Identifies all test functions that directly or transitively verify a function or file.
        Provides the test paths and indicates whether coverage is present.
        """
        res = algorithms.discover_tests(target_symbol)
        return {
            "target": res.target,
            "is_covered": res.is_covered,
            "test_functions": res.test_functions,
            "test_paths": res.test_paths,
        }

    @server.tool()
    def recommend_reviewers(files: list[str], limit: int = 3) -> list[dict[str, Any]]:
        """
        Suggests top subject-matter expert reviewers based on git authorship and churn history
        for the specified files or blast zone.
        """
        recs = algorithms.recommend_reviewers(files, limit=limit)
        return [
            {
                "author_name": r.author_name,
                "author_email": r.author_email,
                "score": r.score,
                "commits_count": r.commits_count,
                "files_touched": r.files_touched,
                "churn": r.churn,
            }
            for r in recs
        ]

    @server.tool()
    def query_graph(cypher: str) -> list[dict[str, Any]]:
        """
        Executes a raw read-only Cypher query on FalkorDB and returns the formatted results.
        Useful for custom multi-hop graph explorations.
        """
        res = target_client.query(cypher)
        output = []
        if res and res.result_set:
            headers = [h[1] for h in getattr(res, "header", [])] or [
                f"col_{i}" for i in range(len(res.result_set[0]))
            ]
            for row in res.result_set:
                row_dict = {}
                for idx, val in enumerate(row):
                    key = headers[idx] if idx < len(headers) else f"col_{idx}"
                    if hasattr(val, "nodes") and hasattr(val, "edges"):
                        row_dict[key] = format_path(val)
                    else:
                        row_dict[key] = str(val)
                output.append(row_dict)
        return output

    return server


mcp_server = create_mcp_server()


if __name__ == "__main__":
    import sys

    # Run in stdio mode for MCP clients
    try:
        asyncio.run(mcp_server.run_stdio_async())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
