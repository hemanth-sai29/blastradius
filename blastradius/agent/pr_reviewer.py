"""
Automated PR Risk Commentary Generator for BlastRadius.
Calculates risk tiers, aggregates downstream impact, detects uncovered gaps,
recommends expert reviewers, and formats a production-ready GitHub/GitLab PR Markdown comment.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from blastradius.graph.algorithms import (
    BlastRadiusResult,
    GraphAlgorithms,
    ReviewerRecommendation,
)
from blastradius.graph.db import FalkorDBClient, db_client

logger = logging.getLogger(__name__)


@dataclass
class PRRiskReport:
    risk_tier: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    risk_badge: str  # emoji badge
    overall_score: float
    modified_files: list[str]
    total_impacted_functions: int
    total_impacted_files: int
    critical_hubs_affected: list[str]
    covered_tests: list[str]
    uncovered_targets: list[str]
    recommended_reviewers: list[ReviewerRecommendation]
    explainability_paths: list[str]
    markdown_comment: str


class PRReviewer:
    """Evaluates pull request impact and produces actionable risk comments."""

    def __init__(self, client: FalkorDBClient | None = None):
        self.client = client or db_client
        self.algorithms = GraphAlgorithms(client=self.client)

    def review_files(self, modified_files: list[str]) -> PRRiskReport:
        """
        Runs comprehensive graph analysis over all modified files in a PR.
        """
        all_impacted_funcs: dict[str, Any] = {}
        all_impacted_files: set[str] = set()
        all_hubs: set[str] = set()
        all_covered_tests: set[str] = set()
        all_uncovered_targets: set[str] = set()
        explainability_paths: list[str] = []
        max_file_score = 0.0

        for file_path in modified_files:
            file_clean = file_path.replace("\\", "/").strip()
            blast = self.algorithms.calculate_blast_radius(file_clean)

            if blast.impact_score > max_file_score:
                max_file_score = blast.impact_score

            all_impacted_files.update(blast.impacted_files)
            all_hubs.update(blast.critical_hubs_affected)

            for fn in blast.impacted_functions:
                all_impacted_funcs[fn.full_name] = fn
                if fn.path_explanation:
                    explainability_paths.append(fn.path_explanation)

            # Test discovery
            cov = self.algorithms.discover_tests(file_clean)
            if cov.is_covered:
                all_covered_tests.update(cov.test_functions)
            else:
                all_uncovered_targets.add(file_clean)

        # Remove modified files themselves from downstream impacted files for clean stats
        downstream_files = all_impacted_files - set(
            f.replace("\\", "/") for f in modified_files
        )

        # Reviewer recommendations based on modified files + touched blast zone
        touch_set = list(set(modified_files) | downstream_files)
        reviewers = self.algorithms.recommend_reviewers(touch_set, limit=3)

        # Overall composite score (0-100)
        overall_score = min(
            100.0,
            round(
                max_file_score
                + len(all_impacted_funcs) * 1.5
                + len(all_hubs) * 5.0
                + (15.0 if all_uncovered_targets else 0.0),
                1,
            ),
        )

        # Determine Risk Tier
        if overall_score >= 70.0 or len(all_hubs) >= 3:
            risk_tier = "CRITICAL"
            risk_badge = "🚨 CRITICAL RISK"
        elif overall_score >= 45.0 or len(all_hubs) >= 1:
            risk_tier = "HIGH"
            risk_badge = "🔴 HIGH RISK"
        elif overall_score >= 20.0 or len(all_impacted_funcs) >= 5:
            risk_tier = "MEDIUM"
            risk_badge = "🟡 MEDIUM RISK"
        else:
            risk_tier = "LOW"
            risk_badge = "🟢 LOW RISK"

        # Format Markdown PR Comment
        markdown = self._generate_markdown(
            risk_tier=risk_tier,
            risk_badge=risk_badge,
            overall_score=overall_score,
            modified_files=modified_files,
            total_impacted_functions=len(all_impacted_funcs),
            total_impacted_files=len(downstream_files),
            critical_hubs=sorted(list(all_hubs)),
            covered_tests=sorted(list(all_covered_tests)),
            uncovered_targets=sorted(list(all_uncovered_targets)),
            reviewers=reviewers,
            paths=list(dict.fromkeys(explainability_paths)),
        )

        return PRRiskReport(
            risk_tier=risk_tier,
            risk_badge=risk_badge,
            overall_score=overall_score,
            modified_files=modified_files,
            total_impacted_functions=len(all_impacted_funcs),
            total_impacted_files=len(downstream_files),
            critical_hubs_affected=sorted(list(all_hubs)),
            covered_tests=sorted(list(all_covered_tests)),
            uncovered_targets=sorted(list(all_uncovered_targets)),
            recommended_reviewers=reviewers,
            explainability_paths=list(dict.fromkeys(explainability_paths)),
            markdown_comment=markdown,
        )

    def _generate_markdown(
        self,
        risk_tier: str,
        risk_badge: str,
        overall_score: float,
        modified_files: list[str],
        total_impacted_functions: int,
        total_impacted_files: int,
        critical_hubs: list[str],
        covered_tests: list[str],
        uncovered_targets: list[str],
        reviewers: list[ReviewerRecommendation],
        paths: list[str],
    ) -> str:
        """Constructs an aesthetic, highly informative GitHub/GitLab PR comment."""
        test_status = (
            f"✅ Covered ({len(covered_tests)} tests)"
            if not uncovered_targets
            else f"⚠️ Gaps ({len(uncovered_targets)} files untested)"
        )

        lines = [
            "## 💥 BlastRadius PR Risk Assessment",
            "",
            "> **Autonomous multi-hop impact analysis powered by FalkorDB graph reasoning.**",
            "",
            "| 🚦 Risk Tier | 📊 Impact Score | 🧩 Impacted Functions | 📁 Dependent Files | 🧪 Test Coverage |",
            "| :---: | :---: | :---: | :---: | :---: |",
            f"| **{risk_badge}** | **{overall_score} / 100** | `{total_impacted_functions}` downstream | `{total_impacted_files}` files | {test_status} |",
            "",
            "---",
            "",
            "### 📁 Modified Files",
        ]
        for mf in modified_files:
            lines.append(f"- `{mf}`")

        # Critical Hubs section
        if critical_hubs:
            lines.extend(
                [
                    "",
                    "### ⚠️ Critical Hubs Affected",
                    "The following high-centrality functions are directly or transitively in the blast zone:",
                ]
            )
            for h in critical_hubs:
                lines.append(f"- 🔴 `{h}`")
        else:
            lines.extend(
                [
                    "",
                    "### 🛡️ Architecture Integrity",
                    "No high-coupling architectural hub functions are affected.",
                ]
            )

        # Test Discovery & Coverage section
        lines.extend(["", "### 🧪 Test Coverage Analysis"])
        if covered_tests:
            lines.append("**Associated Tests Found:**")
            for t in covered_tests[:5]:
                lines.append(f"- ✅ `{t}`")
            if len(covered_tests) > 5:
                lines.append(f"  *(and {len(covered_tests) - 5} more)*")

        if uncovered_targets:
            lines.append("")
            lines.append("**⚠️ Test Gap Warning — Files lacking direct test coverage:**")
            for u in uncovered_targets:
                lines.append(f"- ❌ `{u}`")

        # Reviewer Recommendations section
        lines.extend(["", "### 👥 Suggested Reviewers"])
        if reviewers:
            lines.append(
                "Based on git authorship history and touched blast zone files:"
            )
            for r in reviewers:
                files_str = ", ".join(f"`{f}`" for f in r.files_touched[:2])
                lines.append(
                    f"- **{r.author_name}** (`{r.author_email}`) — touched {files_str} (score: `{r.score}`)"
                )
        else:
            lines.append("- *(No specific git authors found for touched files)*")

        # Collapsible Explainability Paths section
        if paths:
            lines.extend(
                [
                    "",
                    "---",
                    "",
                    f"<details>",
                    f"<summary>🔍 <b>Multi-Hop Graph Explainability Chains ({len(paths)} paths)</b></summary>",
                    "",
                    "```text",
                ]
            )
            for p in paths[:20]:
                lines.append(p)
            if len(paths) > 20:
                lines.append(f"... and {len(paths) - 20} additional call chains")
            lines.extend(["```", "</details>"])

        lines.extend(
            [
                "",
                "---",
                "*Report generated by [BlastRadius](https://github.com/falkordb/falkordb) • Graph Hacks Track 1: Agents That Act on Connected Data*",
            ]
        )

        return "\n".join(lines)
