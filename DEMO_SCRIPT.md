# 💥 BlastRadius: 3-Minute Demo Video Script

**Title**: BlastRadius — Autonomous Code Review Agent Powered by FalkorDB & MCP  
**Track**: Graph Hacks — Track 1: Agents That Act on Connected Data  
**Total Running Time**: Exactly 3 Minutes (180 Seconds)  
**Presenter Tone**: Confident, energetic, student builder voice, technically precise.

---

## ⏱️ Video Timeline Overview

| Section | Timestamp | Focus | Visual / Screen Action |
| :--- | :---: | :--- | :--- |
| **1. The Hook** | 0:00 – 0:25 | The blindspot in modern code review | Pull request diff on GitHub showing a 1-line change |
| **2. The Architecture** | 0:25 – 0:55 | Why code is a graph, not flat text | Mermaid architecture diagram & FalkorDB graph schema |
| **3. Live Demo on Flask** | 0:55 – 1:45 | `demo.py` answering 3 multi-hop questions | Terminal running `python demo.py` with millisecond timings |
| **4. Web UI & Memory** | 1:45 – 2:25 | Cytoscape.js visualizer & episodic memory | Browser showing `http://localhost:5000`, path highlights, memory recall |
| **5. Official MCP Server** | 2:25 – 2:45 | IDE integration with zero hallucination | MCP server config JSON & tool protocol execution |
| **6. Closing** | 2:45 – 3:00 | Summary & submission wrap-up | Project GitHub repository & summary slide |

---

## 🎬 Scene-by-Scene Script

### [0:00 – 0:25] Scene 1: The Hook — The Fatal Flaw of Flat Code Review

**[VISUAL]**:  
Full screen screen-recording of a GitHub Pull Request diff. A developer changes a single helper function return signature (`def verify_token(...)`). A green checkmark appears next to "All CI tests passed".

**[VOICEOVER / PRESENTER]**:  
> "Every day, software engineering teams merge pull requests that look completely innocent on paper. A three-line tweak to a helper function. The unit tests pass. The reviewer clicks 'LGTM'.  
> And twenty minutes later, production crashes.  
> Why? Because code is **not** flat text. Code is a deeply connected, multi-tier dependency graph. A change in module A creates a ripple effect three hops away in module D that no flat regex, keyword search, or traditional LLM prompt can see.  
> To solve this, I built **BlastRadius**."

---

### [0:25 – 0:55] Scene 2: The Architecture — Giving the Agent a Graph

**[VISUAL]**:  
Smooth transition to the architecture diagram from the README. Camera zooms into the 3 layers: Ingestion ➔ FalkorDB Graph ➔ MCP Agent.

**[VOICEOVER / PRESENTER]**:  
> "BlastRadius is an autonomous code intelligence agent powered by **FalkorDB** and the official **Model Context Protocol (MCP)**.  
> Instead of feeding thousands of lines of raw source code into an LLM context window and praying it doesn't hallucinate, BlastRadius parses Python ASTs and Git history directly into a high-performance FalkorDB knowledge graph.  
> We track Functions, Files, Classes, Commits, and Authors, connected by `CALLS`, `IMPORTS`, `AUTHORED`, and `OWNS` edges.  
> When the agent needs to reason, it doesn't guess. It dispatches native graph algorithms: downstream blast radius, bidirectional shortest paths, degree centrality hubs, and test discovery."

---

### [0:55 – 1:45] Scene 3: Live Showcase — Ingesting Pallets Flask (`demo.py`)

**[VISUAL]**:  
Cut to clean terminal window. Presenter types:
```bash
python demo.py
```
Text streams with ANSI color formatting. Ingestion finishes in 1.1 seconds (83 files, 1,462 functions, 804 calls).

**[VOICEOVER / PRESENTER]**:  
> "Let's see it on a real-world, industry-standard codebase: the **Pallets Flask** web framework.  
> I run `demo.py`. In just one second, BlastRadius ingests 83 files and nearly 1,500 functions into FalkorDB. Now watch it answer three impressive questions:  
> **First: Downstream Blast Radius.** We ask: *What breaks if I change `Flask.app_context`?*  
> In just **39 milliseconds**, the agent computes a critical impact score of 100/100, revealing that changing `app_context` ripples into 26 functions across 12 files—including Celery background workers and integration tests. Every caller is backed by an exact Cypher traversal path.  
> **Second: Deep Shortest Path.** We ask: *How does an application factory function in Celery reach `abort()`?*  
> Neither file imports the other. But in **2 milliseconds**, FalkorDB discovers the exact 4-hop call chain: `create_app` calls `from_mapping`, which calls `update`, which calls `get_post`, which triggers `abort`. Mathematical proof of hidden coupling.  
> **Third: Automated PR Review.** For a pull request modifying `src/flask/app.py`, the agent identifies 5 critical hub bottlenecks in the blast zone, discovers 127 covered tests to run in CI, and formats a production-ready Markdown comment with collapsible graph paths."

---

### [1:45 – 2:25] Scene 4: Interactive Web UI & Episodic Memory

**[VISUAL]**:  
Browser window opens to `http://localhost:5000`. Presenter demonstrates the dark mode Cytoscape.js canvas. The user enters a question in the chat assistant. Red and cyan paths glow across the graph nodes. The presenter toggles to the Memory tab.

**[VOICEOVER / PRESENTER]**:  
> "For visual developers, BlastRadius comes with an interactive Web UI built in Cytoscape.js.  
> When you ask a question or evaluate a PR, the exact multi-hop path lights up across the graph in real time. You can zoom through clusters, inspect in-degree centrality, and toggle between dark and light themes.  
> Better yet, BlastRadius features **Episodic User Memory**. When a developer marks a finding as useful, it's stored in an isolated per-user subgraph in FalkorDB. On future code reviews, the agent recalls past architectural gotchas, creating an engineering assistant that actually learns your codebase over time."

---

### [2:25 – 2:45] Scene 5: Official Model Context Protocol (MCP)

**[VISUAL]**:  
Split screen: left side shows `server.py` and `mcpServers` JSON config; right side shows Cursor / Claude Desktop issuing a tool call to `get_blast_radius`.

**[VOICEOVER / PRESENTER]**:  
> "BlastRadius isn't a siloed tool. We built it on the official **Model Context Protocol (MCP)** using Python's official SDK.  
> With 7 registered tools—from `get_blast_radius` to `query_graph`—any modern AI IDE like Cursor, Claude Desktop, or Antigravity can connect directly to FalkorDB.  
> And because every response is grounded in Cypher path proofs, if the graph doesn't connect two symbols, the agent explicitly says so. **Zero hallucinations. 100% explainability.**"

---

### [2:45 – 3:00] Scene 6: Conclusion & Wrap-Up

**[VISUAL]**:  
Show the terminal running `python -m pytest tests/ -v` passing all 55 tests in 7 seconds. Then cut to the GitHub repository README.

**[VOICEOVER / PRESENTER]**:  
> "55 comprehensive tests, under 5-minute setup, and live graph reasoning that transforms code review from educated guesswork into verifiable graph science.  
> Code isn't text. Code is a graph.  
> Thank you, and welcome to BlastRadius!"

**[ON-SCREEN TEXT]**:  
💥 **BlastRadius**  
Graph Hacks 2026 — Track 1: Agents That Act on Connected Data  
Built with FalkorDB & Model Context Protocol
