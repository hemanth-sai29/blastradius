# Why I gave my code review agent a graph

*By a student builder who got tired of watching AI hallucinate code reviews.*

---

Like almost every computer science student working with generative AI over the past year, I started with what felt like the obvious playbook: Retrieval-Augmented Generation (RAG) and raw prompt stuffing. 

Whenever my classmates or I submitted a pull request for a team project, we dreamed of having an autonomous AI senior engineer that could look at our changes and tell us: *"Hey, if you rename this parameter in `auth.py`, you are about to silently break the checkout worker three directories over."*

So, naturally, I did what the tutorials told me to do. I chunked our repository into 500-token text snippets, shoved them into a vector database, computed cosine embeddings, and fed git diffs into an LLM with a system prompt that begged it to *"thoroughly analyze downstream impact."*

It was an utter disaster.

---

### The Lie of Vector Similarity for Code

The failure became obvious the moment I tested our vector-based bot on a simple change. 

I modified the return type of a utility function in an authentication module. The vector search dutifully retrieved five chunks of code that had high semantic similarity: files full of words like "token", "session", and "credentials". But it completely missed the actual function that called our utility—because that caller happened to live inside a module named `event_bus.py`, which used totally different vocabulary. 

Even worse, the LLM hallucinated connections that didn't exist. It confidently told me that our change would break three other services, weaving a plausible-sounding bedtime story about shared variables that had zero basis in reality.

That was my lightbulb moment, and it hit me with the force of an introductory data structures lecture: **Source code is not unstructured prose. Code is a graph.**

When a Python file imports a module, that is a directed edge. When a function executes another function, that is an edge. When a developer authors a commit that closes an issue ticket, that is an edge. By treating code as flat chunks of natural language text, I was stripping away the very topology that gives software its meaning. 

I didn't need a larger language model. I needed to give my agent a graph.

---

### Enter FalkorDB: Grounding Code in Connected Reality

Once I decided to represent our codebase as a graph, the next question was the database. I needed something fast enough to run locally during CI or live inside an IDE, with a query language expressive enough to traverse multi-tier call chains without writing hundreds of lines of recursive Python.

That brought me to **FalkorDB**. 

FalkorDB is built for lightning-fast graph operations powered by Cypher. Using Python’s built-in `ast` parser and `GitPython`, I wrote an ingestion pipeline that parses a live repository into six distinct node types:
- `(:File)`
- `(:Function)`
- `(:Class)`
- `(:Commit)`
- `(:Author)`
- `(:Issue)`

Connecting them are the real-world relationships of software development: `CALLS`, `IMPORTS`, `CONTAINS`, `AUTHORED`, `MODIFIED_BY`, `FIXES`, and `OWNS`.

Suddenly, the questions that broke my vector search became trivial, single-digit-millisecond Cypher queries. 

To find what could break downstream when someone touches a function, I didn’t have to ask an LLM to guess. I had FalkorDB run a transitive breadth-first traversal up the `CALLS` and `IMPORTS` edges:

```cypher
MATCH p = (caller:Function)-[:CALLS*1..3]->(target:Function {name: $name})
RETURN caller.full_name, length(p) AS depth, p
```

When I tested this on **Pallets Flask**—a codebase with over 80 files and nearly 1,500 functions—the downstream blast radius computation took just **39 milliseconds**. 

---

### What Changed: Proof, Not Vibes

The most profound transformation wasn't speed; it was honesty.

In traditional LLM apps, "confidence" is an illusion produced by temperature and token probabilities. But with a graph, every answer comes with a mathematical proof: an exact Cypher path:

```text
[Function:create_app] --(CALLS)--> [Function:Config.from_mapping] 
  --(CALLS)--> [Function:update] 
  --(CALLS)--> [Function:get_post] 
  --(CALLS)--> [Function:abort]
```

When we asked the agent whether an application factory in Celery could trigger Flask's core `abort()` function, neither file imported the other. A human skimming the PR diff would never notice the connection. But FalkorDB traced the exact 4-hop call chain across architectural boundaries in **2.3 milliseconds**.

And when two functions were completely disconnected? The Cypher query returned zero records. Instead of making up a connection to please the user, the agent simply said: *"No graph path connects these symbols."* 

Zero hallucinations. That single behavioral guarantee changed my perception of what AI agents can do.

---

### The Architectural Insights I Didn't Expect

As a student, building BlastRadius taught me more about software engineering than three semesters of lectures. 

First, I discovered that **centrality reveals technical debt**. When I computed degree centrality across Flask, functions like `app_context` and `test_client` emerged with in-degrees over 30. If a pull request modifies one of these central hubs, the risk isn't just high—it is systemic. We turned this into automated PR risk badges (`🚨 CRITICAL RISK`, `🟡 MEDIUM RISK`), warning reviewers before an innocent-looking merge triggered regressions.

Second, I learned the power of **transitive test discovery**. By traversing upstream from modified functions to nodes marked with `is_test: true`, the agent automatically identifies which specific tests in the repository provide coverage for the changed code—and which modified functions have zero test paths touching them.

Third, by implementing the official **Model Context Protocol (MCP)**, I realized that graph-backed agents shouldn't live in isolated chat windows. By exposing our graph algorithms as 7 standard MCP tools, any AI IDE—Cursor, Claude Desktop, or Antigravity—can query the graph natively while you write code.

---

### What I Learned

If this project taught me one thing, it’s that the current AI hype cycle often encourages us to throw more parameters at problems that actually require better data structures.

Large language models are incredible at synthesizing language, translating intent, and formatting reports. But they are lousy databases. When you try to make an LLM remember the call topology of 2,000 functions, it will let you down. But when you pair an LLM with a high-performance graph database like FalkorDB, each tool does what it was born to do: FalkorDB computes the ground truth with mathematical precision, and the LLM translates that truth into actionable engineering advice.

Code was always a graph. We just needed to stop treating it like text.

---

### 🔗 Project Links
- **GitHub Repository**: [https://github.com/hemanth-sai29/blastradius](https://github.com/hemanth-sai29/blastradius)
- **3-Minute Demo Video**: [Watch on YouTube](https://youtu.be/THem7fTU__U)
- **Track**: Graph Hacks — Track 1: Agents That Act on Connected Data (with Track 2 Memory Graph bonus)
