"""
Git History Parser for BlastRadius.
Extracts authors, commits, and modified file relationships from git logs.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileModification:
    file_path: str
    insertions: int
    deletions: int


@dataclass
class ParsedAuthor:
    name: str
    email: str


@dataclass
class ParsedCommit:
    hash: str
    short_hash: str
    author_name: str
    author_email: str
    timestamp: int
    message: str
    modifications: list[FileModification] = field(default_factory=list)


class GitParser:
    """Parses git history into authors, commits, and file modification stats."""

    def __init__(self, repo_root: str | Path = "."):
        self.repo_root = Path(repo_root).resolve()

    def parse_history(
        self, max_commits: int = 100
    ) -> tuple[list[ParsedAuthor], list[ParsedCommit]]:
        """
        Runs `git log` with numstat and parses commits and file changes.
        Returns:
            authors: list of unique ParsedAuthor
            commits: list of ParsedCommit with modifications
        """
        cmd = [
            "git",
            "log",
            f"--pretty=format:COMMIT_START|%H|%h|%an|%ae|%at|%s",
            "--numstat",
            f"-n{max_commits}",
        ]

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Git history could not be retrieved: {e}")
            return [], []

        authors_by_email: dict[str, ParsedAuthor] = {}
        commits: list[ParsedCommit] = []
        current_commit: ParsedCommit | None = None

        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("COMMIT_START|"):
                if current_commit:
                    commits.append(current_commit)

                parts = line.split("|", 6)
                if len(parts) >= 7:
                    _, h_full, h_short, a_name, a_email, a_time, msg = parts
                    author_email = a_email.lower().strip()
                    author_name = a_name.strip()

                    if author_email not in authors_by_email:
                        authors_by_email[author_email] = ParsedAuthor(
                            name=author_name, email=author_email
                        )

                    current_commit = ParsedCommit(
                        hash=h_full.strip(),
                        short_hash=h_short.strip(),
                        author_name=author_name,
                        author_email=author_email,
                        timestamp=int(a_time.strip()) if a_time.strip().isdigit() else 0,
                        message=msg.strip(),
                        modifications=[],
                    )
            elif current_commit:
                # Numstat line: <insertions>\t<deletions>\t<filename>
                parts = line.split("\t")
                if len(parts) == 3:
                    ins_str, del_str, file_path = parts
                    ins = int(ins_str) if ins_str.isdigit() else 0
                    dels = int(del_str) if del_str.isdigit() else 0
                    normalized_path = file_path.replace("\\", "/").strip()
                    current_commit.modifications.append(
                        FileModification(
                            file_path=normalized_path,
                            insertions=ins,
                            deletions=dels,
                        )
                    )

        if current_commit:
            commits.append(current_commit)

        return list(authors_by_email.values()), commits
