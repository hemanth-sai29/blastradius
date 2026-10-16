"""
Graph Ingester for BlastRadius.
Coordinates AST and Git extraction, and populates FalkorDB with code graph knowledge.
"""

import logging
from pathlib import Path
from typing import Any

from blastradius.config import config
from blastradius.graph.db import FalkorDBClient, db_client
from blastradius.ingester.ast_parser import ASTParser
from blastradius.ingester.git_parser import GitParser

logger = logging.getLogger(__name__)


class RepoIngester:
    """Ingests a repository into FalkorDB as a connected code knowledge graph."""

    def __init__(
        self,
        repo_root: str | Path = config.DEFAULT_REPO_PATH,
        client: FalkorDBClient | None = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.client = client or db_client
        self.ast_parser = ASTParser(self.repo_root)
        self.git_parser = GitParser(self.repo_root)

    def _batch_exec(self, cypher: str, items: list[dict[str, Any]], batch_size: int = 500):
        """Helper to run parameterized UNWIND batches."""
        if not items:
            return
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            try:
                self.client.query(cypher, {"batch": batch})
            except Exception as e:
                logger.error(f"Error executing batch query: {e}")

    def ingest(
        self,
        clear_existing: bool = True,
        max_commits: int = 100,
    ) -> dict[str, int]:
        """
        Runs the full ingestion pipeline:
        1. Parse AST (files, classes, functions, calls, imports)
        2. Parse Git history (authors, commits, modified files)
        3. Insert nodes & relationships into FalkorDB
        Returns a dict of counts.
        """
        logger.info(f"Starting ingestion of repository at: {self.repo_root}")

        if clear_existing:
            self.client.clear()
            self.client.init_schema()

        # 1. Parse AST
        parsed_files = self.ast_parser.parse_repo()
        resolved_imports = self.ast_parser.resolve_imports(parsed_files, self.repo_root)
        resolved_calls, resolved_tests = self.ast_parser.resolve_calls(parsed_files)

        # 2. Parse Git
        authors, commits = self.git_parser.parse_history(max_commits=max_commits)

        # 3. Insert Nodes
        # Files
        file_items = [
            {"path": f.path, "name": f.name, "loc": f.loc} for f in parsed_files
        ]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (f:File {path: item.path})
            SET f.name = item.name, f.loc = item.loc
            """,
            file_items,
        )

        # Classes
        class_items = []
        class_inherits_items = []
        for f in parsed_files:
            for cls in f.classes:
                class_items.append(
                    {
                        "full_name": cls.full_name,
                        "name": cls.name,
                        "file_path": cls.file_path,
                        "lineno": cls.lineno,
                        "end_lineno": cls.end_lineno,
                    }
                )
                for base in cls.bases:
                    class_inherits_items.append(
                        {"sub_class": cls.full_name, "base_name": base}
                    )

        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (c:Class {full_name: item.full_name})
            SET c.name = item.name, c.file_path = item.file_path,
                c.lineno = item.lineno, c.end_lineno = item.end_lineno
            """,
            class_items,
        )

        # Functions
        func_items = []
        file_func_items = []
        class_func_items = []
        for f in parsed_files:
            for fn in f.functions:
                func_items.append(
                    {
                        "full_name": fn.full_name,
                        "name": fn.name,
                        "file_path": fn.file_path,
                        "class_name": fn.class_name or "",
                        "lineno": fn.lineno,
                        "end_lineno": fn.end_lineno,
                        "is_test": fn.is_test,
                        "docstring": fn.docstring,
                    }
                )
                if fn.class_name:
                    class_func_items.append(
                        {
                            "class_full_name": f"{fn.file_path}:{fn.class_name}",
                            "func_full_name": fn.full_name,
                        }
                    )
                else:
                    file_func_items.append(
                        {
                            "file_path": fn.file_path,
                            "func_full_name": fn.full_name,
                        }
                    )

        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (fn:Function {full_name: item.full_name})
            SET fn.name = item.name, fn.file_path = item.file_path,
                fn.class_name = item.class_name, fn.lineno = item.lineno,
                fn.end_lineno = item.end_lineno, fn.is_test = item.is_test,
                fn.docstring = item.docstring
            """,
            func_items,
        )

        # Authors
        author_items = [{"name": a.name, "email": a.email} for a in authors]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (a:Author {email: item.email})
            SET a.name = item.name
            """,
            author_items,
        )

        # Commits
        commit_items = [
            {
                "hash": cm.hash,
                "short_hash": cm.short_hash,
                "message": cm.message,
                "timestamp": cm.timestamp,
            }
            for cm in commits
        ]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MERGE (cm:Commit {hash: item.hash})
            SET cm.short_hash = item.short_hash, cm.message = item.message,
                cm.timestamp = item.timestamp
            """,
            commit_items,
        )

        # 4. Insert Relationships
        # File CONTAINS Class
        file_class_items = [
            {"file_path": c["file_path"], "class_full_name": c["full_name"]}
            for c in class_items
        ]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (f:File {path: item.file_path})
            MATCH (c:Class {full_name: item.class_full_name})
            MERGE (f)-[:CONTAINS]->(c)
            """,
            file_class_items,
        )

        # File CONTAINS Function (top-level)
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (f:File {path: item.file_path})
            MATCH (fn:Function {full_name: item.func_full_name})
            MERGE (f)-[:CONTAINS]->(fn)
            """,
            file_func_items,
        )

        # Class CONTAINS Function (methods)
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (c:Class {full_name: item.class_full_name})
            MATCH (fn:Function {full_name: item.func_full_name})
            MERGE (c)-[:CONTAINS]->(fn)
            """,
            class_func_items,
        )

        # Class INHERITS Class
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (sub:Class {full_name: item.sub_class})
            MATCH (base:Class {name: item.base_name})
            MERGE (sub)-[:INHERITS]->(base)
            """,
            class_inherits_items,
        )

        # File IMPORTS File
        import_items = [{"src": src, "dst": dst} for src, dst in resolved_imports]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (src:File {path: item.src})
            MATCH (dst:File {path: item.dst})
            MERGE (src)-[:IMPORTS]->(dst)
            """,
            import_items,
        )

        # Function CALLS Function
        call_items = [{"caller": c[0], "callee": c[1]} for c in resolved_calls]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (caller:Function {full_name: item.caller})
            MATCH (callee:Function {full_name: item.callee})
            MERGE (caller)-[:CALLS]->(callee)
            """,
            call_items,
        )

        # Function TESTS Function
        test_items = [{"tester": t[0], "target": t[1]} for t in resolved_tests]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (tester:Function {full_name: item.tester})
            MATCH (target:Function {full_name: item.target})
            MERGE (tester)-[:TESTS]->(target)
            """,
            test_items,
        )

        # Author AUTHORED Commit
        authored_items = [
            {"author_email": cm.author_email, "commit_hash": cm.hash}
            for cm in commits
        ]
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (a:Author {email: item.author_email})
            MATCH (cm:Commit {hash: item.commit_hash})
            MERGE (a)-[:AUTHORED]->(cm)
            """,
            authored_items,
        )

        # Commit MODIFIED File
        modified_items = []
        for cm in commits:
            for mod in cm.modifications:
                modified_items.append(
                    {
                        "commit_hash": cm.hash,
                        "file_path": mod.file_path,
                        "insertions": mod.insertions,
                        "deletions": mod.deletions,
                    }
                )
        self._batch_exec(
            """
            UNWIND $batch AS item
            MATCH (cm:Commit {hash: item.commit_hash})
            MATCH (f:File {path: item.file_path})
            MERGE (cm)-[:MODIFIED {insertions: item.insertions, deletions: item.deletions}]->(f)
            """,
            modified_items,
        )

        stats = {
            "files": len(file_items),
            "classes": len(class_items),
            "functions": len(func_items),
            "imports": len(import_items),
            "calls": len(call_items),
            "tests": len(test_items),
            "authors": len(author_items),
            "commits": len(commit_items),
            "file_modifications": len(modified_items),
        }

        logger.info(f"Ingestion complete: {stats}")
        return stats
