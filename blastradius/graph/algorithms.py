"""
Graph Algorithms & Impact Analysis for BlastRadius.
Executes multi-hop Cypher queries on FalkorDB:
- Blast Radius (ripple effect & downstream impact scoring)
- Shortest Path (exact call/import chains with explainability)
- Centrality & Hub Identification (PageRank / degree centrality)
- Test Discovery & Test Gap Analysis
- Reviewer Recommendation via git commit & authorship connections
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from blastradius.graph.db import FalkorDBClient, db_client, format_path

logger = logging.getLogger(__name__)


@dataclass
class ImpactedNode:
    full_name: str
    file_path: str
    depth: int
    path_explanation: str


@dataclass
class BlastRadiusResult:
    target: str
    impact_score: float
    total_impacted_functions: int
    total_impacted_files: int
    impacted_functions: list[ImpactedNode] = field(default_factory=list)
    impacted_files: list[str] = field(default_factory=list)
    critical_hubs_affected: list[str] = field(default_factory=list)
    missing_test_coverage: list[str] = field(default_factory=list)


@dataclass
class ShortestPathResult:
    source: str
    target: str
    hops: int
    found: bool
    path_explanation: str


@dataclass
class CentralityScore:
    symbol: str
    file_path: str
    in_degree: int
    out_degree: int
    hub_score: float


@dataclass
class TestCoverageResult:
    target: str
    test_functions: list[str] = field(default_factory=list)
    test_paths: list[str] = field(default_factory=list)
    is_covered: bool = False


@dataclass
class ReviewerRecommendation:
    author_name: str
    author_email: str
    score: float
    commits_count: int
    files_touched: list[str] = field(default_factory=list)
    churn: int = 0


class GraphAlgorithms:
    """Provides high-performance graph reasoning algorithms on top of FalkorDB."""

    def __init__(self, client: FalkorDBClient | None = None):
        self.client = client or db_client

    def calculate_blast_radius(
        self, target_symbol: str, max_depth: int = 4
    ) -> BlastRadiusResult:
        """
        Calculates ripple effects when a function or file is changed.
        Traverses callers and dependent files to compute an impact score
        and complete explainability paths.
        """
        # Determine if target is a file or a function
        is_file = target_symbol.endswith(".py")
        impacted_funcs: dict[str, ImpactedNode] = {}
        impacted_files_set: set[str] = set()

        if is_file:
            # 1. Target is a file: find functions inside it, and files that import it
            cypher_file_imports = f"""
            MATCH p = (importer:File)-[:IMPORTS*1..{max_depth}]->(target:File {{path: $target}})
            RETURN importer.path, length(p), p
            """
            res_imp = self.client.query(cypher_file_imports, {"target": target_symbol})
            if res_imp and res_imp.result_set:
                for row in res_imp.result_set:
                    impacted_files_set.add(row[0])

            # Also check callers of all functions inside this file
            cypher_funcs_in_file = """
            MATCH (f:File {path: $target})-[:CONTAINS*1..2]->(fn:Function)
            RETURN fn.full_name
            """
            res_fn = self.client.query(cypher_funcs_in_file, {"target": target_symbol})
            target_funcs = [r[0] for r in res_fn.result_set] if res_fn else []

            for fn_full in target_funcs:
                cypher_callers = f"""
                MATCH p = (caller:Function)-[:CALLS*1..{max_depth}]->(target:Function {{full_name: $fn_name}})
                WHERE caller.file_path <> $target
                RETURN caller.full_name, caller.file_path, length(p), p
                """
                res_callers = self.client.query(
                    cypher_callers, {"fn_name": fn_full, "target": target_symbol}
                )
                if res_callers and res_callers.result_set:
                    for row in res_callers.result_set:
                        caller_name, file_path, depth, path_obj = row
                        impacted_files_set.add(file_path)
                        if (
                            caller_name not in impacted_funcs
                            or depth < impacted_funcs[caller_name].depth
                        ):
                            impacted_funcs[caller_name] = ImpactedNode(
                                full_name=caller_name,
                                file_path=file_path,
                                depth=depth,
                                path_explanation=format_path(path_obj),
                            )
        else:
            # 2. Target is a function
            # Find direct and multi-hop callers
            cypher_callers = f"""
            MATCH p = (caller:Function)-[:CALLS*1..{max_depth}]->(target:Function)
            WHERE target.full_name = $target OR target.name = $target
            RETURN caller.full_name, caller.file_path, length(p), p
            """
            res = self.client.query(cypher_callers, {"target": target_symbol})
            if res and res.result_set:
                for row in res.result_set:
                    caller_name, file_path, depth, path_obj = row
                    impacted_files_set.add(file_path)
                    if (
                        caller_name not in impacted_funcs
                        or depth < impacted_funcs[caller_name].depth
                    ):
                        impacted_funcs[caller_name] = ImpactedNode(
                            full_name=caller_name,
                            file_path=file_path,
                            depth=depth,
                            path_explanation=format_path(path_obj),
                        )

        # Check centrality of impacted functions to identify critical hubs
        hub_names = set()
        for fn_name in impacted_funcs:
            c = self.get_symbol_centrality(fn_name)
            if c and c.in_degree >= 2:
                hub_names.add(fn_name)

        # Check test coverage for target
        cov = self.discover_tests(target_symbol)
        missing_tests = []
        if not cov.is_covered:
            missing_tests.append(target_symbol)

        # Calculate impact score (0 to 100)
        # Factors: number of functions (weight 2), files (weight 4), hubs (weight 10), un-tested penalty (+15)
        raw_score = (
            len(impacted_funcs) * 2.5
            + len(impacted_files_set) * 4.0
            + len(hub_names) * 8.0
            + (15.0 if missing_tests else 0.0)
        )
        impact_score = min(100.0, round(raw_score, 1))

        return BlastRadiusResult(
            target=target_symbol,
            impact_score=impact_score,
            total_impacted_functions=len(impacted_funcs),
            total_impacted_files=len(impacted_files_set),
            impacted_functions=list(impacted_funcs.values()),
            impacted_files=sorted(list(impacted_files_set)),
            critical_hubs_affected=sorted(list(hub_names)),
            missing_test_coverage=missing_tests,
        )

    def find_shortest_path(
        self, source: str, target: str, max_depth: int = 6
    ) -> ShortestPathResult:
        """
        Finds the shortest call path between two functions or files.
        """
        # Try Function to Function directed first
        cypher = f"""
        MATCH p = (src:Function)-[:CALLS*1..{max_depth}]->(dst:Function)
        WHERE (src.full_name = $src OR src.name = $src)
          AND (dst.full_name = $dst OR dst.name = $dst)
        RETURN p, length(p)
        ORDER BY length(p) ASC
        LIMIT 1
        """
        res = self.client.query(cypher, {"src": source, "dst": target})
        if res and res.result_set:
            path_obj, hops = res.result_set[0]
            return ShortestPathResult(
                source=source,
                target=target,
                hops=hops,
                found=True,
                path_explanation=format_path(path_obj),
            )

        # Try File to File IMPORTS directed
        cypher_file = f"""
        MATCH p = (src:File)-[:IMPORTS*1..{max_depth}]->(dst:File)
        WHERE src.path = $src AND dst.path = $dst
        RETURN p, length(p)
        ORDER BY length(p) ASC
        LIMIT 1
        """
        res_file = self.client.query(cypher_file, {"src": source, "dst": target})
        if res_file and res_file.result_set:
            path_obj, hops = res_file.result_set[0]
            return ShortestPathResult(
                source=source,
                target=target,
                hops=hops,
                found=True,
                path_explanation=format_path(path_obj),
            )

        # Try undirected fallback for functions
        cypher_undir = f"""
        MATCH p = (src:Function)-[:CALLS*1..{max_depth}]-(dst:Function)
        WHERE (src.full_name = $src OR src.name = $src)
          AND (dst.full_name = $dst OR dst.name = $dst)
        RETURN p, length(p)
        ORDER BY length(p) ASC
        LIMIT 1
        """
        res_undir = self.client.query(cypher_undir, {"src": source, "dst": target})
        if res_undir and res_undir.result_set:
            path_obj, hops = res_undir.result_set[0]
            return ShortestPathResult(
                source=source,
                target=target,
                hops=hops,
                found=True,
                path_explanation=format_path(path_obj),
            )

        return ShortestPathResult(
            source=source,
            target=target,
            hops=-1,
            found=False,
            path_explanation="No connecting path found between symbols.",
        )

    def get_symbol_centrality(self, symbol: str) -> CentralityScore | None:
        """Computes in-degree and out-degree centrality for a specific function."""
        cypher = """
        MATCH (fn:Function)
        WHERE fn.full_name = $sym OR fn.name = $sym
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(fn)
        OPTIONAL MATCH (fn)-[:CALLS]->(callee:Function)
        RETURN fn.full_name, fn.file_path, count(DISTINCT caller) AS in_deg, count(DISTINCT callee) AS out_deg
        LIMIT 1
        """
        res = self.client.query(cypher, {"sym": symbol})
        if not res or not res.result_set:
            return None

        full_name, file_path, in_deg, out_deg = res.result_set[0]
        hub_score = in_deg * 2.0 + out_deg * 0.5
        return CentralityScore(
            symbol=full_name,
            file_path=file_path,
            in_degree=in_deg,
            out_degree=out_deg,
            hub_score=hub_score,
        )

    def get_top_central_hubs(self, limit: int = 10) -> list[CentralityScore]:
        """Returns the most central / interconnected hub functions in the repository."""
        cypher = """
        MATCH (fn:Function)
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(fn)
        OPTIONAL MATCH (fn)-[:CALLS]->(callee:Function)
        WITH fn, count(DISTINCT caller) AS in_deg, count(DISTINCT callee) AS out_deg
        WHERE in_deg > 0 OR out_deg > 0
        RETURN fn.full_name, fn.file_path, in_deg, out_deg, (in_deg * 2.0 + out_deg * 0.5) AS score
        ORDER BY score DESC, in_deg DESC
        LIMIT $limit
        """
        res = self.client.query(cypher, {"limit": limit})
        hubs = []
        if res and res.result_set:
            for row in res.result_set:
                hubs.append(
                    CentralityScore(
                        symbol=row[0],
                        file_path=row[1],
                        in_degree=row[2],
                        out_degree=row[3],
                        hub_score=row[4],
                    )
                )
        return hubs

    def discover_tests(self, target_symbol: str) -> TestCoverageResult:
        """
        Discovers all test functions that directly or transitively verify a function or file.
        """
        test_funcs: set[str] = set()
        test_paths: list[str] = []

        is_file = target_symbol.endswith(".py")
        if is_file:
            # Tests for any function in the file
            cypher = """
            MATCH (f:File {path: $target})-[:CONTAINS*1..2]->(fn:Function)
            MATCH p = (t:Function {is_test: true})-[:TESTS|CALLS*1..4]->(fn)
            RETURN DISTINCT t.full_name, p
            """
            res = self.client.query(cypher, {"target": target_symbol})
        else:
            cypher = """
            MATCH (target:Function)
            WHERE target.full_name = $target OR target.name = $target
            MATCH p = (t:Function {is_test: true})-[:TESTS|CALLS*1..4]->(target)
            RETURN DISTINCT t.full_name, p
            """
            res = self.client.query(cypher, {"target": target_symbol})

        if res and res.result_set:
            for row in res.result_set:
                test_funcs.add(row[0])
                test_paths.append(format_path(row[1]))

        return TestCoverageResult(
            target=target_symbol,
            test_functions=sorted(list(test_funcs)),
            test_paths=test_paths,
            is_covered=len(test_funcs) > 0,
        )

    def recommend_reviewers(
        self, files: list[str], limit: int = 3
    ) -> list[ReviewerRecommendation]:
        """
        Identifies the top subject-matter expert reviewers for a set of changed files
        based on git authorship and churn history.
        """
        cypher = """
        MATCH (cm:Commit)-[m:MODIFIED]->(f:File)
        WHERE f.path IN $files
        MATCH (a:Author)-[:AUTHORED]->(cm)
        RETURN a.name, a.email, count(DISTINCT cm) AS commits_cnt,
               collect(DISTINCT f.path) AS touched,
               sum(m.insertions + m.deletions) AS total_churn
        ORDER BY commits_cnt DESC, total_churn DESC
        LIMIT $limit
        """
        res = self.client.query(cypher, {"files": files, "limit": limit})
        recs = []
        if res and res.result_set:
            for row in res.result_set:
                name, email, commits_cnt, touched, churn = row
                churn_val = churn if churn is not None else 0
                # Weighted score based on commit count and churn
                score = round(commits_cnt * 10.0 + (churn_val * 0.1), 1)
                recs.append(
                    ReviewerRecommendation(
                        author_name=name,
                        author_email=email,
                        score=score,
                        commits_count=commits_cnt,
                        files_touched=touched,
                        churn=churn_val,
                    )
                )
        return recs
