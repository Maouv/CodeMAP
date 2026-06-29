/* CodeMAP — Cmd+K node search overlay.
 *
 * Substring match (case-insensitive) pada node.id / node.path.
 * Max 10 hasil, arrow keys + Enter + Esc.
 *
 * ponytail: tanpa fuzzy match. Substring sudah cukup untuk path list.
 */
(function () {
  "use strict";
  window.CodeMAP = window.CodeMAP || {};
  const store = window.CodeMAP.store;
  const setState = window.CodeMAP.setState;

  let overlay, input, list;
  let results = [];
  let cursor = 0;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function open() {
    if (!overlay) return;
    overlay.style.display = "flex";
    input.value = "";
    results = [];
    cursor = 0;
    render();
    input.focus();
  }

  function close() {
    if (overlay) overlay.style.display = "none";
  }

  function search(q) {
    const g = store.state.graph;
    if (!g || !g.nodes) return [];
    if (!q) return [];
    const needle = q.toLowerCase();
    const hits = [];
    for (const n of g.nodes) {
      const id = (n.id || "").toLowerCase();
      const p = (n.path || "").toLowerCase();
      if (id.indexOf(needle) >= 0 || p.indexOf(needle) >= 0) {
        hits.push(n);
        if (hits.length >= 10) break;
      }
    }
    return hits;
  }

  function render() {
    if (!list) return;
    if (results.length === 0) {
      list.innerHTML = input.value
        ? '<div class="search-empty">No matches</div>'
        : '<div class="search-empty">Type to search files…</div>';
      return;
    }
    list.innerHTML = results.map((n, i) =>
      '<div class="search-item' + (i === cursor ? " active" : "") + '" data-i="' + i + '">' +
        '<div class="search-item-name">' + esc(n.path || n.id) + "</div>" +
        ((n.functions || []).length
          ? '<div class="search-item-meta">' + (n.functions || []).length + " fns</div>"
          : "") +
      "</div>"
    ).join("");
    list.querySelectorAll(".search-item").forEach((el) => {
      el.addEventListener("click", () => choose(parseInt(el.dataset.i, 10)));
    });
  }

  function choose(i) {
    const n = results[i];
    if (!n) return;
    setState({ selectedNode: n });
    window.dispatchEvent(new CustomEvent("codemap:pan-to", { detail: { id: n.id } }));
    close();
  }

  function boot() {
    overlay = document.getElementById("search-overlay");
    input = document.getElementById("search-input");
    list = document.getElementById("search-list");
    if (!overlay || !input || !list) return;

    document.addEventListener("keydown", (ev) => {
      const isMod = ev.metaKey || ev.ctrlKey;
      if (isMod && (ev.key === "k" || ev.key === "K")) {
        ev.preventDefault();
        if (overlay.style.display === "flex") close();
        else open();
      } else if (overlay.style.display === "flex") {
        if (ev.key === "Escape") {
          ev.preventDefault();
          close();
        } else if (ev.key === "ArrowDown") {
          ev.preventDefault();
          if (results.length) { cursor = (cursor + 1) % results.length; render(); }
        } else if (ev.key === "ArrowUp") {
          ev.preventDefault();
          if (results.length) { cursor = (cursor - 1 + results.length) % results.length; render(); }
        } else if (ev.key === "Enter") {
          ev.preventDefault();
          choose(cursor);
        }
      }
    });

    input.addEventListener("input", () => {
      results = search(input.value);
      cursor = 0;
      render();
    });

    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) close();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
