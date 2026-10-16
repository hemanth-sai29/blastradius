# 💥 BlastRadius

> **Graph Hacks — Track 1: Agents That Act on Connected Data**  
> An autonomous AI agent powered by **FalkorDB** and the official **Model Context Protocol (MCP)** that performs multi-hop code impact analysis, shortest path call chain tracing, centrality assessment, test discovery, and automated PR risk commentary.

---

## 🌟 Key Features

1. **Multi-Hop Reasoning on Connected Code**: Traverses deep, multi-edge relationships across `File`, `Function`, `Class`, `Commit`, and `Author` nodes in a real repository graph.
2. **Graph Algorithms Exposed as Agent Tools**:
   - 💥 **Blast Radius**: Calculates downstream ripple effects and impact scores (0–100) when code changes.
   - 🧭 **Shortest Path**: Traces exact call chains and import paths between any two symbols.
   - 🎯 **Centrality & Hubs**: Pinpoints critical architectural bottlenecks and high incoming coupling.
   - 🧪 **Test Discovery**: Traverses upstream callers to identify direct and transitive test coverage and untested gaps.
   - 👥 **Reviewer Recommendation**: Recommends subject matter expert reviewers based on git commit history and touched blast zone files.
3. **Official MCP Server**: Implements the official Model Context Protocol using Python's `mcp` SDK to seamlessly serve graph intelligence to AI IDEs (Claude Desktop, Cursor, Antigravity, etc.).
4. **Actionable PR Risk Commentary**: Automatically generates production-ready GitHub/GitLab PR comments with dynamic risk badges (`🚨 CRITICAL RISK`, `🔴 HIGH RISK`, `🟡 MEDIUM RISK`, `🟢 LOW RISK`), test gaps, affected critical hubs, and collapsible graph paths.
5. **Full Explainability**: Every answer includes the exact multi-hop graph path:
   ```text
   [Function:blastradius/config.py:_detect_falkordb_host] --(CALLS)--> [Function:blastradius/config.py:_is_port_open]
   ```
6. **Zero Mocked Data**: Parses live code repositories via Python AST and Git commit history directly into FalkorDB.

---

## 📁 Project Architecture

```
blastradius/
├── config.py                 # Smart FalkorDB host discovery (localhost, WSL2, cloud)
├── cli.py                    # Unified CLI command-line interface
├── graph/
│   ├── __init__.py           # Graph exports
│   ├── schema.py             # Node labels, relation types, and Cypher indexes
│   ├── db.py                 # FalkorDB client wrapper with path explainability
│   └── algorithms.py         # Multi-hop impact, shortest path, centrality, test discovery
├── ingester/
│   ├── __init__.py
│   ├── ast_parser.py         # Python AST parser (functions, classes, calls, imports)
│   ├── git_parser.py         # Git history parser (commits, authors, modifications)
│   └── builder.py            # Graph construction engine
├── mcp_server/
│   ├── __init__.py
│   └── server.py             # Official Python MCP server with 7 graph tools
├── agent/
│   ├── __init__.py
│   ├── reasoner.py           # Architectural smell diagnosis & multi-hop explanation
│   └── pr_reviewer.py        # Automated PR risk report & Markdown comment generator
└── tests/
    ├── test_step1_db.py      # Step 1: FalkorDB connection & path explainability
    ├── test_step2_ingester.py# Step 2: Live AST & Git graph ingestion
    ├── test_step3_algorithms.py # Step 3: Graph algorithms (impact, shortest path, hubs)
    ├── test_step4_mcp.py     # Step 4: Official MCP server protocol & tools
    └── test_step5_agent.py   # Step 5: Agent reasoning & automated PR risk commentary
```

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.11+
- FalkorDB running on port `6379`
  ```bash
  docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
  ```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Step-by-Step Verification Tests
Verify all 5 steps one by one or all together:
```bash
# Step 1: FalkorDB connection, indices, and Cypher path formatting
python tests/test_step1_db.py

# Step 2: AST & Git history ingestion from live codebase
python tests/test_step2_ingester.py

# Step 3: Graph algorithms (Blast radius, shortest path, centrality hubs)
python tests/test_step3_algorithms.py

# Step 4: Official MCP server tools & async protocol
python tests/test_step4_mcp.py

# Step 5: Autonomous agent reasoning & automated PR comment generator
python tests/test_step5_agent.py
```

---

## 💻 CLI Usage Guide

BlastRadius provides a command-line interface:

