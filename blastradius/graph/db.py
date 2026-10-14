"""
Database access layer for FalkorDB.
Simple, robust wrapper to connect, initialize indices, and query the graph.
"""

import logging
from typing import Any, List
from falkordb import FalkorDB, Graph
from blastradius.config import config
from blastradius.graph.schema import INDEX_QUERIES

logger = logging.getLogger(__name__)


class FalkorDBClient:
    """Manages connection and Cypher query execution for FalkorDB."""

    def __init__(self, host: str = config.FALKORDB_HOST,
                 port: int = config.FALKORDB_PORT,
                 password: str | None = config.FALKORDB_PASSWORD,
                 graph_name: str = config.GRAPH_NAME):
        self.host = host
        self.port = port
        self.password = password
        self.graph_name = graph_name
        self._client: FalkorDB | None = None
        self._graph: Graph | None = None

    def connect(self) -> Graph:
        """Establishes connection to FalkorDB and selects graph."""
        if self._graph is None:
            self._client = FalkorDB(
                host=self.host,
                port=self.port,
                password=self.password
            )
            self._graph = self._client.select_graph(self.graph_name)
        return self._graph

    @property
    def graph(self) -> Graph:
        """Returns the active Graph instance."""
        if self._graph is None:
            return self.connect()
        return self._graph

    def init_schema(self) -> None:
        """Creates indexes for fast lookups."""
        g = self.connect()
        for idx_query in INDEX_QUERIES:
            try:
                g.query(idx_query)
            except Exception as e:
                # FalkorDB may raise if index already exists
                logger.debug(f"Index notice: {e}")

    def clear(self) -> None:
        """Wipes the graph clean for fresh ingestion."""
        try:
            g = self.connect()
            g.delete()
            self._graph = self._client.select_graph(self.graph_name)
        except Exception:
            # Fallback if delete raises on non-existent graph
            pass

    def query(self, cypher: str, params: dict[str, Any] | None = None):
        """Executes a Cypher query and returns the QueryResult."""
        g = self.connect()
        return g.query(cypher, params)


# Global singleton instance for easy import across modules
db_client = FalkorDBClient()


def format_path(path_obj: Any) -> str:
    """
    Converts a FalkorDB Path object or list of hops into a readable chain:
    Example: [Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]
    """
    if not path_obj:
        return ""

    # If FalkorDB returns a Path instance
    if hasattr(path_obj, "nodes") and hasattr(path_obj, "edges"):
        nodes = path_obj.nodes() if callable(path_obj.nodes) else path_obj.nodes
        edges = path_obj.edges() if callable(path_obj.edges) else path_obj.edges

        parts = []
        for i, node in enumerate(nodes):
            name = (
                node.properties.get("full_name")
                or node.properties.get("path")
                or node.properties.get("name")
                or str(node.id)
            )
            label = node.labels[0] if getattr(node, "labels", None) else "Node"
            parts.append(f"[{label}:{name}]")

            if i < len(edges):
                edge = edges[i]
                rel_type = getattr(edge, "relation", getattr(edge, "type", "RELATED_TO"))
                parts.append(f"--({rel_type})-->")

        return " ".join(parts)

    return str(path_obj)
