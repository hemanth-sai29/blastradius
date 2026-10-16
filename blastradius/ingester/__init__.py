"""
Ingester module for BlastRadius.
Extracts code architecture via Python AST and git history.
"""

from blastradius.ingester.builder import RepoIngester

__all__ = ["RepoIngester"]
