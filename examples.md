# 💥 BlastRadius Code Graph Agent — 5 Example Scenarios

This document demonstrates **`agent.py`**, an autonomous LLM agent that connects to the official Model Context Protocol (MCP) server (`server.py`) powered by **FalkorDB**.

For every question, the agent:
1. **Picks the right tool(s)** based on user intent.
2. **Calls more than one tool** when the question requires multi-angle reasoning.
3. **Always returns**:
   - 🗣️ **Plain-language answer**
   - 🧭 **Exact multi-hop graph path(s)**
   - 🛠️ **List of tools called and why**
4. **Refuses to hallucinate**: If the graph has no answer, it explicitly states so instead of guessing.

---

## 📋 Table of Examples

| # | Question / Scenario | Tools Called | Pattern |
| :-: | :--- | :--- | :--- |
| **1** | [Downstream Blast Radius Impact](#example-1-downstream-blast-radius-impact) | `impact_analysis` | Single-Tool |
| **2** | [Code Provenance & Issue Origin](#example-2-code-provenance--issue-origin) | `explain_origin` | Single-Tool |
| **3** | [Impact Analysis + Reviewer Recommendation](#example-3-impact-analysis--reviewer-recommendation) | `impact_analysis`, `suggest_reviewers` | **Multi-Tool** |
| **4** | [Shortest Call Chain + Centrality Bottlenecks](#example-4-shortest-call-chain--centrality-bottlenecks) | `shortest_path`, `critical_nodes` | **Multi-Tool** |
| **5** | [Honest Refusal (Graph Has No Answer)](#example-5-honest-refusal-graph-has-no-answer) | `impact_analysis` | **Zero-Hallucination** |

---

## Example 1: Downstream Blast Radius Impact

### User Question
```bash
python agent.py "What could break if I modify function 'connect' in blastradius/graph/db.py?"
```

### Agent Response
```text
======================================================================
QUESTION: What could break if I modify function 'connect' in blastradius/graph/db.py?
======================================================================

1. PLAIN-LANGUAGE ANSWER:
• [Downstream Impact]: Modifying 'connect' risks breaking 14 function(s) across 6 file(s) within depth 3. Key callers include: blastradius/graph/db.py:FalkorDBClient.query, blastradius/graph/db.py:FalkorDBClient.init_schema, blastradius/graph/algorithms.py:GraphAlgorithms.calculate_blast_radius, blastradius/ingester/builder.py:RepoIngester.ingest (+9 more). Dependent modules: blastradius/graph/db.py, blastradius/graph/algorithms.py, blastradius/ingester/builder.py.

----------------------------------------------------------------------
2. EXACT GRAPH PATHS TRAVERSED (4 path(s)):
   [1] [Function:blastradius/graph/db.py:FalkorDBClient.query] --(CALLS)--> [Function:blastradius/graph/db.py:FalkorDBClient.connect]
   [2] [Function:blastradius/graph/db.py:FalkorDBClient.init_schema] --(CALLS)--> [Function:blastradius/graph/db.py:FalkorDBClient.connect]
   [3] [Function:blastradius/graph/algorithms.py:GraphAlgorithms.calculate_blast_radius] --(CALLS)--> [Function:blastradius/graph/db.py:FalkorDBClient.query] --(CALLS)--> [Function:blastradius/graph/db.py:FalkorDBClient.connect]
   [4] [File:blastradius/graph/algorithms.py] --(IMPORTS)--> [File:blastradius/graph/db.py]

----------------------------------------------------------------------
3. TOOLS CALLED & REASONING (1 tool(s)):
   • Tool: impact_analysis
     Args: {"function_name": "connect", "depth": 3}
     Why:  To calculate downstream blast radius and identify affected callers/modules for 'connect'.
======================================================================
```

---

## Example 2: Code Provenance & Issue Origin

### User Question
```bash
python agent.py "Where did 'load_history' come from, who wrote it, and what issues did it resolve?"
```

### Agent Response
```text
======================================================================
QUESTION: Where did 'load_history' come from, who wrote it, and what issues did it resolve?
======================================================================

1. PLAIN-LANGUAGE ANSWER:
• [Origin Provenance]: 'load_history' was authored by Seenu across 2 commit(s) (5db75a5, 88c0601), resolving issue(s) #123, #101.

----------------------------------------------------------------------
2. EXACT GRAPH PATHS TRAVERSED (3 path(s)):
   [1] [Author:Seenu] --(AUTHORED)--> [Commit:5db75a5]
   [2] [Commit:5db75a5] --(MODIFIED_BY)--> [File:git_loader.py] --(CONTAINS)--> [Function:git_loader.py:GitLoader.load_history]
   [3] [Commit:5db75a5] --(FIXES)--> [Issue:#123]

----------------------------------------------------------------------
3. TOOLS CALLED & REASONING (1 tool(s)):
   • Tool: explain_origin
     Args: {"function_name": "load_history"}
     Why:  To trace the historical provenance, introducing commits, and issue tickets for 'load_history'.
======================================================================
```

---

## Example 3: Impact Analysis + Reviewer Recommendation
*(Demonstrates multi-tool composition: combining downstream blast radius evaluation with git ownership ranking).*

### User Question
```bash
python agent.py "What breaks if I change 'verify_token' and who should review it?"
```

### Agent Response
```text
======================================================================
QUESTION: What breaks if I change 'verify_token' and who should review it?
======================================================================

1. PLAIN-LANGUAGE ANSWER:
• [Downstream Impact]: Modifying 'verify_token' risks breaking 2 function(s) across 2 file(s) within depth 3. Key callers include: auth/service.py:login, api/routes.py:login_route. Dependent modules: auth/service.py, api/routes.py.
• [Suggested Reviewers]: For changes to 'verify_token', recommended reviewers are: Alice Smith (alice@company.com, score: 32.5); Bob Jones (bob@company.com, score: 24.0).

----------------------------------------------------------------------
2. EXACT GRAPH PATHS TRAVERSED (4 path(s)):
   [1] [Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]
   [2] [Function:api/routes.py:login_route] --(CALLS)--> [Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]
   [3] [Author:Alice Smith] --(OWNS)--> [File:auth/service.py]
   [4] [Author:Alice Smith] --(AUTHORED)--> [Commit:c101] --(MODIFIED_BY)--> [File:auth/service.py]

----------------------------------------------------------------------
3. TOOLS CALLED & REASONING (2 tool(s)):
   • Tool: impact_analysis
     Args: {"function_name": "verify_token", "depth": 3}
     Why:  To calculate downstream blast radius and identify affected callers/modules for 'verify_token'.
   • Tool: suggest_reviewers
     Args: {"file_or_function": "verify_token"}
     Why:  To identify code owners and expert contributors qualified to review changes to 'verify_token'.
======================================================================
```

---

## Example 4: Shortest Call Chain + Centrality Bottlenecks
*(Demonstrates multi-tool composition: tracing call hops between two symbols and checking high-fan-in bottlenecks).*

### User Question
```bash
python agent.py "How does 'api/routes.py:login_route' connect to 'auth/jwt.py:verify_token', and what are the critical bottlenecks in the repo?"
```

### Agent Response
```text
======================================================================
QUESTION: How does 'api/routes.py:login_route' connect to 'auth/jwt.py:verify_token', and what are the critical bottlenecks in the repo?
======================================================================

1. PLAIN-LANGUAGE ANSWER:
• [Shortest Path]: 'api/routes.py:login_route' connects to 'auth/jwt.py:verify_token' in 2 hop(s).
• [Critical Hubs]: The highest-risk architectural bottlenecks are: verify_token (score: 10.0, in-callers: 3), login (score: 5.0, in-callers: 1), checkout (score: 4.0, in-callers: 1).

----------------------------------------------------------------------
2. EXACT GRAPH PATHS TRAVERSED (2 path(s)):
   [1] [Function:api/routes.py:login_route] --(CALLS)--> [Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]
   [2] [Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]

----------------------------------------------------------------------
3. TOOLS CALLED & REASONING (2 tool(s)):
   • Tool: shortest_path
     Args: {"source": "api/routes.py:login_route", "target": "auth/jwt.py:verify_token"}
     Why:  To trace the shortest multi-hop dependency path connecting 'api/routes.py:login_route' and 'auth/jwt.py:verify_token'.
   • Tool: critical_nodes
     Args: {"top_n": 5}
     Why:  To identify top 5 architectural bottlenecks and high-centrality hubs based on caller coupling.
======================================================================
```

---

## Example 5: Honest Refusal (Graph Has No Answer)
*(Demonstrates zero-hallucination guarantee: when a non-existent or unlinked function is queried, the agent refuses to fabricate data and explicitly reports that the graph has no answer).*

### User Question
```bash
python agent.py "What breaks if I modify 'legacy_billing_migration_v0'?"
```

### Agent Response
```text
======================================================================
QUESTION: What breaks if I modify 'legacy_billing_migration_v0'?
======================================================================

1. PLAIN-LANGUAGE ANSWER:
The graph database has NO answer for 'legacy_billing_migration_v0'. No matching nodes, edges, or historical records were found in FalkorDB. Rather than guessing or hallucinating details, the agent confirms that 'legacy_billing_migration_v0' is either unreferenced in the repository graph or does not exist.

----------------------------------------------------------------------
2. EXACT GRAPH PATHS TRAVERSED (0 path(s)):
   [None] No graph edges were traversed for this query.

----------------------------------------------------------------------
3. TOOLS CALLED & REASONING (1 tool(s)):
   • Tool: impact_analysis
     Args: {"function_name": "legacy_billing_migration_v0", "depth": 3}
     Why:  To calculate downstream blast radius and identify affected callers/modules for 'legacy_billing_migration_v0'.
======================================================================
```

---

## 🚀 Running the Agent Programmatically

You can also import and execute `CodeGraphAgent` directly inside Python or asynchronous workflows:

```python
import asyncio
from agent import CodeGraphAgent

async def main():
    agent = CodeGraphAgent()
    response = await agent.ask(
        "What breaks if I change FalkorDBClient.connect and who should review it?"
    )

    # 1. Plain-language answer
    print(response.answer)

    # 2. Graph paths traversed
    for path in response.paths:
        print("Path:", path)

    # 3. Tools called and rationale
    for tool_record in response.tools_called:
        print(f"Called {tool_record.tool} because: {tool_record.why}")

asyncio.run(main())
```

---

## ⚡ Autonomous Graph Actions & PR Review Pipeline

The agent supports **autonomous actions** triggered directly by graph metrics:
1. **HIGH RISK Flagging**: Triggered if a changed function has a high blast radius (many callers or dependent files).
2. **2 Best Reviewers with Graph Evidence**: Discovers the top 2 reviewers and explains the exact graph edges (`OWNS`, `AUTHORED`, commit history, lines changed) qualifying them.
3. **Ready-to-Post GitHub PR Comment**: Generates a production-ready Markdown comment with badges, caller lists, reviewer evidence, and collapsible graph paths.
4. **Dry Run Mode by Default**: All actions run in dry-run mode and render a complete preview. Passing `--execute` executes the action live (e.g., saving `pr_comment.md`).

### Dry Run Preview Execution
```bash
python agent.py --action review --target "verify_token"
```

#### Output Preview:
```text
======================================================================
[DRY RUN PREVIEW - NO CHANGES COMMITTED] Autonomous Code Graph Action Pipeline
Target Function: 'verify_token' | Mode: DRY RUN
======================================================================

[ACTION 1: RISK ASSESSMENT]
• Risk Level: 🚨 HIGH RISK
• Reason:     High blast radius triggered: modifying 'verify_token' affects 2 downstream caller(s) across 2 dependent file(s).
• Impacted:   2 function(s) across 2 file(s)

----------------------------------------------------------------------
[ACTION 2: 2 BEST SUGGESTED REVIEWERS (WITH GRAPH EVIDENCE)]
• Reviewer 1: Alice Smith <alice@company.com> (Designated Code Owner)
  Score:    32.5
  Evidence: Designated Code Owner via graph edge (Author:Alice Smith)-[:OWNS]->(File) [ownership score: 32.5, 3 commit(s), 105 lines changed].
• Reviewer 2: Bob Jones <bob@company.com> (Frequent Contributor)
  Score:    24.0
  Evidence: Frequent Contributor via graph chain (Author:Bob Jones)-[:AUTHORED]->(Commit)-[:MODIFIED_BY]->(File) [2 commit(s) touching blast zone, 80 lines changed, score: 24.0].

----------------------------------------------------------------------
[ACTION 3: READY-TO-POST GITHUB PR COMMENT (MARKDOWN)]
----------------------------------------------------------------------
## 💥 BlastRadius PR Impact & Risk Assessment

> **Autonomous multi-hop graph analysis powered by FalkorDB.**

| 🚦 Risk Tier | 🧩 Downstream Callers | 📁 Dependent Files | 👥 Best Reviewers | 🛡️ Status |
| :---: | :---: | :---: | :---: | :---: |
| **🚨 HIGH RISK** | `2` callers | `2` files | `2` suggested | 🟡 Preview (Dry Run) |

---

### ⚠️ Risk Assessment
- **Level**: `HIGH RISK`
- **Trigger**: High blast radius triggered: modifying 'verify_token' affects 2 downstream caller(s) across 2 dependent file(s).

### 📁 Target Modified Function
- `verify_token`

### 🧩 Affected Functions in Blast Zone (2)
- 🔴 `auth/service.py:login`
- 🔴 `api/routes.py:login_route`

### 👥 2 Best Suggested Reviewers (with Graph Evidence)
1. **Alice Smith** (`alice@company.com`) — *Designated Code Owner* (Score: `32.5`)
   > **Graph Evidence**: `Designated Code Owner via graph edge (Author:Alice Smith)-[:OWNS]->(File) [ownership score: 32.5, 3 commit(s), 105 lines changed].`
2. **Bob Jones** (`bob@company.com`) — *Frequent Contributor* (Score: `24.0`)
   > **Graph Evidence**: `Frequent Contributor via graph chain (Author:Bob Jones)-[:AUTHORED]->(Commit)-[:MODIFIED_BY]->(File) [2 commit(s) touching blast zone, 80 lines changed, score: 24.0].`

---

<details>
<summary>🔍 <b>Multi-Hop Graph Path(s) Traversed (4 paths)</b></summary>

```text
[Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]
[Function:api/routes.py:login_route] --(CALLS)--> [Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]
[Author:Alice Smith] --(OWNS)--> [File:auth/service.py]
[Author:Bob Jones] --(AUTHORED)--> [Commit:c102] --(MODIFIED_BY)--> [File:auth/jwt.py]
```
</details>

### 📋 Reviewer Checklist
- [ ] Verify regression tests for 2 affected downstream caller(s)
- [ ] Inspect cross-module boundary contracts for 2 dependent file(s)
- [ ] Obtain review sign-off from suggested domain expert(s)

---
*Generated by [BlastRadius](https://github.com/falkordb/falkordb) Code Graph Agent • Dry Run Mode*
----------------------------------------------------------------------

[DRY RUN NOTICE]:
Actions are in DRY RUN mode by default. No external comments were posted.
To execute these actions live (e.g. write to pr_comment.md),
pass '--execute' or call 'run_pr_actions(..., dry_run=False)'.
======================================================================
```

### Live Execution Mode
To write the Markdown comment to disk and commit the actions:
```bash
python agent.py --action review --target "verify_token" --execute --output-file pr_comment.md
```
Output:
```text
[EXECUTION CONFIRMED]: Successfully wrote ready-to-post GitHub PR comment to 'pr_comment.md'.
```

