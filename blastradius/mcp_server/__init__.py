"""
Official MCP Server package for BlastRadius.
Exposes FalkorDB graph reasoning tools via the Model Context Protocol.
"""

from blastradius.mcp_server.server import create_mcp_server, mcp_server

__all__ = ["create_mcp_server", "mcp_server"]
