"""
git_loader.py - Git History Graph Loader using GitPython for FalkorDB.

Part of BlastRadius (Graph Hacks - Track 1: Agents That Act on Connected Data).

This module:
1. Connects to FalkorDB via `blastradius.graph.db.FalkorDBClient`.
2. Inspects up to the last 500 commits using GitPython (`git.Repo`).
3. Creates:
   - (Author) nodes (name, email)
   - (Commit) nodes (hash, short_hash, message, timestamp, date)
   - (File) nodes (path, name)
4. Establishes edges:
   - (Author)-[:AUTHORED]->(Commit)
   - (Commit)-[:MODIFIED_BY]->(File) (with insertions, deletions, lines)
5. Detects issue mentions in commit messages (e.g. "fixes #123"):
   - Creates (Issue) node
   - Connects (Commit)-[:FIXES]->(Issue)
6. Computes (Author)-[:OWNS]->(File) edges for files each author changed most.
7. Prints the top 5 owners for 3 sample files in a clean, student-friendly table.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add workspace root to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from git import Repo, Commit
from blastradius.config import config
from blastradius.graph.db import FalkorDBClient, db_client


class GitLoader:
    """
    Loads Git history into FalkorDB using GitPython, creating rich
    Author, Commit, File, and Issue nodes with AUTHORED, MODIFIED_BY, FIXES, and OWNS edges.
    """

    def __init__(
        self,
        repo_path: str | Path = ".",
        client: FalkorDBClient | None = None,
        max_commits: int = 500,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.client = client or db_client
        self.max_commits = max_commits
        self.repo = Repo(str(self.repo_path))

    def init_schema(self) -> None:
        """Creates indices on FalkorDB for high-speed lookups."""
        indices = [
            "CREATE INDEX FOR (a:Author) ON (a.email)",
            "CREATE INDEX FOR (c:Commit) ON (c.hash)",
            "CREATE INDEX FOR (f:File) ON (f.path)",
            "CREATE INDEX FOR (i:Issue) ON (i.id)",
        ]
        g = self.client.connect()
        for idx in indices:
            try:
                g.query(idx)
            except Exception:
                # Index may already exist; safe to continue
                pass

    def load_history(self, clear_graph: bool = False) -> dict[str, Any]:
        """
        Parses up to 500 commits using GitPython and inserts the full
        graph structure into FalkorDB.
        """
        if clear_graph:
            self.client.clear()

        self.init_schema()

        # 1. Fetch commits using GitPython
        try:
            commits = list(self.repo.iter_commits("HEAD", max_count=self.max_commits))
        except Exception as e:
            print(f"[!] Warning: Could not retrieve commits from HEAD: {e}")
            return {"commits": 0, "authors": 0, "issues": 0, "files": 0, "owns": 0}

        if not commits:
            print("[!] No commits found in repository.")
            return {"commits": 0, "authors": 0, "issues": 0, "files": 0, "owns": 0}

        print(f"[*] Parsing {len(commits)} commit(s) from '{self.repo_path.name}' using GitPython...")

        # Data structures for batch insertion
        authors_map: dict[str, dict[str, str]] = {}
        commit_nodes: list[dict[str, Any]] = []
        authored_edges: list[dict[str, str]] = []
        modified_by_edges: list[dict[str, Any]] = []
        files_map: dict[str, str] = {}
        issue_nodes: dict[str, dict[str, Any]] = {}
        fixes_edges: list[dict[str, str]] = []

        # Tracking for author -> file ownership computation
        # (author_email, file_path) -> {"commits": count, "lines": int}
        author_file_contributions: dict[tuple[str, str], dict[str, int]] = {}

        # Regex pattern to detect issue references like "fixes #123", "fixed #456", "close #789"
        issue_pattern = re.compile(
            r"(?i)\b(?:fixes|fixed|fix|closes|closed|resolves|resolved)\s+#(\d+)"
        )

        for commit in commits:
            commit_hash = commit.hexsha
            short_hash = commit.hexsha[:7]
            author_name = commit.author.name or "Unknown"
            author_email = (commit.author.email or "unknown@local").lower().strip()
            message = commit.message.strip()
            timestamp = commit.authored_date
            date_str = commit.authored_datetime.strftime("%Y-%m-%d %H:%M:%S")

            # Collect Author
            if author_email not in authors_map:
                authors_map[author_email] = {
                    "name": author_name,
                    "email": author_email,
                }

            # Collect Commit
            commit_nodes.append(
                {
                    "hash": commit_hash,
                    "short_hash": short_hash,
                    "author_name": author_name,
                    "author_email": author_email,
                    "message": message,
                    "timestamp": timestamp,
                    "date": date_str,
                }
            )

            # (Author)-[:AUTHORED]->(Commit)
            authored_edges.append(
                {
                    "author_email": author_email,
                    "commit_hash": commit_hash,
                }
            )

            # Parse files modified in this commit using GitPython stats
            try:
                stat_files = commit.stats.files
            except Exception:
                stat_files = {}

            for raw_path, stats in stat_files.items():
                normalized_path = raw_path.replace("\\", "/").strip()
                file_name = Path(normalized_path).name

                if normalized_path not in files_map:
                    files_map[normalized_path] = file_name

                insertions = stats.get("insertions", 0)
                deletions = stats.get("deletions", 0)
                lines_changed = stats.get("lines", insertions + deletions)

                # (Commit)-[:MODIFIED_BY]->(File)
                modified_by_edges.append(
                    {
                        "commit_hash": commit_hash,
                        "file_path": normalized_path,
                        "insertions": insertions,
                        "deletions": deletions,
                        "lines": lines_changed,
                    }
                )

                # Track for OWNS edge computation
                contrib_key = (author_email, normalized_path)
                if contrib_key not in author_file_contributions:
                    author_file_contributions[contrib_key] = {
                        "commits": 0,
                        "lines": 0,
                    }
                author_file_contributions[contrib_key]["commits"] += 1
                author_file_contributions[contrib_key]["lines"] += lines_changed

            # Detect "fixes #123" in commit message
            issue_matches = issue_pattern.findall(message)
            for num_str in issue_matches:
                issue_id = f"#{num_str}"
                issue_num = int(num_str)
                if issue_id not in issue_nodes:
                    issue_nodes[issue_id] = {
                        "id": issue_id,
                        "number": issue_num,
                        "title": f"Issue {issue_id}",
                    }
                fixes_edges.append(
                    {
                        "commit_hash": commit_hash,
                        "issue_id": issue_id,
                    }
                )

        # 2. Insert into FalkorDB via batch queries
        print(f"[*] Inserting nodes & relationships into FalkorDB graph '{self.client.graph_name}'...")

        # Insert Authors
        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (a:Author {email: item.email})
            SET a.name = item.name
            """,
            list(authors_map.values()),
        )

        # Insert Commits
        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (c:Commit {hash: item.hash})
            SET c.short_hash = item.short_hash,
                c.author_name = item.author_name,
                c.author_email = item.author_email,
                c.message = item.message,
                c.timestamp = item.timestamp,
                c.date = item.date
            """,
            commit_nodes,
        )

        # Insert Files
        file_items = [{"path": p, "name": n} for p, n in files_map.items()]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (f:File {path: item.path})
            ON CREATE SET f.name = item.name
            """,
            file_items,
        )

        # Connect (Author)-[:AUTHORED]->(Commit)
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (a:Author {email: item.author_email})
            MATCH (c:Commit {hash: item.commit_hash})
            MERGE (a)-[:AUTHORED]->(c)
            """,
            authored_edges,
        )

        # Connect (Commit)-[:MODIFIED_BY]->(File)
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (c:Commit {hash: item.commit_hash})
            MATCH (f:File {path: item.file_path})
            MERGE (c)-[m:MODIFIED_BY]->(f)
            SET m.insertions = item.insertions,
                m.deletions = item.deletions,
                m.lines = item.lines
            """,
            modified_by_edges,
        )

        # Insert Issues and Connect (Commit)-[:FIXES]->(Issue)
        if issue_nodes:
            self._batch_exec(
                """
                UNWIND $batch AS item
                MERGE (i:Issue {id: item.id})
                SET i.number = item.number,
                    i.title = item.title
                """,
                list(issue_nodes.values()),
            )

            self._batch_exec(
                """
                UNWIND $batch AS item
                MATCH (c:Commit {hash: item.commit_hash})
                MATCH (i:Issue {id: item.issue_id})
                MERGE (c)-[:FIXES]->(i)
                """,
                fixes_edges,
            )

        # 3. Compute (Author)-[:OWNS]->(File) edges for the files each author changed most
        owns_count = self._compute_ownership(author_file_contributions)

        stats = {
            "commits": len(commit_nodes),
            "authors": len(authors_map),
            "files": len(files_map),
            "issues": len(issue_nodes),
            "modified_edges": len(modified_by_edges),
            "fixes_edges": len(fixes_edges),
            "owns_edges": owns_count,
        }

        print(f"[OK] Ingestion complete: {stats['commits']} commits, {stats['authors']} authors, "
              f"{stats['files']} files, {stats['issues']} issues, {stats['owns_edges']} OWNS edges.")
        return stats

    def _compute_ownership(
        self, author_file_contributions: dict[tuple[str, str], dict[str, int]]
    ) -> int:
        """
        Computes OWNS edges from each author to the files they changed most.
        For each author, sorts their touched files by commits and lines changed,
        and creates (a:Author)-[:OWNS]->(f:File).
        """
        # Group files per author
        files_by_author: dict[str, list[dict[str, Any]]] = {}
        for (author_email, file_path), contrib in author_file_contributions.items():
            if author_email not in files_by_author:
                files_by_author[author_email] = []
            files_by_author[author_email].append(
                {
                    "file_path": file_path,
                    "commits": contrib["commits"],
                    "lines": contrib["lines"],
                    # Composite score giving weight to both commit frequency and lines modified
                    "score": round(contrib["commits"] * 10.0 + contrib["lines"] * 0.1, 1),
                }
            )

        owns_items: list[dict[str, Any]] = []

        # For each author, select their most changed files (e.g. top files)
        for author_email, file_list in files_by_author.items():
            # Sort descending by commit count, then by lines changed
            sorted_files = sorted(
                file_list,
                key=lambda x: (x["commits"], x["lines"], x["score"]),
                reverse=True,
            )

            # Determine "changed most": top 10 files or all files if <= 10
            top_files = sorted_files[:10]

            for rank, item in enumerate(top_files, start=1):
                owns_items.append(
                    {
                        "author_email": author_email,
                        "file_path": item["file_path"],
                        "commits": item["commits"],
                        "lines_changed": item["lines"],
                        "score": item["score"],
                        "rank": rank,
                    }
                )

        # Batch insert OWNS edges into FalkorDB
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (a:Author {email: item.author_email})
            MATCH (f:File {path: item.file_path})
            MERGE (a)-[o:OWNS]->(f)
            SET o.commits = item.commits,
                o.lines_changed = item.lines_changed,
                o.score = item.score,
                o.rank = item.rank
            """,
            owns_items,
        )

        return len(owns_items)

    def print_top_owners_for_sample_files(self, sample_limit: int = 3, top_n: int = 5) -> None:
        """
        Finds sample files in the graph and prints their top owners with statistics.
        """
        print("\n" + "=" * 78)
        print(f"📊 CODE OWNERSHIP ANALYSIS: TOP {top_n} OWNERS FOR {sample_limit} SAMPLE FILES")
        print("=" * 78)

        # Query 3 sample files that have OWNS relationships
        sample_query = """
        MATCH (a:Author)-[o:OWNS]->(f:File)
        RETURN f.path AS path, count(a) AS owner_count, sum(o.commits) AS total_commits
        ORDER BY total_commits DESC, owner_count DESC, f.path ASC
        LIMIT $sample_limit
        """
        res = self.client.query(sample_query, {"sample_limit": sample_limit})

        sample_paths = [row[0] for row in res.result_set] if res.result_set else []

        # Fallback to any File nodes if no OWNS edges found yet
        if not sample_paths:
            fallback_res = self.client.query("MATCH (f:File) RETURN f.path LIMIT $sample_limit", {"sample_limit": sample_limit})
            sample_paths = [row[0] for row in fallback_res.result_set] if fallback_res.result_set else []

        if not sample_paths:
            print("[!] No files available in graph.")
            return

        for idx, file_path in enumerate(sample_paths, start=1):
            print(f"\n[{idx}] 📁 File: {file_path}")
            print("-" * 78)
            print(f"{'Rank':<6} {'Author Name':<28} {'Email':<30} {'Commits':<8} {'Lines Changed':<12}")
            print("-" * 78)

            owner_query = """
            MATCH (a:Author)-[o:OWNS]->(f:File {path: $path})
            RETURN a.name, a.email, o.commits, o.lines_changed, o.score
            ORDER BY o.commits DESC, o.lines_changed DESC, o.score DESC
            LIMIT $top_n
            """
            owner_res = self.client.query(owner_query, {"path": file_path, "top_n": top_n})

            if not owner_res.result_set:
                print("   (No direct owner edges recorded for this file)")
                continue

            for rank, row in enumerate(owner_res.result_set, start=1):
                author_name = str(row[0])[:26]
                author_email = str(row[1])[:28]
                commits_count = row[2]
                lines_changed = row[3]
                print(f"#{rank:<5} {author_name:<28} {author_email:<30} {commits_count:<8} {lines_changed:<12}")

        print("=" * 78 + "\n")

    def _batch_exec(
        self, cypher: str, items: list[dict[str, Any]], batch_size: int = 500
    ) -> None:
        """Executes parameterized UNWIND Cypher batches."""
        if not items:
            return
        g = self.client.connect()
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            g.query(cypher, {"batch": batch})


def main():
    """CLI entrypoint for git_loader.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Load Git history into FalkorDB and compute OWNS edges."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to git repository (default: current directory)",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=500,
        help="Maximum commits to process (default: 500)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear graph before ingestion",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Number of sample files to inspect (default: 3)",
    )

    args = parser.parse_args()

    loader = GitLoader(repo_path=args.repo, max_commits=args.max_commits)
    loader.load_history(clear_graph=args.clear)
    loader.print_top_owners_for_sample_files(sample_limit=args.samples)


if __name__ == "__main__":
    main()
