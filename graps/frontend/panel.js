/* graps — side panel: render file detail, function accordion, + AI chat (Phase 5).
 *
 * Listen store.change → kalau selectedNode berubah, render panel content ke
 * #panel-scroll. Chat section (#chat-section) adalah sibling yang di-wire
 * sekali saat boot — tidak di-overwrite oleh render.
 *
 * Phase 5: hapus callAI/showConsentModal/aiResults/_aiConsentGiven/aiSection.
 * Ganti dengan chat interface (Option C): @tag parsing, tag-time non-blocking
 * warning (cek [REDACTED] constants dari C-01), POST /api/ai/chat.
 *
 * ponytail: render via template literal + innerHTML. Chat state in-memory
 * (fresh session, no localStorage). Re-use errorMsg() dari lama buat error map.
 */
(function () {
  "use strict";
  window.graps = window.graps || {};
  const store = window.graps.store;
  const setState = window.graps.setState;
  const toast = window.graps.toast;

  let panelEl, scrollEl;
  const expandedFns = new Set(); // names yang sedang expand

  // Chat state — in-memory, reset tiap page load (no localStorage, no persistence).
  const chatHistory = [];    // [{role: 'user'|'assistant', content}]
  const chatWarnings = [];   // non-blocking warnings current message [{file, reason}]
  let chatSending = false;   // guard double-send
  let chatDisabled = false;  // ponytail: persisten saat no_api_key/sdk_not_installed.
  //   Ceiling: no boot-time probe — disabled state baru muncul setelah send
  //   pertama. Upgrade path: GET /api/ai/status kalau perlu greyed sejak boot.
  let chatInput, chatSend, chatMsgEl, chatWarnEl;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // ponytail: basename() di-share dari graph.js via window.graps (Finding 14)
  const basename = window.graps.basename;

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

        // ponytail: per-function AI insight → affordance yang insert @tag ke chat.
        // Tidak generate langsung — user ketik pertanyaan mereka sendiri.
        '<button class="btn-ai" data-ai-fn="' + esc(fn.name) + '">' +
          '<span class="icon">✦</span> Ask AI' +
        "</button>" +
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

  function currentNode() {
    return store.state.selectedNode;
  }

  // ponytail: lookup node by path/id dari graph yang sudah di-load. Dipakai
  // checkTagWarnings + parseTags (resolve bare @function ke file path).
  function findNodeByPath(rel) {
    const g = store.state.graph;
    if (!g || !g.nodes) return null;
    return (g.nodes || []).find((n) => n.path === rel || n.id === rel) || null;
  }

  function render() {
    const node = currentNode();
    if (!panelEl || !scrollEl) return;
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
      ) : "");

    scrollEl.innerHTML = html;   // ponytail: render ke #panel-scroll, chat section utuh
    wireEvents();
  }

  function wireEvents() {
    const close = document.getElementById("panel-close");
    if (close) close.addEventListener("click", () => setState({ selectedNode: null }));

    scrollEl.querySelectorAll(".fn-row[data-fn]").forEach((row) => {
      row.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-pan-to]")) return;
        if (ev.target.closest(".btn-ai")) return;     // jangan toggle row saat klik Ask AI
        const name = row.dataset.fn;
        if (expandedFns.has(name)) expandedFns.delete(name);
        else expandedFns.add(name);
        render();
      });
    });

    scrollEl.querySelectorAll("[data-pan-to]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const target = el.dataset.panTo;
        if (target) {
          window.dispatchEvent(new CustomEvent("graps:pan-to", { detail: { id: target } }));
        }
      });
    });

    // ✦ Ask AI — insert @file::function ke chat input + focus (tidak generate).
    scrollEl.querySelectorAll("[data-ai-fn]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        askAI(btn.dataset.aiFn);
      });
    });
  }

  // ============================================================
  // === CHAT (Phase 5 — Option C) =============================
  // ============================================================

  /**
   * Insert @file::function ke chat input + focus. User ketik pertanyaan sendiri.
   */
  function askAI(fnName) {
    const node = currentNode();
    if (!node || !chatInput) return;
    const tag = "@" + (node.path || node.id) + "::" + fnName;
    chatInput.value = chatInput.value
      ? (chatInput.value.replace(/\s+$/, "") + " " + tag)
      : tag;
    chatInput.focus();
  }

  /**
   * Parse @tag dari input. Format: @file::function | @file | @function.
   * ponytail: bare @function di-resolve ke path node pertama yang punya fungsi
   *   itu — ceiling: ambigu kalau function name duplikat cross-file, ambil yang
   *   pertama. Upgrade path: autocomplete dropdown kalau perlu.
   * @returns {{tags: string[], cleanText: string}} tags = ["file.py", "file.py::fn", ...]
   */
  function parseTags(text) {
    const tags = [];
    // @path::function  atau  @path  atau  @bareword
    const re = /@(\S+)/g;
    let m;
    let stripped = text;
    while ((m = re.exec(text)) !== null) {
      const raw = m[1];
      stripped = stripped.replace("@" + raw, "");
      if (raw.indexOf("::") !== -1) {
        tags.push(raw);
      } else {
        // path or bare function name. Kalau ada node dgn path == raw → file tag.
        // Kalau bukan path yang dikenal, coba resolve sebagai function name.
        const node = findNodeByPath(raw);
        if (node) {
          tags.push(node.path || node.id);
        } else {
          const fnOwner = findNodeByFunction(raw);
          if (fnOwner) tags.push((fnOwner.path || fnOwner.id) + "::" + raw);
          else tags.push(raw); // biarkan server yang kasih warning file_not_in_graph
        }
      }
    }
    return { tags: tags, cleanText: stripped.replace(/\s+/g, " ").trim() };
  }

  // ponytail: cari node pertama yang punya fungsi dgn name == fnName.
  function findNodeByFunction(fnName) {
    const g = store.state.graph;
    if (!g || !g.nodes) return null;
    return (g.nodes || []).find((n) =>
      (n.functions || []).some((f) => f.name === fnName)
    ) || null;
  }

  /**
   * Tag-time non-blocking warning: cek node.constants ada yang [REDACTED] (C-01).
   * ponytail: ceiling = cuma catch constants, bukan secret di function body.
   *   Reuse data graph yang sudah di-load — zero fetch. Tidak halt send.
   */
  function checkTagWarnings(tags) {
    const added = [];
    tags.forEach((tag) => {
      const rel = tag.indexOf("::") !== -1 ? tag.split("::", 1)[0] : tag;
      const node = findNodeByPath(rel);
      if (!node) return;
      const consts = node.constants || [];
      const hasRedacted = consts.some((c) => String(c.value) === "[REDACTED]");
      if (!hasRedacted) return;
      // dedup per file
      if (chatWarnings.some((w) => w.file === rel && w.reason === "redacted_constants")) return;
      const w = { file: rel, reason: "redacted_constants" };
      chatWarnings.push(w);
      added.push(w);
    });
    if (added.length) renderChat();
  }

  function warningText(w) {
    if (w.reason === "redacted_constants")
      return esc(w.file) + " mungkin contain sensitive values (constant [REDACTED]) yang akan di-share ke AI provider.";
    if (w.reason === "credential_file_excluded")
      return esc(w.file || "") + " adalah credential file — source di-exclude dari AI context.";
    if (w.reason === "file_not_in_graph")
      return esc(w.file || "") + " tidak ada di graph — context terbatas.";
    if (w.reason === "function_not_found")
      return "Fungsi tidak ditemukan di " + esc(w.file || "") + ".";
    if (w.reason === "source_unreadable")
      return esc(w.file || "") + " source tidak bisa dibaca.";
    return esc(w.reason || "warning");
  }

  function renderChat() {
    if (!chatMsgEl || !chatWarnEl) return;
    // messages
    if (!chatHistory.length) {
      chatMsgEl.innerHTML =
        '<div class="chat-bubble chat-bubble--system">No messages yet. Ask AI about @file or @function.</div>';
    } else {
      chatMsgEl.innerHTML = chatHistory.map((m) => {
        const cls = m.role === "user" ? "chat-bubble--user"
          : m.role === "assistant" ? "chat-bubble--assistant"
          : m.role === "error" ? "chat-bubble--error"
          : "chat-bubble--system";
        return '<div class="chat-bubble ' + cls + '">' + esc(m.content) + "</div>";
      }).join("");
      // auto-scroll ke bawah
      chatMsgEl.scrollTop = chatMsgEl.scrollHeight;
    }
    // warnings — non-blocking, dismissible
    chatWarnEl.innerHTML = chatWarnings.map((w, i) =>
      '<div class="chat-warning" data-warn-idx="' + i + '">' +
        '<span class="chat-warning-icon">⚠</span>' +
        '<span class="chat-warning-msg">' + warningText(w) + "</span>" +
        '<button class="chat-warning-dismiss" type="button" aria-label="Dismiss" data-warn-dismiss="' + i + '">×</button>' +
      "</div>"
    ).join("");
    chatWarnEl.querySelectorAll("[data-warn-dismiss]").forEach((btn) => {
      btn.addEventListener("click", () => {
        chatWarnings.splice(Number(btn.dataset.warnDismiss), 1);
        renderChat();
      });
    });
  }

  // Reuse dari lama: map error_type ke toast message.
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

  async function handleSend() {
    if (!chatInput || chatSending || chatDisabled) return;
    const raw = chatInput.value;
    const parsed = parseTags(raw);
    if (!parsed.cleanText.trim()) return;       // butuh pertanyaan, tag saja tidak cukup

    checkTagWarnings(parsed.tags);              // non-blocking, tidak halt send

    chatSending = true;
    chatInput.value = "";
    chatSend.disabled = true;
    chatHistory.push({ role: "user", content: raw.trim() });
    renderChat();

    const body = {
      message: parsed.cleanText,
      tagged: parsed.tags,
      history: chatHistory.slice(0, -1),        // exclude user msg baru (di-append server)
    };
    try {
      const r = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (data.enabled === false) {
        // no_api_key / sdk_not_installed / empty_message → system bubble, no toast
        const reason = data.reason === "sdk_not_installed" ? "AI SDK not installed"
          : data.reason === "empty_message" ? "Message is empty"
          : "No API key configured";
        chatHistory.push({ role: "system", content: reason });
        if (data.warnings && data.warnings.length) chatWarnings.push.apply(chatWarnings, data.warnings);
        // ponytail: disable persisten + hint tooltip (spec §4.5).
        //   empty_message transien (caught client-side) → tidak disable.
        if (data.reason === "no_api_key" || data.reason === "sdk_not_installed") {
          chatDisabled = true;
          chatInput.disabled = true;
          chatSend.disabled = true;
          chatInput.title = reason;
        }
      } else if (data.error_type) {
        if (toast) toast(errorMsg(data), "error");
        chatHistory.push({ role: "error", content: errorMsg(data) });
        if (data.warnings && data.warnings.length) chatWarnings.push.apply(chatWarnings, data.warnings);
      } else {
        chatHistory.push({ role: "assistant", content: data.reply || "" });
        if (data.warnings && data.warnings.length) chatWarnings.push.apply(chatWarnings, data.warnings);
      }
      renderChat();
    } catch (err) {
      if (toast) toast("AI request failed: " + err.message, "error");
      chatHistory.push({ role: "error", content: "Network error: " + err.message });
      renderChat();
    } finally {
      chatSending = false;
      chatSend.disabled = chatDisabled;
      chatInput.disabled = chatDisabled;
    }
  }

  function wireChat() {
    chatInput = document.getElementById("chat-input");
    chatSend = document.getElementById("chat-send");
    chatMsgEl = document.getElementById("chat-messages");
    chatWarnEl = document.getElementById("chat-warnings");
    if (!chatInput || !chatSend) return;
    chatSend.addEventListener("click", handleSend);
    chatInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        handleSend();
      }
    });
    // ponytail: collapse toggle — toggle class, CSS hide children. aria sinkron.
    const collapse = document.getElementById("chat-collapse");
    const section = document.getElementById("chat-section");
    if (collapse && section) {
      collapse.addEventListener("click", () => {
        const collapsed = section.classList.toggle("collapsed");
        collapse.setAttribute("aria-expanded", collapsed ? "false" : "true");
      });
    }
    renderChat();
  }

  function boot() {
    panelEl = document.getElementById("side-panel");
    scrollEl = document.getElementById("panel-scroll");
    if (!panelEl) return;
    store.addEventListener("change", (e) => {
      if (e.detail.keys.includes("selectedNode")) {
        expandedFns.clear();
        render();
      }
    });
    wireChat();   // wire chat sekali — section sibling, tidak di-overwrite render
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
