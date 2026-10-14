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
    Intelligently determines the best host for FalkorDB:
    1. Explicit FALKORDB_HOST environment variable.
    2. Localhost / 127.0.0.1 if port 6379 is listening.
    3. WSL2 IP if on Windows where Docker runs in WSL.
    4. Defaults to 127.0.0.1.
    """
    env_host = os.getenv("FALKORDB_HOST")
    if env_host:
        return env_host

    port = int(os.getenv("FALKORDB_PORT", "6379"))

    # 1. Test 127.0.0.1
    if _is_port_open("127.0.0.1", port, timeout=0.3):
        return "127.0.0.1"

    # 2. If on Windows, check WSL2 IP
    if os.name == "nt":
        try:
            res = subprocess.run(
                ["wsl", "hostname", "-I"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0 and res.stdout.strip():
                ips = res.stdout.strip().split()
                for ip in ips:
                    if _is_port_open(ip, port, timeout=0.5):
                        return ip
        except Exception:
            pass

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
