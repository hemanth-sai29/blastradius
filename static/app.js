/**
 * app.js - Frontend controller for BlastRadius Code Graph Explorer & Memory System.
 * Connects FastAPI backend, Cytoscape.js interactive graph, per-user memory, and MCP tools inspector.
 */

let cy = null;
let currentHighlightedNodes = new Set();
let currentHighlightedEdges = new Set();
let allGraphElements = [];
let currentGraphMode = "code"; // "code" or "memory"

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  initUserSession();
  setupEventListeners();
  try {
    await initCytoscape();
  } catch (err) {
    console.error("Cytoscape init error:", err);
  }
  try {
    await loadPresetExamples();
  } catch (err) {
    console.error("Load examples error:", err);
  }
  try {
    await refreshMemoryDashboard();
  } catch (err) {
    console.error("Memory dashboard error:", err);
  }
});

// ------------------------------------------------------------------------------
// 1. Theme Management (Dark Mode Default)
// ------------------------------------------------------------------------------
function initTheme() {
  const savedTheme = localStorage.getItem("blastradius_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
  updateThemeIcon(savedTheme);
}

function updateThemeIcon(theme) {
  const icon = document.getElementById("themeIcon");
  if (icon) {
    icon.textContent = theme === "dark" ? "🌙" : "☀️";
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("blastradius_theme", next);
  updateThemeIcon(next);
  if (cy) {
    cy.style().update();
  }
}

// ------------------------------------------------------------------------------
// 2. User Session Management
// ------------------------------------------------------------------------------
function initUserSession() {
  const savedUser = localStorage.getItem("blastradius_user_id") || "alice";
  const inputEl = document.getElementById("inputUserId");
  if (inputEl) {
    inputEl.value = savedUser;
  }
}

function getActiveUserId() {
  const inputEl = document.getElementById("inputUserId");
  const val = inputEl ? inputEl.value.trim() : "";
  return val || localStorage.getItem("blastradius_user_id") || "alice";
}

// ------------------------------------------------------------------------------
// 3. Cytoscape.js Graph Initialization & Styling
// ------------------------------------------------------------------------------
async function initCytoscape() {
  const container = document.getElementById("cy");
  if (!container) return;

  // Fetch initial graph structure
  let graphData = { nodes: [], edges: [] };
  try {
    const res = await fetch("/api/graph");
    if (res.ok) {
      graphData = await res.json();
    }
  } catch (err) {
    console.warn("Could not load /api/graph, using fallback empty graph:", err);
  }

  // Convert to Cytoscape elements format with validation
  const elements = [];
  const nodeIds = new Set();
  (graphData.nodes || []).forEach((n) => {
    nodeIds.add(n.id);
    elements.push({
      group: "nodes",
      data: {
        id: n.id,
        label: n.label || n.id,
        type: n.type || "Node",
      },
    });
  });

  (graphData.edges || []).forEach((e) => {
    if (!nodeIds.has(e.source)) {
      nodeIds.add(e.source);
      elements.push({
        group: "nodes",
        data: { id: e.source, label: e.source, type: "Unknown" },
      });
    }
    if (!nodeIds.has(e.target)) {
      nodeIds.add(e.target);
      elements.push({
        group: "nodes",
        data: { id: e.target, label: e.target, type: "Unknown" },
      });
    }
    elements.push({
      group: "edges",
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label || "RELATED_TO",
      },
    });
  });

  allGraphElements = elements;

  // Cytoscape stylesheet supporting Code Graph and Memory Graph node/edge types
  cy = cytoscape({
    container: container,
    elements: elements,
    style: [
      // Base Node Style
      {
        selector: "node",
        style: {
          "label": "data(label)",
          "color": "#cbd5e1",
          "font-family": "Inter, sans-serif",
          "font-size": "10px",
          "font-weight": "500",
          "text-valign": "bottom",
          "text-margin-y": 5,
          "background-color": "#475569",
          "width": 26,
          "height": 26,
          "border-width": 2,
          "border-color": "#334155",
          "transition-property": "background-color, border-color, border-width, width, height, opacity",
          "transition-duration": "0.3s",
        },
      },
      // Code Graph Node Types
      {
        selector: "node[type = 'Function']",
        style: {
          "background-color": "#6366f1",
          "border-color": "#4f46e5",
          "shape": "ellipse",
        },
      },
      {
        selector: "node[type = 'File']",
        style: {
          "background-color": "#0ea5e9",
          "border-color": "#0284c7",
          "shape": "round-rectangle",
        },
      },
      {
        selector: "node[type = 'Author']",
        style: {
          "background-color": "#a855f7",
          "border-color": "#9333ea",
          "shape": "diamond",
        },
      },
      {
        selector: "node[type = 'Commit']",
        style: {
          "background-color": "#f59e0b",
          "border-color": "#d97706",
          "shape": "hexagon",
        },
      },
      {
        selector: "node[type = 'Issue']",
        style: {
          "background-color": "#10b981",
          "border-color": "#059669",
          "shape": "triangle",
        },
      },

      // Per-User Memory Graph Node Types
      {
        selector: "node[type = 'User']",
        style: {
          "background-color": "#06b6d4",
          "border-color": "#22d3ee",
          "border-width": 3,
          "shape": "hexagon",
          "width": 42,
          "height": 42,
          "font-weight": "700",
          "font-size": "11px",
          "color": "#ffffff",
        },
      },
      {
        selector: "node[type = 'Question']",
        style: {
          "background-color": "#3b82f6",
          "border-color": "#60a5fa",
          "border-width": 2,
          "shape": "round-rectangle",
          "width": 36,
          "height": 28,
        },
      },
      {
        selector: "node[type = 'CodeArea']",
        style: {
          "background-color": "#10b981",
          "border-color": "#34d399",
          "border-width": 2,
          "shape": "ellipse",
          "width": 32,
          "height": 32,
          "color": "#a7f3d0",
        },
      },
      {
        selector: "node[type = 'Finding']",
        style: {
          "background-color": "#f59e0b",
          "border-color": "#fbbf24",
          "border-width": 2,
          "shape": "diamond",
          "width": 32,
          "height": 32,
        },
      },
      {
        selector: "node[type = 'Finding'][marked_useful]",
        style: {
          "background-color": "#eab308",
          "border-color": "#fde047",
          "border-width": 4,
          "width": 38,
          "height": 38,
          "color": "#fef08a",
          "font-weight": "700",
        },
      },

      // Base Edge Style
      {
        selector: "edge",
        style: {
          "label": "data(label)",
          "color": "#64748b",
          "font-family": "JetBrains Mono, monospace",
          "font-size": "8px",
          "font-weight": "600",
          "text-rotation": "autorotate",
          "text-background-opacity": 0.8,
          "text-background-color": "#0f172a",
          "text-background-padding": 2,
          "text-background-shape": "roundrectangle",
          "width": 1.5,
          "line-color": "#334155",
          "target-arrow-color": "#334155",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "arrow-scale": 0.9,
          "transition-property": "line-color, target-arrow-color, width, opacity",
          "transition-duration": "0.3s",
        },
      },

      // Memory Graph Edges
      {
        selector: "edge[label = 'ASKED']",
        style: {
          "line-color": "#3b82f6",
          "target-arrow-color": "#3b82f6",
          "width": 2,
        },
      },
      {
        selector: "edge[label = 'TOUCHED_AREA']",
        style: {
          "line-color": "#10b981",
          "target-arrow-color": "#10b981",
          "width": 2,
        },
      },
      {
        selector: "edge[label = 'PRODUCED']",
        style: {
          "line-color": "#f59e0b",
          "target-arrow-color": "#f59e0b",
          "width": 2,
        },
      },
      {
        selector: "edge[label = 'RELATES_TO']",
        style: {
          "line-color": "#8b5cf6",
          "target-arrow-color": "#8b5cf6",
          "width": 1.5,
        },
      },
      {
        selector: "edge[label = 'MARKED_USEFUL']",
        style: {
          "line-color": "#fbbf24",
          "target-arrow-color": "#fbbf24",
          "line-style": "dashed",
          "width": 3,
        },
      },

      // DIMMED state when a path is being highlighted
      {
        selector: ".dimmed",
        style: {
          "opacity": 0.15,
        },
      },
      // ACTIVE PATH HIGHLIGHT: Glowing Nodes
      {
        selector: "node.highlighted",
        style: {
          "background-color": "#ec4899",
          "border-color": "#f43f5e",
          "border-width": 4,
          "width": 36,
          "height": 36,
          "color": "#ffffff",
          "font-size": "11px",
          "font-weight": "700",
          "z-index": 999,
          "opacity": 1,
        },
      },
      // ACTIVE PATH HIGHLIGHT: Glowing Directed Edges
      {
        selector: "edge.highlighted",
        style: {
          "width": 4,
          "line-color": "#ec4899",
          "target-arrow-color": "#ec4899",
          "color": "#ec4899",
          "text-background-color": "#831843",
          "text-background-opacity": 1,
          "z-index": 998,
          "opacity": 1,
          "arrow-scale": 1.3,
        },
      },
    ],
    layout: {
      name: "cose",
      animate: false,
      padding: 30,
      nodeRepulsion: 6500,
      idealEdgeLength: 60,
    },
  });

  // Center view
  cy.fit(undefined, 30);
}

function runGraphLayout(name = "cose") {
  if (!cy) return;
  const layout = cy.layout({
    name: name,
    animate: true,
    animationDuration: 500,
    padding: 30,
  });
  layout.run();
}

// ------------------------------------------------------------------------------
// 4. Graph Mode Switcher: Code Graph vs. Memory Graph
// ------------------------------------------------------------------------------
async function loadMemoryGraph() {
  currentGraphMode = "memory";
  const userId = getActiveUserId();
  const toggleBtn = document.getElementById("btnToggleMemoryGraph");
  if (toggleBtn) {
    toggleBtn.classList.add("active");
    const icon = document.getElementById("memoryGraphBtnIcon");
    const txt = document.getElementById("memoryGraphBtnText");
    if (icon) icon.textContent = "🧭";
    if (txt) txt.textContent = "Show Code Graph";
  }

  // Toggle legend items
  document.querySelectorAll(".legend-code").forEach((el) => (el.style.display = "none"));
  document.querySelectorAll(".legend-mem").forEach((el) => (el.style.display = "inline-flex"));

  try {
    const res = await fetch(`/api/memory/graph?user_id=${encodeURIComponent(userId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const badge = document.getElementById("pathStatusBadge");
    if (badge) {
      badge.textContent = `Memory Graph: ${userId} (${data.nodes.length} nodes, ${data.edges.length} edges)`;
    }

    if (cy) {
      cy.elements().remove();
      cy.add(data.nodes);
      cy.add(data.edges);
      runGraphLayout("cose");
    }
  } catch (err) {
    console.error("Failed to load memory graph:", err);
  }
}

async function loadCodeGraph() {
  currentGraphMode = "code";
  const toggleBtn = document.getElementById("btnToggleMemoryGraph");
  if (toggleBtn) {
    toggleBtn.classList.remove("active");
    const icon = document.getElementById("memoryGraphBtnIcon");
    const txt = document.getElementById("memoryGraphBtnText");
    if (icon) icon.textContent = "🧠";
    if (txt) txt.textContent = "Show My Memory Graph";
  }

  // Toggle legend items
  document.querySelectorAll(".legend-mem").forEach((el) => (el.style.display = "none"));
  document.querySelectorAll(".legend-code").forEach((el) => (el.style.display = "inline-flex"));

  const badge = document.getElementById("pathStatusBadge");
  if (badge) badge.textContent = "Path: Waiting for query";

  try {
    const res = await fetch("/api/graph");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (cy) {
      cy.elements().remove();
      const elements = [];
      const nodeIds = new Set();
      (data.nodes || []).forEach((n) => {
        nodeIds.add(n.id);
        elements.push({ group: "nodes", data: { id: n.id, label: n.label || n.id, type: n.type || "Node" } });
      });
      (data.edges || []).forEach((e) => {
        if (!nodeIds.has(e.source)) {
          nodeIds.add(e.source);
          elements.push({ group: "nodes", data: { id: e.source, label: e.source, type: "Unknown" } });
        }
        if (!nodeIds.has(e.target)) {
          nodeIds.add(e.target);
          elements.push({ group: "nodes", data: { id: e.target, label: e.target, type: "Unknown" } });
        }
        elements.push({ group: "edges", data: { id: e.id, source: e.source, target: e.target, label: e.label || "RELATED_TO" } });
      });
      cy.add(elements);
      runGraphLayout("cose");
    }
  } catch (err) {
    console.error("Failed to load code graph:", err);
  }
}

/**
 * Highlights the exact multi-hop graph path used in the latest agent answer.
 */
function highlightPathInGraph(highlightedElements) {
  if (!cy || !highlightedElements) return;

  // If currently in memory graph mode, stay focused or switch when answering code questions
  if (currentGraphMode === "memory") {
    return;
  }

  const hlNodes = highlightedElements.nodes || [];
  const hlEdges = highlightedElements.edges || [];

  if (hlNodes.length === 0 && hlEdges.length === 0) {
    document.getElementById("pathStatusBadge").textContent = "Path: None (unconnected)";
    return;
  }

  // 1. Add any dynamically discovered nodes/edges that aren't yet in Cytoscape
  cy.batch(() => {
    hlNodes.forEach((n) => {
      if (cy.getElementById(n.id).length === 0) {
        cy.add({
          group: "nodes",
          data: {
            id: n.id,
            label: n.label || n.id,
            type: n.type || "Function",
          },
        });
      }
    });

    hlEdges.forEach((e) => {
      if (cy.getElementById(e.source).length > 0 && cy.getElementById(e.target).length > 0) {
        if (cy.getElementById(e.id).length === 0) {
          cy.add({
            group: "edges",
            data: {
              id: e.id,
              source: e.source,
              target: e.target,
              label: e.label || "CALLS",
            },
          });
        }
      }
    });

    // 2. Dim all elements first
    cy.elements().removeClass("highlighted").addClass("dimmed");

    // 3. Highlight target nodes
    hlNodes.forEach((n) => {
      const nodeEl = cy.getElementById(n.id);
      if (nodeEl.length > 0) {
        nodeEl.removeClass("dimmed").addClass("highlighted");
      }
    });

    // 4. Highlight target edges
    hlEdges.forEach((e) => {
      let edgeEl = cy.getElementById(e.id);
      if (edgeEl.length === 0) {
        edgeEl = cy.edges(`[source = "${e.source}"][target = "${e.target}"]`);
      }
      if (edgeEl.length > 0) {
        edgeEl.removeClass("dimmed").addClass("highlighted");
      }
    });
  });

  document.getElementById("pathStatusBadge").textContent = `Path: ${hlNodes.length} nodes highlighted`;

  // Focus and zoom smoothly on the active path elements
  const activePathCollection = cy.elements(".highlighted");
  if (activePathCollection.length > 0) {
    cy.animate({
      fit: {
        eles: activePathCollection,
        padding: 50,
      },
      duration: 500,
    });
  }
}

function resetHighlights() {
  if (!cy) return;
  cy.batch(() => {
    cy.elements().removeClass("dimmed").removeClass("highlighted");
  });
  document.getElementById("pathStatusBadge").textContent = "Path: Cleared";
  cy.animate({
    fit: {
      eles: cy.elements(),
      padding: 30,
    },
    duration: 400,
  });
}

// ------------------------------------------------------------------------------
// 5. Chat Interaction & Message Stream
// ------------------------------------------------------------------------------
async function submitQuestion(questionText, mode = "ask") {
  if (!questionText || !questionText.trim()) return;

  const inputEl = document.getElementById("chatInput");
  const sendBtn = document.getElementById("btnSend");
  const userId = getActiveUserId();

  // If currently in memory graph mode, switch back to code graph when submitting questions
  if (currentGraphMode === "memory") {
    await loadCodeGraph();
  }

  // Disable inputs while processing
  if (inputEl) inputEl.value = "";
  if (sendBtn) {
    sendBtn.disabled = true;
    sendBtn.innerHTML = `<span>Thinking...</span><span class="status-dot"></span>`;
  }

  // 1. Append User Message Bubble
  appendMessage({
    author: "User",
    text: questionText,
    isUser: true,
  });

  // 2. Send API Request with user_id
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: questionText,
        mode: mode,
        user_id: userId,
      }),
    });

    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }

    const data = await res.json();

    // 3. Append Agent Message Bubble (with memory recall & useful bookmark button)
    appendMessage({
      author: "BlastRadius Agent",
      text: data.answer,
      paths: data.paths,
      tools: data.tools_called,
      actionReport: data.action_report,
      memoryRecalls: data.memory_recalls || [],
      findingId: data.finding_id,
      isUser: false,
    });

    // 4. Highlight path in Cytoscape
    if (data.highlighted_elements) {
      highlightPathInGraph(data.highlighted_elements);
    }

    // 5. Update Side Panel Tool Calls and Memory
    updateSidePanel(data.tools_called, data.action_report);
    await refreshMemoryDashboard();

  } catch (err) {
    console.error("Chat error:", err);
    appendMessage({
      author: "System Error",
      text: `Failed to query agent: ${err.message}. Please verify the backend server is running.`,
      isUser: false,
    });
  } finally {
    if (sendBtn) {
      sendBtn.disabled = false;
      sendBtn.innerHTML = `<span>Send</span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>`;
    }
  }
}

function appendMessage({
  author,
  text,
  isUser,
  paths = [],
  tools = [],
  actionReport = null,
  memoryRecalls = [],
  findingId = null,
}) {
  const container = document.getElementById("chatMessages");
  if (!container) return;

  const bubble = document.createElement("div");
  bubble.className = `msg-bubble ${isUser ? "user-bubble" : "agent-bubble"}`;

  const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  // Format memory recall cards
  let memoryRecallsHtml = "";
  if (memoryRecalls && memoryRecalls.length > 0) {
    memoryRecallsHtml = memoryRecalls
      .map(
        (m) => `
      <div class="memory-recall-card">
        <span class="memory-recall-icon">🧠</span>
        <div class="memory-recall-text"><b>Memory Context:</b> ${escapeHtml(m)}</div>
      </div>
    `
      )
      .join("");
  }

  // Format paths block
  let pathsHtml = "";
  if (paths && paths.length > 0) {
    pathsHtml = `
      <div class="bubble-paths">
        <div class="paths-title">🧭 Graph Paths (${paths.length}):</div>
        ${paths.map((p) => `<div class="path-item">${escapeHtml(p)}</div>`).join("")}
      </div>
    `;
  }

  // Format PR Action Preview Card inside bubble if present
  let actionCardHtml = "";
  if (actionReport) {
    actionCardHtml = `
      <div class="action-bubble-card">
        <div class="action-card-header">
          <span class="action-badge">${actionReport.risk_badge}</span>
          <span class="action-dry-pill">${actionReport.dry_run ? "DRY RUN" : "EXECUTED"}</span>
        </div>
        <p class="action-reason">${escapeHtml(actionReport.risk_reason)}</p>
      </div>
    `;
  }

  // Format Mark as Useful button
  let usefulBtnHtml = "";
  if (!isUser && findingId) {
    usefulBtnHtml = `
      <div class="bubble-actions-row">
        <button class="btn-useful" id="btnUseful_${findingId}" data-finding-id="${findingId}">
          <span class="useful-icon">⭐</span>
          <span class="useful-label">Mark as Useful</span>
        </button>
      </div>
    `;
  }

  bubble.innerHTML = `
    <div class="bubble-avatar">${isUser ? "👤" : "💥"}</div>
    <div class="bubble-content">
      <div class="bubble-header">
        <span class="bubble-author">${author}</span>
        <span class="bubble-time">${timeStr}</span>
      </div>
      ${memoryRecallsHtml}
      <div class="bubble-text">${formatMarkdownText(text)}</div>
      ${actionCardHtml}
      ${pathsHtml}
      ${usefulBtnHtml}
    </div>
  `;

  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;

  // Attach click handler to Mark as Useful button
  if (findingId) {
    const btn = document.getElementById(`btnUseful_${findingId}`);
    if (btn) {
      btn.addEventListener("click", async () => {
        const isCurrentlyUseful = btn.classList.contains("is-useful");
        const nextState = !isCurrentlyUseful;
        const userId = getActiveUserId();

        try {
          const res = await fetch("/api/memory/useful", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_id: userId,
              finding_id: findingId,
              useful: nextState,
            }),
          });

          if (res.ok) {
            btn.classList.toggle("is-useful", nextState);
            const lbl = btn.querySelector(".useful-label");
            if (lbl) {
              lbl.textContent = nextState ? "⭐ Marked Useful!" : "Mark as Useful";
            }
            await refreshMemoryDashboard();

            // If memory graph is currently open, dynamically update the node
            if (currentGraphMode === "memory" && cy) {
              const nodeEl = cy.getElementById(findingId);
              if (nodeEl.length > 0) {
                nodeEl.data("marked_useful", nextState);
                if (nextState) {
                  nodeEl.addClass("marked_useful");
                } else {
                  nodeEl.removeClass("marked_useful");
                }
              }
            }
          }
        } catch (err) {
          console.error("Failed to mark finding as useful:", err);
        }
      });
    }
  }
}

function formatMarkdownText(text) {
  if (!text) return "";
  let formatted = escapeHtml(text)
    .replace(/\n\n/g, "<br/><br/>")
    .replace(/\n/g, "<br/>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  return formatted;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ------------------------------------------------------------------------------
// 6. Side Panel: Tool Calls & PR Action Inspector
// ------------------------------------------------------------------------------
function updateSidePanel(toolsCalled = [], actionReport = null) {
  const toolsCountEl = document.getElementById("toolsCount");
  if (toolsCountEl) toolsCountEl.textContent = toolsCalled.length;

  const toolsListEl = document.getElementById("toolsList");
  if (toolsListEl) {
    if (toolsCalled.length === 0) {
      toolsListEl.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">🔍</span>
          <p>No tools were required for this query.</p>
        </div>
      `;
    } else {
      toolsListEl.innerHTML = toolsCalled
        .map(
          (t) => `
        <div class="tool-card">
          <div class="tool-card-header">
            <span class="tool-name">🛠️ ${escapeHtml(t.tool)}</span>
            <span class="tool-badge">SUCCESS</span>
          </div>
          <p class="tool-why"><b>Why:</b> ${escapeHtml(t.why)}</p>
          <pre class="tool-args">args: ${escapeHtml(JSON.stringify(t.arguments, null, 2))}</pre>
        </div>
      `
        )
        .join("");
    }
  }

  // Update PR Action Inspector
  const actionsListEl = document.getElementById("actionsList");
  if (actionsListEl && actionReport) {
    const reviewersHtml = (actionReport.best_reviewers || [])
      .map(
        (r) => `
        <div class="reviewer-item">
          <b>${escapeHtml(r.name)} (${escapeHtml(r.email)})</b> — <i>${escapeHtml(r.role)}</i>
          <small>🔍 Evidence: ${escapeHtml(r.evidence)}</small>
        </div>
      `
      )
      .join("");

    actionsListEl.innerHTML = `
      <div class="action-inspector">
        <div class="inspector-badge-row">
          <span class="action-badge-lg">${actionReport.risk_badge}</span>
          <span class="action-dry-pill">${actionReport.dry_run ? "DRY RUN" : "EXECUTED"}</span>
        </div>
        <p class="inspector-reason">${escapeHtml(actionReport.risk_reason)}</p>

        <div class="inspector-section-title">👥 2 Best Suggested Reviewers:</div>
        <div class="reviewers-list">${reviewersHtml}</div>

        <div class="inspector-section-title">📝 Ready-to-Post PR Markdown Comment:</div>
        <div class="markdown-preview-box">
          <pre>${escapeHtml(actionReport.markdown_comment)}</pre>
        </div>
        <button class="btn btn-secondary btn-copy-pr" id="btnCopyPr">
          📋 Copy PR Comment Markdown
        </button>
      </div>
    `;

    document.getElementById("btnCopyPr")?.addEventListener("click", () => {
      navigator.clipboard.writeText(actionReport.markdown_comment);
      const btn = document.getElementById("btnCopyPr");
      if (btn) btn.textContent = "✅ Copied to Clipboard!";
      setTimeout(() => {
        if (btn) btn.textContent = "📋 Copy PR Comment Markdown";
      }, 2000);
    });
  }
}

// ------------------------------------------------------------------------------
// 7. Per-User Memory Dashboard Controller
// ------------------------------------------------------------------------------
async function refreshMemoryDashboard() {
  const userId = getActiveUserId();

  // Update badge & graph name in dashboard
  const userBadge = document.getElementById("memUserBadge");
  if (userBadge) userBadge.textContent = userId;
  const graphNameEl = document.getElementById("memGraphName");
  if (graphNameEl) graphNameEl.textContent = userId;

  try {
    const res = await fetch(`/api/memory/summary?user_id=${encodeURIComponent(userId)}`);
    if (!res.ok) return;
    const data = await res.json();

    const qNum = document.getElementById("statQuestions");
    if (qNum) qNum.textContent = data.total_questions || 0;

    const aNum = document.getElementById("statAreas");
    if (aNum) aNum.textContent = data.total_areas || 0;

    const uNum = document.getElementById("statUseful");
    if (uNum) uNum.textContent = data.useful_findings || 0;

    const memCount = document.getElementById("memoryCount");
    if (memCount) memCount.textContent = (data.total_areas || 0) + (data.useful_findings || 0);

    // Populate tracked code areas
    const listEl = document.getElementById("trackedAreasList");
    if (listEl) {
      const areas = data.tracked_areas || [];
      if (areas.length === 0) {
        listEl.innerHTML = `<small class="text-muted">No code areas tracked yet. Ask a question to start building your graph memory.</small>`;
      } else {
        listEl.innerHTML = areas
          .map(
            (area) => `
          <button class="tracked-chip" data-area="${escapeHtml(area)}" title="Click to ask what breaks if this changes">
            📁 ${escapeHtml(area)}
          </button>
        `
          )
          .join("");

        // Attach click handlers to tracked area chips
        listEl.querySelectorAll(".tracked-chip").forEach((chip) => {
          chip.addEventListener("click", () => {
            const area = chip.getAttribute("data-area");
            submitQuestion(`What could break if I modify ${area}?`);
          });
        });
      }
    }
  } catch (err) {
    console.warn("Could not refresh memory dashboard:", err);
  }
}

// ------------------------------------------------------------------------------
// 8. 5 Sample Example Scenarios Loader
// ------------------------------------------------------------------------------
async function loadPresetExamples() {
  try {
    const res = await fetch("/api/examples");
    if (!res.ok) return;
    const examples = await res.json();

    const grid = document.getElementById("examplesGrid");
    if (!grid) return;

    grid.innerHTML = examples
      .map(
        (ex) => `
      <div class="example-card" data-q="${escapeHtml(ex.question)}">
        <div class="example-left">
          <span class="example-icon">${ex.icon}</span>
          <div>
            <div class="example-title">${escapeHtml(ex.title)}</div>
            <div class="example-q">${escapeHtml(ex.question)}</div>
          </div>
        </div>
        <span class="example-badge">${escapeHtml(ex.category)}</span>
      </div>
    `
      )
      .join("");

    // Attach click handlers to example cards
    document.querySelectorAll(".example-card").forEach((card) => {
      card.addEventListener("click", () => {
        const q = card.getAttribute("data-q");
        closeExamplesModal();
        submitQuestion(q);
      });
    });
  } catch (err) {
    console.error("Could not load examples:", err);
  }
}

function openExamplesModal() {
  const modal = document.getElementById("examplesModal");
  if (modal) modal.style.display = "flex";
}

function closeExamplesModal() {
  const modal = document.getElementById("examplesModal");
  if (modal) modal.style.display = "none";
}

// ------------------------------------------------------------------------------
// 9. Event Listeners Setup
// ------------------------------------------------------------------------------
function setupEventListeners() {
  // Theme toggle
  document.getElementById("btnThemeToggle")?.addEventListener("click", toggleTheme);

  // User input change
  const inputUser = document.getElementById("inputUserId");
  if (inputUser) {
    inputUser.addEventListener("change", async (e) => {
      const val = e.target.value.trim() || "alice";
      localStorage.setItem("blastradius_user_id", val);
      await refreshMemoryDashboard();
      if (currentGraphMode === "memory") {
        await loadMemoryGraph();
      }
    });
  }

  // Toggle Memory Graph button
  document.getElementById("btnToggleMemoryGraph")?.addEventListener("click", () => {
    if (currentGraphMode === "code") {
      loadMemoryGraph();
    } else {
      loadCodeGraph();
    }
  });

  // Examples modal
  document.getElementById("btnExamplesModal")?.addEventListener("click", openExamplesModal);
  document.getElementById("btnCloseModal")?.addEventListener("click", closeExamplesModal);

  // Close modal when clicking outside card
  const modal = document.getElementById("examplesModal");
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeExamplesModal();
    });
  }

  // Quick chips
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-q");
      submitQuestion(q);
    });
  });

  // Quick PR Review button
  document.getElementById("btnQuickReview")?.addEventListener("click", () => {
    document.getElementById("tabActionsBtn")?.click();
    submitQuestion("Review PR for function 'verify_token'", "review");
  });

  // Clear chat
  document.getElementById("btnClearChat")?.addEventListener("click", () => {
    const msgs = document.getElementById("chatMessages");
    if (msgs) msgs.innerHTML = "";
    resetHighlights();
  });

  // Chat form submit
  document.getElementById("chatForm")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("chatInput");
    if (input && input.value.trim()) {
      submitQuestion(input.value.trim());
    }
  });

  // Graph Layout select
  document.getElementById("selectLayout")?.addEventListener("change", (e) => {
    runGraphLayout(e.target.value);
  });

  // Graph Zoom / Fit buttons
  document.getElementById("btnZoomIn")?.addEventListener("click", () => {
    if (cy) cy.zoom(cy.zoom() * 1.25);
  });
  document.getElementById("btnZoomOut")?.addEventListener("click", () => {
    if (cy) cy.zoom(cy.zoom() * 0.8);
  });
  document.getElementById("btnFitGraph")?.addEventListener("click", () => {
    if (cy) cy.fit(undefined, 30);
  });
  document.getElementById("btnResetHighlight")?.addEventListener("click", resetHighlights);

  // Side panel tabs switching
  const tabToolsBtn = document.getElementById("tabToolsBtn");
  const tabActionsBtn = document.getElementById("tabActionsBtn");
  const tabMemoryBtn = document.getElementById("tabMemoryBtn");
  const tabToolsContent = document.getElementById("tabToolsContent");
  const tabActionsContent = document.getElementById("tabActionsContent");
  const tabMemoryContent = document.getElementById("tabMemoryContent");

  function switchTab(activeBtn, activeContent) {
    [tabToolsBtn, tabActionsBtn, tabMemoryBtn].forEach((b) => b?.classList.remove("active"));
    [tabToolsContent, tabActionsContent, tabMemoryContent].forEach((c) => c?.classList.remove("active"));
    activeBtn?.classList.add("active");
    activeContent?.classList.add("active");
  }

  tabToolsBtn?.addEventListener("click", () => switchTab(tabToolsBtn, tabToolsContent));
  tabActionsBtn?.addEventListener("click", () => switchTab(tabActionsBtn, tabActionsContent));
  tabMemoryBtn?.addEventListener("click", () => {
    switchTab(tabMemoryBtn, tabMemoryContent);
    refreshMemoryDashboard();
  });

  // Memory dashboard actions
  document.getElementById("btnMemViewGraph")?.addEventListener("click", () => {
    loadMemoryGraph();
  });

  document.getElementById("btnMemClear")?.addEventListener("click", async () => {
    const userId = getActiveUserId();
    if (confirm(`Clear all memory graph data for user '${userId}'?`)) {
      await fetch(`/api/memory?user_id=${encodeURIComponent(userId)}`, { method: "DELETE" });
      await refreshMemoryDashboard();
      if (currentGraphMode === "memory") {
        await loadMemoryGraph();
      }
    }
  });
}
