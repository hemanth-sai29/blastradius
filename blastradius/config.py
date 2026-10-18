"""
Configuration for BlastRadius.
Handles connection parameters for FalkorDB and repository paths.
Supports auto-detection for Docker running natively, in WSL2, or in Cloud.
"""

import os
import socket
import subprocess
from dataclasses import dataclass


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Checks if a host:port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _detect_falkordb_host() -> str:
    """
    Determines the host for FalkorDB:
    1. Explicit FALKORDB_HOST environment variable.
    2. Probes localhost using _is_port_open, then defaults to '127.0.0.1'.
    """
    env_host = os.getenv("FALKORDB_HOST")
    if env_host:
        return env_host
    if _is_port_open("127.0.0.1", 6379):
        return "127.0.0.1"
    return "127.0.0.1"


@dataclass
class Config:
    # FalkorDB connection settings
    FALKORDB_HOST: str = _detect_falkordb_host()
    FALKORDB_PORT: int = int(os.getenv("FALKORDB_PORT", "6379"))
    FALKORDB_PASSWORD: str | None = os.getenv("FALKORDB_PASSWORD", None)

    # Graph name inside FalkorDB
    GRAPH_NAME: str = os.getenv("GRAPH_NAME", "blastradius_repo")

    # Default repo path (can be overridden by command-line args)
    DEFAULT_REPO_PATH: str = os.getenv("REPO_PATH", ".")


config = Config()
