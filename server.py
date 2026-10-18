"""
server.py - Official MCP Server wrapping tools.py graph analysis tools.

Exposes 6 read-only graph intelligence tools powered by FalkorDB:
1. impact_analysis: What breaks if a function changes (downstream blast radius).
2. suggest_reviewers: Who should review code based on authorship and ownership.
3. explain_origin: Traces code provenance back to commits, issues, and authors.
4. shortest_path: How two code elements are connected.
5. critical_nodes: Discovers critical architectural bottlenecks and hubs.
6. find_clusters: Community detection grouping cohesive module boundaries.

Built with the official Model Context Protocol (MCP) Python SDK.
Enforces read-only safety and input validation via Pydantic.
"""

import logging
import os
import sys
from typing import Annotated, Any
from pydantic import Field
from mcp.server.mcpserver import MCPServer

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from blastradius.graph.db import FalkorDBClient, db_client
from tools import (
    impact_analysis as _impact_analysis,
    suggest_reviewers as _suggest_reviewers,
    explain_origin as _explain_origin,
    shortest_path as _shortest_path,
    critical_nodes as _critical_nodes,
    find_clusters as _find_clusters,
)

logger = logging.getLogger("blastradius.mcp_server")


class ReadOnlyGraphClient:
    """
    Read-only proxy wrapping FalkorDBClient to strictly prevent
    mutating Cypher operations (CREATE, MERGE, SET, DELETE, DROP, DETACH).
    """

    def __init__(self, inner: Any):
        self._inner = inner

    def query(self, cypher: str, params: dict[str, Any] | None = None):
        forbidden = {"CREATE", "MERGE", "SET", "DELETE", "DROP", "DETACH"}
        tokens = {word.strip(";(),\"'").upper() for word in cypher.split()}
        if any(tok in forbidden for tok in tokens):
            raise PermissionError(
                "Write operations are forbidden. This MCP server operates in strictly READ-ONLY mode."
            )
        return self._inner.query(cypher, params)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def create_server(
    client: FalkorDBClient | None = None, read_only: bool = True
) -> MCPServer:
    """
    Creates and configures the official MCP Server with all 6 tools.
    Read-only by default to ensure database integrity.
    """
    raw_client = client or db_client
    target_client = ReadOnlyGraphClient(raw_client) if read_only else raw_client

    server = MCPServer(
        name="blastradius-tools",
        version="1.0.0",
        description=(
            "Official FalkorDB Code Graph MCP Server (READ-ONLY). Provides autonomous agents "
            "with multi-hop impact analysis, reviewer recommendations, origin tracing, shortest paths, "
            "centrality hubs, and community detection."
        ),
        instructions=(
            "This server is strictly READ-ONLY. Use these graph intelligence tools to inspect, "
            "reason about, and explain connected code relationships, blast radius impacts, "
            "and historical provenance without modifying any repository state."
        ),
    )

    # --------------------------------------------------------------------------
    # Tool 1: impact_analysis
    # --------------------------------------------------------------------------
    @server.tool(
        name="impact_analysis",
        description=(
            "Use this tool when the user asks what could break if a function changes, "
            "wants to calculate the downstream blast radius, or needs to know which callers "
            "and dependent modules are affected by modifying a function. "
            "Performs reverse multi-hop traversal over CALLS and IMPORTS."
        ),
    )
    def impact_analysis(
        function_name: Annotated[
            str,
            Field(
                min_length=1,
                description="The name or full_name of the target function to evaluate (e.g. 'login' or 'auth/service.py:login').",
            ),
        ],
        depth: Annotated[
            int,
            Field(
                default=3,
                ge=1,
                le=10,
                description="Maximum reverse traversal depth for multi-hop callers and imports (1 to 10). Default is 3.",
            ),
        ] = 3,
    ) -> dict[str, Any]:
        """Calculates downstream blast radius and impacted callers/files."""
        clean_name = function_name.strip()
        if not clean_name:
            raise ValueError("Parameter 'function_name' cannot be empty or whitespace.")
        return _impact_analysis(clean_name, depth=depth, client=target_client)

    # --------------------------------------------------------------------------
    # Tool 2: suggest_reviewers
    # --------------------------------------------------------------------------
    @server.tool(
        name="suggest_reviewers",
        description=(
            "Use this tool when the user asks who should review a pull request, "
            "who has domain expertise in a specific file or function, or who is the designated code owner. "
            "Recommends reviewers based on git authorship history, commit counts, and code ownership (OWNS) metrics."
        ),
    )
    def suggest_reviewers(
        file_or_function: Annotated[
            str,
            Field(
                min_length=1,
                description="File path (e.g. 'auth/service.py') or function name (e.g. 'login') to find expert reviewers for.",
            ),
        ],
    ) -> dict[str, Any]:
        """Recommends subject matter expert reviewers and code owners."""
        clean_target = file_or_function.strip()
        if not clean_target:
            raise ValueError("Parameter 'file_or_function' cannot be empty or whitespace.")
        return _suggest_reviewers(clean_target, client=target_client)

    # --------------------------------------------------------------------------
    # Tool 3: explain_origin
    # --------------------------------------------------------------------------
    @server.tool(
        name="explain_origin",
        description=(
            "Use this tool when the user asks where a function came from, why it was implemented, "
            "which git commits introduced it, which authors wrote it, or which issue tickets (e.g. 'fixes #123') "
            "it resolved. Traces full historical provenance."
        ),
    )
    def explain_origin(
        function_name: Annotated[
            str,
            Field(
                min_length=1,
                description="The name or full_name of the function to trace back to commits, issues, and authors.",
            ),
        ],
    ) -> dict[str, Any]:
        """Traces function provenance back to introducing commits, resolved issues, and authors."""
        clean_name = function_name.strip()
        if not clean_name:
            raise ValueError("Parameter 'function_name' cannot be empty or whitespace.")
        return _explain_origin(clean_name, client=target_client)

    # --------------------------------------------------------------------------
    # Tool 4: shortest_path
    # --------------------------------------------------------------------------
    @server.tool(
        name="shortest_path",
        description=(
            "Use this tool when the user asks how two code elements are connected, "
            "how function A reaches or calls function B, or what the dependency chain between two modules is. "
            "Discovers the shortest multi-hop path across CALLS, IMPORTS, and CONTAINS edges."
        ),
    )
    def shortest_path(
        source: Annotated[
            str,
            Field(
                min_length=1,
                description="Starting code symbol or file path (e.g. 'api/routes.py:login_route').",
            ),
        ],
        target: Annotated[
            str,
            Field(
                min_length=1,
                description="Destination code symbol or file path (e.g. 'auth/jwt.py:verify_token').",
            ),
        ],
    ) -> dict[str, Any]:
        """Finds the shortest call or import dependency chain connecting two code elements."""
        src_clean = source.strip()
        dst_clean = target.strip()
        if not src_clean or not dst_clean:
            raise ValueError("Both 'source' and 'target' parameters must be non-empty strings.")
        return _shortest_path(src_clean, dst_clean, client=target_client)

    # --------------------------------------------------------------------------
    # Tool 5: critical_nodes
    # --------------------------------------------------------------------------
    @server.tool(
        name="critical_nodes",
        description=(
            "Use this tool when the user asks what the most critical, central, or riskiest functions "
            "in the codebase are, or wants to identify architectural bottlenecks and high-fan-in hubs "
            "with heavy incoming caller coupling."
        ),
    )
    def critical_nodes(
        top_n: Annotated[
            int,
            Field(
                default=5,
                ge=1,
                le=50,
                description="Number of top central hub functions to return (1 to 50). Default is 5.",
            ),
        ] = 5,
    ) -> dict[str, Any]:
        """Identifies top architectural bottlenecks and high-centrality hub functions."""
        return _critical_nodes(top_n=top_n, client=target_client)

    # --------------------------------------------------------------------------
    # Tool 6: find_clusters
    # --------------------------------------------------------------------------
    @server.tool(
        name="find_clusters",
        description=(
            "Use this tool when the user asks about the modular structure of the repository, "
            "how files and functions are grouped into architectural communities, "
            "or wants community detection across package and dependency boundaries."
        ),
    )
    def find_clusters() -> dict[str, Any]:
        """Performs community detection grouping files and functions into module clusters."""
        return _find_clusters(client=target_client)

    return server


# Global instance for direct imports and standard execution
mcp_server = create_server()


def main():
    """Main CLI entry point for running the MCP server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the BlastRadius MCP server over standard input/output (stdio)."
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse"],
        help="MCP transport protocol (default: stdio)",
    )
    args = parser.parse_args()

    # Run in stdio mode for MCP clients and inspectors
    try:
        mcp_server.run(transport=args.transport)
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)


if __name__ == "__main__":
    main()
