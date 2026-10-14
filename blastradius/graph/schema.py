"""
Graph Schema Definitions for BlastRadius.

This module defines the node labels, relationship types, and indexing
strategies used to represent a code repository inside FalkorDB.
"""

from dataclasses import dataclass


class NodeLabel:
    """Labels for nodes stored in the FalkorDB graph."""
    FILE = "File"
    FUNCTION = "Function"
    CLASS = "Class"
    COMMIT = "Commit"
    AUTHOR = "Author"


class RelationType:
    """Edge types representing code and git relationships."""
    CONTAINS = "CONTAINS"     # File -> Function/Class, or Class -> Method
    IMPORTS = "IMPORTS"       # File -> File
    CALLS = "CALLS"           # Function -> Function
    INHERITS = "INHERITS"     # Class -> Class
    TESTS = "TESTS"           # TestFunction -> TargetFunction
    AUTHORED = "AUTHORED"     # Author -> Commit
    MODIFIED = "MODIFIED"     # Commit -> File


# Cypher commands to build indices for high-performance traversals
INDEX_QUERIES = [
    f"CREATE INDEX FOR (f:{NodeLabel.FILE}) ON (f.path)",
    f"CREATE INDEX FOR (fn:{NodeLabel.FUNCTION}) ON (fn.full_name)",
    f"CREATE INDEX FOR (c:{NodeLabel.CLASS}) ON (c.full_name)",
    f"CREATE INDEX FOR (a:{NodeLabel.AUTHOR}) ON (a.email)",
    f"CREATE INDEX FOR (cm:{NodeLabel.COMMIT}) ON (cm.hash)",
]
