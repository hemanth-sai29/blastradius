"""
Multi-Hop Graph Reasoner for BlastRadius.
Enables agents to query FalkorDB for architectural smells, safe refactoring,
and comprehensive blast radius explanations.
"""

import logging
from typing import Any

from blastradius.graph.algorithms import GraphAlgorithms
from blastradius.graph.db import FalkorDBClient, db_client, format_path

logger = logging.getLogger(__name__)


class GraphReasoner:
    """Provides high-level agentic reasoning over the FalkorDB code graph."""

    def __init__(self, client: FalkorDBClient | None = None):
        self.client = client or db_client
        self.algorithms = GraphAlgorithms(client=self.client)

    def explain_symbol_impact(self, symbol: str) -> str:
        """Generates a plain-text multi-hop explanation of downstream blast radius."""
        blast = self.algorithms.calculate_blast_radius(symbol)
        lines = [
            f"=== BlastRadius Analysis for '{symbol}' ===",
            f"Impact Score: {blast.impact_score}/100",
            f"Impacted Functions: {blast.total_impacted_functions}",
            f"Impacted Files: {blast.total_impacted_files}",
        ]

        if blast.critical_hubs_affected:
            lines.append("\n[!] Critical Hubs Affected:")
            for h in blast.critical_hubs_affected:
                lines.append(f"    - {h}")

        if blast.impacted_functions:
            lines.append("\n[+] Direct and Multi-Hop Call Paths:")
            for fn in blast.impacted_functions[:10]:
                lines.append(f"    - (Depth {fn.depth}) {fn.path_explanation}")

        if blast.missing_test_coverage:
            lines.append(
                f"\n[?] Warning: No test functions currently cover '{symbol}'."
            )
        else:
            cov = self.algorithms.discover_tests(symbol)
            lines.append(
                f"\n[*] Verified by {len(cov.test_functions)} test function(s)."
            )

        return "\n".join(lines)

    def diagnose_architectural_smells(self) -> dict[str, Any]:
        """
        Detects structural smells across the code graph:
        1. High-risk hubs (functions with very high in-degree)
        2. Circular imports (File A -> File B -> File A)
        3. Dead/Orphan functions (internal non-test functions with 0 callers)
        """
        # 1. Hubs
        hubs = self.algorithms.get_top_central_hubs(limit=5)

        # 2. Circular imports
        cypher_cycles = """
        MATCH (f1:File)-[:IMPORTS]->(f2:File)-[:IMPORTS]->(f1)
        WHERE f1.path < f2.path
        RETURN f1.path, f2.path
        """
        res_cycles = self.client.query(cypher_cycles)
        circular_imports = []
        if res_cycles and res_cycles.result_set:
            for row in res_cycles.result_set:
                circular_imports.append({"file_a": row[0], "file_b": row[1]})

        # 3. Dead/orphan functions (non-test functions with in_degree == 0 not called anywhere)
        cypher_orphans = """
        MATCH (fn:Function {is_test: false})
        WHERE NOT (fn.name STARTS WITH "__" AND fn.name ENDS WITH "__")
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(fn)
        WITH fn, count(caller) AS callers_cnt
        WHERE callers_cnt = 0
        RETURN fn.full_name, fn.file_path
        LIMIT 10
        """
        res_orphans = self.client.query(cypher_orphans)
        orphans = []
        if res_orphans and res_orphans.result_set:
            for row in res_orphans.result_set:
                orphans.append({"function": row[0], "file": row[1]})

        return {
            "critical_hubs": [
                {"symbol": h.symbol, "in_degree": h.in_degree, "score": h.hub_score}
                for h in hubs
            ],
            "circular_imports": circular_imports,
            "orphan_functions": orphans,
        }