### 1. Ingest Repository
Ingest a Python repository into FalkorDB:
```bash
python -m blastradius.cli ingest --repo .
```

### 2. Calculate Blast Radius
Compute the downstream impact of changing a function or file:
```bash
python -m blastradius.cli blast connect --depth 4
```

### 3. Trace Shortest Path
Trace the call chain between any two functions:
```bash
python -m blastradius.cli path blastradius/config.py:_detect_falkordb_host blastradius/config.py:_is_port_open
```

### 4. Identify Central Hub Functions
Identify architectural bottlenecks and high-coupling functions:
```bash
python -m blastradius.cli hubs --limit 5
```

### 5. Discover Test Coverage
Find all tests that cover a function or file directly or indirectly:
```bash
python -m blastradius.cli tests blastradius/graph/db.py
```

### 6. Generate PR Risk Assessment
Evaluate PR impact and output Markdown comments:
```bash
python -m blastradius.cli review --files blastradius/graph/db.py --output pr_comment.md
```

### 7. Diagnose Architectural Smells
Detect circular imports, orphan functions, and critical hubs:
```bash
python -m blastradius.cli diagnose
```

### 8. Run Official MCP Server
Launch the MCP server in standard input/output (stdio) mode:
```bash
python -m blastradius.cli serve-mcp
```

---

## 🔌 Model Context Protocol (MCP) Configuration

To connect BlastRadius to an MCP client like Claude Desktop, Cursor, or Antigravity, add this configuration to your MCP config file:

```json
{
  "mcpServers": {
    "blastradius": {
      "command": "python",
      "args": ["-m", "blastradius.cli", "serve-mcp"],
      "env": {
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6379"
      }
    }
  }
}
```

### MCP Tools Provided:
| Tool Name | Description |
| :--- | :--- |
| `ingest_codebase` | Ingests a local Git & Python codebase into FalkorDB |
| `get_blast_radius` | Calculates downstream impact score and impacted functions |
| `get_shortest_path` | Traces multi-hop call chains between two symbols |
| `get_central_hubs` | Finds high-centrality hub functions with degree analysis |
| `discover_tests` | Identifies direct and indirect test coverage for target files |
| `recommend_reviewers` | Suggests expert reviewers based on git authorship history |
| `query_graph` | Runs raw Cypher queries for agent reasoning |

---

## 📊 Sample Generated PR Review Comment

```markdown
## 💥 BlastRadius PR Risk Assessment

> **Autonomous multi-hop impact analysis powered by FalkorDB graph reasoning.**

| 🚦 Risk Tier | 📊 Impact Score | 🧩 Impacted Functions | 📁 Dependent Files | 🧪 Test Coverage |
| :---: | :---: | :---: | :---: | :---: |
| **🚨 CRITICAL RISK** | **100.0 / 100** | `26` downstream | `15` files | ✅ Covered (4 tests) |

---

### 📁 Modified Files
- `blastradius/graph/db.py`

### ⚠️ Critical Hubs Affected
The following high-centrality functions are directly or transitively in the blast zone:
- 🔴 `blastradius/graph/algorithms.py:GraphAlgorithms.calculate_blast_radius`
- 🔴 `blastradius/graph/algorithms.py:GraphAlgorithms.find_shortest_path`

### 👥 Suggested Reviewers
- **BlastRadius Developer** (`dev@blastradius.local`) — touched `blastradius/graph/db.py` (score: `20.8`)

<details>
<summary>🔍 <b>Multi-Hop Graph Explainability Chains</b></summary>

```text
[Function:blastradius/graph/db.py:FalkorDBClient.graph] --(CALLS)--> [Function:blastradius/graph/db.py:FalkorDBClient.connect]
[Function:blastradius/graph/db.py:FalkorDBClient.query] --(CALLS)--> [Function:blastradius/graph/db.py:FalkorDBClient.connect]
```
</details>
```

---

## 🏆 Graph Hacks Track 1 Alignment

- **Multi-Hop Reasoning**: Follows multi-tier call and import graphs (`File -> Function -> Calls -> Function -> Test`).
- **Graph Algorithms as Tools**: Calculates blast radius, shortest paths, and degree centrality as native agent tools.
- **Official MCP Server**: Built using Python's official `mcp` SDK with full schema and type checking.
- **Actionable Outputs**: Automatically assesses risk tiers, checks test coverage gaps, and recommends code reviewers.
- **Full Path Explainability**: Every query result formats and returns the exact Cypher path traversal.
