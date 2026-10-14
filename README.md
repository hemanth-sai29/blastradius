# 💥 BlastRadius

> **Graph Hacks — Track 1: Agents That Act on Connected Data**  
> An AI agent powered by **FalkorDB** and the official **Model Context Protocol (MCP)** that performs multi-hop code impact analysis, shortest path tracing, centrality assessment, test discovery, and automated PR risk commentary.

---

## 🌟 Key Features

1. **Multi-Hop Reasoning**: Traverses deep relationships across files, functions, classes, commits, and authors.
2. **Graph Algorithms as Tools**:
   - 💥 **Blast Radius**: Calculates ripple effects and downstream impact scores when code changes.
   - 🧭 **Shortest Path**: Traces exact call chains and import paths between any two symbols.
   - 🎯 **PageRank / Centrality**: Pinpoints high-risk hub functions with high incoming coupling.
   - 🧪 **Test Discovery**: Identifies direct and indirect test coverage for affected code.
3. **Official MCP Server**: Exposes graph algorithms as standardized tools to AI agents using the official Python MCP SDK.
4. **Actionable Outputs**:
   - Suggests subject-matter expert reviewers based on git authorship and touched blast zones.
   - Generates production-ready Markdown PR comments with risk tiers.
5. **Explainability**: Every answer includes the exact multi-hop graph path:
   ```text
   [Function:auth/service.py:login] --(CALLS)--> [Function:auth/jwt.py:verify_token]
   ```

---

## 📁 Project Architecture

```
blastradius/
├── config.py             # Smart FalkorDB host discovery (localhost, WSL2, cloud)
├── graph/
│   ├── schema.py         # Node labels, relation types, and Cypher indexes
│   └── db.py             # FalkorDB client wrapper with path explainability
├── ingester/             # (Step 2) Python AST & Git history graph builder
├── mcp_server/           # (Step 4) Official MCP server implementation
├── agent/                # (Step 5) Multi-hop reasoning agent & PR actions
└── tests/
    └── test_step1_db.py  # Step 1 database & schema verification
```

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.11+
- FalkorDB running on port `6379` (Docker image: `falkordb/falkordb:latest`)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Verify Step 1
```bash
python tests/test_step1_db.py
```
