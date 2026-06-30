/* graps — Canvas2D graph renderer + D3 force simulation.
 *
 * Public API: window.graps.graph
 *   .panTo(node)  — center viewport ke node (pakai zoom transform)
 *   .fit()        — fit-to-viewport
 *
 * ponytail: rebuild quadtree tiap tick (O(n)). Cukup untuk <500 nodes;
 * 2000+ butuh throttle atau static index. Upgrade kalau frame drop terasa.
 * ponytail: source code raw belum di-fetch (parser belum ekstrak) — AI
 * dipanggil dengan source="".
 */
(function () {
  "use strict";
  window.graps = window.graps || {};
  const store = window.graps.store;
  const setState = window.graps.setState;
  const toast = window.graps.toast;

  let canvas, ctx, wrap;
  let width = 0, height = 0, dpr = 1;
  let nodes = [], edges = [];
  let simulation = null;
  let quadtree = null;
  let transform = { x: 0, y: 0, k: 1 };
  let zoomBehavior = null;

  // Risk → ring color (sinkron dengan CSS tokens, hardcoded karena ctx tidak
  // bisa baca CSS custom prop dengan murah; ponytail: copy dari ui-ux §1.1).
  const RING = {
    clean:  "oklch(52% 0.02 250)",
    yellow: "oklch(76% 0.15 75)",
    red:    "oklch(58% 0.22 25)",
  };
  const RING_WIDTH = { clean: 1.5, yellow: 2, red: 2.5 };
  const NODE_FILL = "oklch(18% 0.008 75)";
  const EDGE_DEFAULT = "oklch(65% 0.008 75)";
  const EDGE_ACTIVE = "oklch(94% 0.006 75)";

  function nodeRisk(n) {
    return n.risk_level || "clean";
  }

  function nodeRadius(n) {
    const deg = n._degree || 0;
    return 8 + Math.min(deg * 1.2, 10);
  }

  function resize() {
    if (!wrap) return;
    const rect = wrap.getBoundingClientRect();
    width = Math.max(rect.width, 100);
    height = Math.max(rect.height, 100);
    dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    if (simulation) {
      simulation.force("center", d3.forceCenter(width / 2, height / 2));
      simulation.alpha(0.3).restart();
    }
  }

  function buildQuadtree() {
    // ponytail: rebuild tiap tick. O(n) per tick; OK <500 nodes.
    quadtree = d3.quadtree()
      .x((d) => d.x)
      .y((d) => d.y)
      .addAll(nodes);
  }

  function nodeAt(clientX, clientY) {
    if (!quadtree) return null;
    const rect = canvas.getBoundingClientRect();
    // Screen → world coords (inverse transform).
    const sx = clientX - rect.left;
    const sy = clientY - rect.top;
    const wx = (sx - transform.x) / transform.k;
    const wy = (sy - transform.y) / transform.k;
    // Hit radius dalam world space (max radius + sedikit slack).
    const found = quadtree.find(wx, wy, 22);
    if (!found) return null;
    const r = nodeRadius(found);
    const dx = found.x - wx, dy = found.y - wy;
    return (dx * dx + dy * dy) <= (r + 4) * (r + 4) ? found : null;
  }

  function isDimmed(node) {
    const f = store.state.filter;
    const hov = store.state.hoveredNode;
    const sel = store.state.selectedNode;
    if (f.risk === "high" && nodeRisk(node) !== "red") return true;
    if (f.dead) {
      // Dead = semua fungsi is_dead_code, atau tidak ada fungsi sama sekali
      // tapi tetap connected. ponytail: simple — kalau ada minimal 1 fungsi
      // non-dead → bukan dead.
      const fns = node.functions || [];
      if (fns.length === 0) return true;
      const allDead = fns.every((fn) => fn.is_dead_code);
      if (!allDead) return true;
    }
    // Selected/hover: dim semua yang bukan node itu atau neighbor.
    const focus = sel || hov;
    if (focus && focus !== node) {
      const neigh = focus._neighbors;
      if (neigh && !neigh.has(node.id)) return true;
    }
    return false;
  }

  function draw() {
    if (!ctx) return;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    const hov = store.state.hoveredNode;
    const sel = store.state.selectedNode;
    const focus = sel || hov;

    // Edges first.
    for (const e of edges) {
      const s = e.source, t = e.target;
      if (!s || !t || typeof s.x !== "number") continue;
      let state = "default";
      if (focus && (s.id === focus.id || t.id === focus.id)) {
        state = "active";
      } else if (focus) {
        state = "dimmed";
      }
      const w = e.weight || 1;
      const lw = (0.5 + Math.min(w * 0.35, 2.5)) / transform.k;
      ctx.globalAlpha = state === "dimmed" ? 0.04 : state === "active" ? 0.7 : 0.18;
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.strokeStyle = state === "active" ? EDGE_ACTIVE : EDGE_DEFAULT;
      ctx.lineWidth = lw;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // Nodes.
    for (const n of nodes) {
      const r = nodeRadius(n);
      const risk = nodeRisk(n);
      const ring = RING[risk] || RING.clean;
      const rw = RING_WIDTH[risk] || 1.5;
      let opacity = 0.65;
      const dim = isDimmed(n);
      if (dim) opacity = 0.1;
      else if (focus && n === focus) opacity = 1.0;
      else if (focus) opacity = 0.85;
      ctx.globalAlpha = opacity;

      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = NODE_FILL;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.strokeStyle = ring;
      ctx.lineWidth = rw / transform.k;
      ctx.stroke();

      // Glow merah.
      if (risk === "red" && !dim) {
        ctx.shadowColor = RING.red;
        ctx.shadowBlur = 12 / transform.k;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.strokeStyle = ring;
        ctx.lineWidth = rw / transform.k;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // Selected outer ring.
      if (sel && n === sel) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 5, 0, Math.PI * 2);
        ctx.strokeStyle = "oklch(94% 0.006 75 / 0.4)";
        ctx.lineWidth = 1 / transform.k;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  function tick() {
    buildQuadtree();
    draw();
  }

  function precomputeNeighbors() {
    // Map node.id → Set of neighbor ids (incl. self).
    const byId = new Map(nodes.map((n) => [n.id, n]));
    nodes.forEach((n) => { n._neighbors = new Set([n.id]); n._degree = 0; });
    edges.forEach((e) => {
      const s = typeof e.source === "object" ? e.source.id : e.source;
      const t = typeof e.target === "object" ? e.target.id : e.target;
      const sn = byId.get(s), tn = byId.get(t);
      if (sn && tn) {
        sn._neighbors.add(t);
        tn._neighbors.add(s);
        sn._degree++; tn._degree++;
      }
    });
  }

  function initSim() {
    simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(edges).id((d) => d.id).distance(80).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius((d) => nodeRadius(d) + 4))
      .on("tick", tick);
  }

  function initZoom() {
    zoomBehavior = d3.zoom()
      .scaleExtent([0.2, 4])
      .on("zoom", (event) => {
        transform = { x: event.transform.x, y: event.transform.y, k: event.transform.k };
        draw();
        updateZoomIndicator();
      });
    d3.select(canvas).call(zoomBehavior);
  }

  function updateZoomIndicator() {
    const el = document.getElementById("zoom-level");
    if (el) el.textContent = Math.round(transform.k * 100) + "%";
  }

  function fitToViewport() {
    if (!nodes.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      if (n.x < minX) minX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.x > maxX) maxX = n.x;
      if (n.y > maxY) maxY = n.y;
    }
    const pad = 60;
    const w = (maxX - minX) || 1, h = (maxY - minY) || 1;
    const k = Math.min(width / (w + pad * 2), height / (h + pad * 2), 2);
    const tx = (width - (minX + maxX) * k) / 2;
    const ty = (height - (minY + maxY) * k) / 2;
    d3.select(canvas).transition().duration(300)
      .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
  }

  function panTo(node) {
    if (!node || typeof node.x !== "number") return;
    const k = Math.max(transform.k, 1);
    const tx = width / 2 - node.x * k;
    const ty = height / 2 - node.y * k;
    d3.select(canvas).transition().duration(280)
      .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
  }

  // Tooltip.
  function showTooltip(node, ev) {
    const tip = document.getElementById("tooltip");
    if (!tip || !node) return;
    const risk = node.risk_summary || "";
    const fns = (node.functions || []).length;
    tip.innerHTML =
      '<div class="tooltip-filename">' + escapeHtml(basename(node.path || node.id)) + "</div>" +
      '<div class="tooltip-path">' + escapeHtml(node.path || node.id) + "</div>" +
      '<div class="tooltip-divider"></div>' +
      '<div class="tooltip-meta">' + escapeHtml(risk || (fns + " functions")) + "</div>";
    tip.style.display = "block";
    tip.style.left = (ev.clientX + 14) + "px";
    tip.style.top = (ev.clientY + 14) + "px";
  }

  function hideTooltip() {
    const tip = document.getElementById("tooltip");
    if (tip) tip.style.display = "none";
  }

  function basename(p) {
    if (!p) return "";
    const i = p.lastIndexOf("/");
    return i >= 0 ? p.slice(i + 1) : p;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function showWarnings(warnings) {
    const banner = document.getElementById("warning-banner");
    const summary = document.getElementById("warning-summary");
    if (!banner || !summary) return;
    if (!warnings || warnings.length === 0) {
      banner.style.display = "none";
      return;
    }
    banner.style.display = "";
    summary.textContent = warnings.length + " warning" + (warnings.length === 1 ? "" : "s") +
      " (" + summarizeWarningTypes(warnings) + ")";
  }

  function summarizeWarningTypes(warnings) {
    const counts = {};
    warnings.forEach((w) => { counts[w.type] = (counts[w.type] || 0) + 1; });
    return Object.entries(counts).map(([t, c]) => t + "×" + c).join(", ");
  }

  function showEmpty(graph) {
    const empty = document.getElementById("empty-state");
    if (!empty) return;
    const nNodes = (graph.nodes || []).length;
    let totalFns = 0;
    (graph.nodes || []).forEach((n) => { totalFns += (n.functions || []).length; });
    if (nNodes === 0) {
      empty.innerHTML = emptyTpl("◇", "No Python files found",
        "graps scanned " + escapeHtml(graph.meta && graph.meta.root || ".") +
        " and found 0 .py files to analyze.",
        "graps ./src");
      empty.style.display = "";
      return false;
    }
    if (totalFns === 0) {
      empty.innerHTML = emptyTpl("◇", "Files found, no functions detected",
        "Your Python files may contain only constants, imports, or module-level code.",
        null);
      empty.style.display = "";
      return false;
    }
    if (nNodes === 1 && (graph.edges || []).length === 0) {
      empty.innerHTML = emptyTpl("◉", "Single file (no imports)",
        "This file has no import relationships with other files.", null);
      empty.style.display = "";
      // Tetap render canvas — single node still useful.
      return true;
    }
    empty.style.display = "none";
    return true;
  }

  function emptyTpl(icon, title, desc, cmd) {
    return '<div class="empty-icon">' + icon + "</div>" +
      '<div class="empty-title">' + escapeHtml(title) + "</div>" +
      '<div class="empty-desc">' + escapeHtml(desc) + "</div>" +
      (cmd ? '<div class="empty-cmd">' + escapeHtml(cmd) + "</div>" : "");
  }

  function updateTopBarStats(meta) {
    const el = document.getElementById("topbar-stats");
    if (!el || !meta) return;
    el.textContent = (meta.total_files || 0) + " files  " +
      (meta.total_functions || 0) + " fns";
  }

  function debounce(fn, ms) {
    let t = null;
    return function () {
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  async function loadGraph() {
    try {
      const r = await fetch("/api/graph");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const graph = await r.json();
      setState({ graph: graph });

      hideLoading();
      updateTopBarStats(graph.meta);
      showWarnings(graph.warnings);

      const shouldRender = showEmpty(graph);
      if (!shouldRender) return;

      nodes = (graph.nodes || []).map((n) => Object.assign({}, n));
      edges = (graph.edges || []).map((e) => Object.assign({}, e));
      precomputeNeighbors();
      initSim();
      initZoom();
      draw();
    } catch (err) {
      hideLoading();
      if (toast) toast("Failed to load graph: " + err.message, "error");
      // ponytail: log untuk debug, tidak ada retry UI di MVP.
      console.error(err);
    }
  }

  function hideLoading() {
    const s = document.getElementById("loading-screen");
    if (s) s.style.display = "none";
  }

  function setupInteractions() {
    canvas.addEventListener("mousemove", (ev) => {
      const n = nodeAt(ev.clientX, ev.clientY);
      if (n !== store.state.hoveredNode) {
        setState({ hoveredNode: n });
        if (n) showTooltip(n, ev);
        else hideTooltip();
      } else if (n) {
        showTooltip(n, ev);
      }
      canvas.style.cursor = n ? "pointer" : "grab";
    });

    canvas.addEventListener("mouseleave", () => {
      setState({ hoveredNode: null });
      hideTooltip();
    });

    canvas.addEventListener("click", (ev) => {
      const n = nodeAt(ev.clientX, ev.clientY);
      if (n) setState({ selectedNode: n });
    });

    document.addEventListener("keydown", (ev) => {
      // Skip kalau focus di input/textarea.
      const tag = (ev.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      if (ev.key === "Escape") {
        setState({ selectedNode: null });
        hideTooltip();
      } else if (ev.key === "f" || ev.key === "F") {
        fitToViewport();
      } else if (ev.key === "h" || ev.key === "H") {
        const cur = store.state.filter;
        setState({ filter: Object.assign({}, cur, { risk: cur.risk === "high" ? null : "high" }) });
      } else if (ev.key === "d" || ev.key === "D") {
        const cur = store.state.filter;
        setState({ filter: Object.assign({}, cur, { dead: !cur.dead }) });
      }
    });

    // Repaint saat state berubah (filter / selection).
    store.addEventListener("change", (e) => {
      if (e.detail.keys.includes("filter") || e.detail.keys.includes("selectedNode")) {
        draw();
      }
    });

    // Pan-to event dari panel.js (caller/callee click).
    window.addEventListener("graps:pan-to", (ev) => {
      const node = nodes.find((n) => n.id === ev.detail.id || n.path === ev.detail.id);
      if (node) {
        panTo(node);
        setState({ selectedNode: node });
      }
    });

    // Warning banner toggle.
    const toggle = document.getElementById("warning-toggle");
    const banner = document.getElementById("warning-banner");
    if (toggle && banner) {
      toggle.addEventListener("click", () => {
        const expanded = banner.classList.toggle("expanded");
        banner.classList.toggle("collapsed", !expanded);
        toggle.textContent = expanded ? "Hide" : "Show all";
      });
    }
  }

  function boot() {
    wrap = document.getElementById("canvas-wrap");
    canvas = document.getElementById("graph-canvas");
    if (!canvas || !wrap) return;
    ctx = canvas.getContext("2d");
    resize();
    window.addEventListener("resize", debounce(resize, 100));
    setupInteractions();
    loadGraph();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.graps.graph = {
    panTo: panTo,
    fit: fitToViewport,
    getNodes: () => nodes,
  };
})();
