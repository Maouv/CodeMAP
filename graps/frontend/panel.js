/* graps — side panel: render file detail, function accordion, AI insight.
 *
 * Listen store.change → kalau selectedNode berubah, render panel content.
 *
 * ponytail: render via template literal + innerHTML. Tidak ada virtual DOM,
 * tidak ada template engine. Re-render seluruh panel saat selection ganti.
 */
(function () {
  "use strict";
  window.graps = window.graps || {};
  const store = window.graps.store;
  const setState = window.graps.setState;
  const toast = window.graps.toast;

  let panelEl, scrollEl;
  const expandedFns = new Set(); // names yang sedang expand
  const aiResults = new Map();   // key "file::function" → response payload
  let _aiConsentGiven = false;   // PHASE3 Task 2: in-memory, reset tiap server restart (no localStorage)

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function basename(p) {
    if (!p) return "";
    const i = p.lastIndexOf("/");
    return i >= 0 ? p.slice(i + 1) : p;
  }

  function fmtParam(p) {
    if (!p) return "";
    if (p.annotation) return esc(p.name) + ": " + esc(p.annotation);
    return esc(p.name);
  }

  function critClass(level) {
    return "crit-dot--" + (level || "clean");
  }

  function fnRow(fn, idx) {
    const isOpen = expandedFns.has(fn.name);
    const ret = fn.returns ? esc(fn.returns) : "—";
    const dead = fn.is_dead_code
      ? '<span class="fn-dead">dead code</span>'
      : "";
    return (
      '<div class="fn-row' + (isOpen ? " active" : "") + '" data-fn="' + esc(fn.name) + '">' +
        '<span class="crit-dot ' + critClass(fn.criticality) + '"></span>' +
        '<span class="fn-name">' + esc(fn.name) + "</span>" +
        dead +
        '<span class="fn-return">' + ret + "</span>" +
        '<span class="fn-chevron">▸</span>' +
      "</div>" +
      (isOpen ? fnDetail(fn) : "")
    );
  }

  function fnDetail(fn) {
    const params = (fn.params || []).map(fmtParam).filter(Boolean);
    const callers = fn.callers || [];
    const callees = fn.callees || [];
    const risks = fn.risks || [];
    const lineRange = (fn.line_start != null)
      ? (fn.line_start + (fn.line_end != null ? " – " + fn.line_end : ""))
      : "—";
    const aiKey = currentNode().path + "::" + fn.name;
    const ai = aiResults.get(aiKey);

    return (
      '<div class="fn-detail" data-fn-detail="' + esc(fn.name) + '">' +
        (params.length
          ? '<div class="detail-label">Parameters</div>' +
            '<div class="detail-value">' + params.join(", ") + "</div>"
          : "") +
        (fn.returns
          ? '<div class="detail-label">Returns</div>' +
            '<div class="detail-value">' + esc(fn.returns) + "</div>"
          : "") +
        '<div class="detail-label">Lines</div>' +
        '<div class="detail-value">' + esc(lineRange) + "</div>" +

        (callers.length
          ? '<div class="detail-label">Called by ' + callers.length + "</div>" +
            callers.map((c) =>
              '<div class="caller-item" data-pan-to="' + esc(c) + '">' + esc(c) + "</div>"
            ).join("")
          : "") +

        (callees.length
          ? '<div class="detail-label">Calls ' + callees.length + "</div>" +
            callees.map((c) => {
              const target = c.resolved_file || "";
              const name = c.name || "";
              return '<div class="caller-item"' +
                (target ? ' data-pan-to="' + esc(target) + '"' : "") +
                ">" + esc(name) +
                (target ? ' <span style="opacity:0.5">' + esc(target) + "</span>" : "") +
                "</div>";
            }).join("")
          : "") +

        (risks.length
          ? '<div class="detail-label">Risks</div>' +
            risks.map(riskCard).join("")
          : "") +

        aiSection(fn, ai) +
      "</div>"
    );
  }

  function riskCard(r) {
    const sev = r.severity || "low";
    const files = (r.affected_files || []).map((f) =>
      '<div class="risk-file">' + esc(f) + "</div>"
    ).join("");
    return (
      '<div class="risk-card risk-card--' + esc(sev) + '">' +
        '<div class="risk-title">' + esc(sev) + " " + esc(r.type || "") + "</div>" +
        '<div class="risk-desc">' + esc(r.detail || "") + "</div>" +
        (files ? '<div class="risk-files">' + files + "</div>" : "") +
      "</div>"
    );
  }

  function aiSection(fn, ai) {
    if (!ai) {
      return '<button class="btn-ai" data-ai-fn="' + esc(fn.name) + '">' +
        '<span class="icon">✦</span> Generate AI Insight' +
        "</button>";
    }
    if (ai.loading) {
      return '<button class="btn-ai" disabled>' +
        '<span class="icon">✦</span> Analyzing…' +
        "</button>";
    }
    if (ai.enabled === false) {
      const msg = ai.reason === "sdk_not_installed"
        ? "AI SDK not installed"
        : "No API key configured";
      return '<button class="btn-ai" disabled title="' + esc(msg) + '">' +
        '<span class="icon">✦</span> ' + esc(msg) +
        "</button>";
    }
    if (ai.error_type) {
      return '<button class="btn-ai" data-ai-fn="' + esc(fn.name) + '">' +
        '<span class="icon">✦</span> Retry AI Insight' +
        "</button>";
    }
    const s = ai.summary || {};
    return (
      '<div class="ai-card">' +
        '<div class="ai-card-header">' +
          '<div class="ai-card-title">AI INSIGHT</div>' +
          '<div class="ai-card-provider">' + esc(ai.provider || "") +
          (ai.cached ? " · cached" : "") + "</div>" +
        "</div>" +
        aiField("Role", s.role) +
        aiField("Importance", s.importance) +
        aiField("Hidden assumption", s.hidden_assumption) +
      "</div>"
    );
  }

  function aiField(label, value) {
    if (!value) return "";
    return '<div class="ai-field">' +
      '<div class="ai-field-label">' + esc(label) + "</div>" +
      '<div class="ai-field-value">' + esc(value) + "</div>" +
      "</div>";
  }

  function currentNode() {
    return store.state.selectedNode;
  }

  function render() {
    const node = currentNode();
    if (!panelEl) return;
    if (!node) {
      panelEl.classList.remove("open");
      panelEl.setAttribute("aria-hidden", "true");
      return;
    }
    panelEl.classList.add("open");
    panelEl.setAttribute("aria-hidden", "false");

    const fns = node.functions || [];
    const consts = node.constants || [];
    const imps = node.imports || [];

    // Hitung badges.
    let high = 0, medium = 0;
    fns.forEach((fn) => {
      (fn.risks || []).forEach((r) => {
        if (r.severity === "high") high++;
        else if (r.severity === "medium") medium++;
      });
    });

    const html =
      '<div class="panel-scroll">' +
        '<div class="panel-header">' +
          '<button class="panel-close" id="panel-close" aria-label="Close panel">×</button>' +
          '<div class="panel-filename">' + esc(basename(node.path || node.id)) + "</div>" +
          '<div class="panel-filepath">' + esc(node.path || node.id) + "</div>" +
          '<div class="badge-row">' +
            (high ? '<span class="badge badge--high">' + high + " high</span>" : "") +
            (medium ? '<span class="badge badge--medium">' + medium + " medium</span>" : "") +
            '<span class="badge badge--count">' + fns.length + " functions</span>" +
          "</div>" +
        "</div>" +

        '<div class="section-header">Functions <span class="section-count">' + fns.length + "</span></div>" +
        (fns.length ? fns.map(fnRow).join("")
          : '<div class="fn-row" style="cursor:default;color:var(--ink-muted)">No functions</div>') +

        (consts.length ? (
          '<div class="section-header">Constants <span class="section-count">' + consts.length + "</span></div>" +
          consts.map((c) =>
            '<div class="fn-row" style="cursor:default">' +
              '<span class="fn-name">' + esc(c.name) + "</span>" +
              '<span class="fn-return">' + esc(c.value) + "</span>" +
            "</div>"
          ).join("")
        ) : "") +

        (imps.length ? (
          '<div class="section-header">Imports <span class="section-count">' + imps.length + "</span></div>" +
          imps.map((i) => {
            const names = (i.names || []).join(", ");
            return '<div class="fn-row" data-pan-to="' + esc(i.resolved_path || "") + '"' +
              (i.resolved_path ? "" : ' style="cursor:default"') + ">" +
              '<span class="fn-name">' + esc(i.from || "") + "</span>" +
              '<span class="fn-return">' + esc(names) + "</span>" +
              "</div>";
          }).join("")
        ) : "") +
      "</div>";

    panelEl.innerHTML = html;
    wireEvents();
  }

  function wireEvents() {
    const close = document.getElementById("panel-close");
    if (close) close.addEventListener("click", () => setState({ selectedNode: null }));

    panelEl.querySelectorAll(".fn-row[data-fn]").forEach((row) => {
      row.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-pan-to]")) return;
        const name = row.dataset.fn;
        if (expandedFns.has(name)) expandedFns.delete(name);
        else expandedFns.add(name);
        render();
      });
    });

    panelEl.querySelectorAll("[data-pan-to]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const target = el.dataset.panTo;
        if (target) {
          window.dispatchEvent(new CustomEvent("graps:pan-to", { detail: { id: target } }));
        }
      });
    });

    panelEl.querySelectorAll("[data-ai-fn]").forEach((btn) => {
      btn.addEventListener("click", () => callAI(btn.dataset.aiFn));
    });
  }

    // PHASE3 Task 2 / BLUEPRINT §10: consent gate sebelum AI pertama kali dipanggil.
  // ponytail: modal dibangun dinamis (pola toast.js), di-remove saat resolve. In-memory
  // flag 1 per sesi browser; reset otomatis tiap server restart (refresh page saja tidak
  // reset, tapi itu OK — sesi = lifetime halaman).
  function showConsentModal() {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.className = "consent-overlay";
      overlay.setAttribute("role", "dialog");
      overlay.setAttribute("aria-modal", "true");
      overlay.setAttribute("aria-label", "Kirim ke AI consent");
      overlay.innerHTML =
        '<div class="consent-box">' +
          '<div class="consent-title">Kirim ke AI?</div>' +
          '<div class="consent-body">File content akan dikirim ke ' +
          "Anthropic/OpenAI untuk dianalisis. " +
          "Pastikan tidak ada credentials hardcoded.</div>" +
          '<div class="consent-actions">' +
            '<button class="consent-btn consent-btn--cancel" type="button">Batal</button>' +
            '<button class="consent-btn consent-btn--ok" type="button">Lanjutkan</button>' +
          "</div>" +
        "</div>";
      document.body.appendChild(overlay);

      function done(ok) {
        overlay.remove();
        document.removeEventListener("keydown", onKey);
        resolve(ok);
      }
      function onKey(e) {
        if (e.key === "Escape") done(false);
        else if (e.key === "Enter") done(true);
      }
      overlay.querySelector(".consent-btn--ok").addEventListener("click", () => done(true));
      overlay.querySelector(".consent-btn--cancel").addEventListener("click", () => done(false));
      overlay.addEventListener("click", (e) => { if (e.target === overlay) done(false); });
      document.addEventListener("keydown", onKey);
      overlay.querySelector(".consent-btn--ok").focus();
    });
  }

  async function callAI(fnName) {
    const node = currentNode();
    if (!node) return;
    const fn = (node.functions || []).find((f) => f.name === fnName);
    if (!fn) return;
    if (!_aiConsentGiven) {
      const ok = await showConsentModal();
      if (!ok) return;            // Batal → tombol balik idle (loading state belum di-set)
      _aiConsentGiven = true;
    }
    const key = node.path + "::" + fnName;
    aiResults.set(key, { loading: true });
    render();

    const body = {
      file: node.path || node.id,
      function: fnName,
      line: fn.line_start || 0,
      modified_at: node.file_modified_at || "",
      // ponytail: parser belum ekstrak source raw — kirim "". Server menolak
      // dengan reason "no_source" sampai source extraction di-wire (Finding 7).
      source: "",
    };

    try {
      const r = await fetch("/api/ai/summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      aiResults.set(key, data);
      if (data.enabled === false) {
        // tampil disabled state, no toast — itu config issue, bukan error sesi.
      } else if (data.error_type) {
        const m = errorMsg(data);
        if (toast) toast(m, "error");
      } else if (data.cached) {
        if (toast) toast("Loaded from cache", "info");
      }
      render();
    } catch (err) {
      aiResults.set(key, { enabled: true, error_type: "network" });
      if (toast) toast("AI request failed: " + err.message, "error");
      render();
    }
  }

  function errorMsg(data) {
    switch (data.error_type) {
      case "auth_failed": return "API auth failed";
      case "rate_limited":
        return data.retry_after
          ? "Rate limited, retry in " + data.retry_after + "s"
          : "Rate limited";
      case "timeout": return "AI timeout";
      default: return "AI error";
    }
  }

  function boot() {
    panelEl = document.getElementById("side-panel");
    if (!panelEl) return;
    store.addEventListener("change", (e) => {
      if (e.detail.keys.includes("selectedNode")) {
        expandedFns.clear();
        render();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
