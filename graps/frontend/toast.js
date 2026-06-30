/* graps — toast notification (paling simple, no dependency).
 *
 * Public API: window.graps.toast(msg, type='info')
 *   type: 'info' | 'success' | 'error'
 *
 * ponytail: max 3 toast hidup, auto dismiss 3 detik via setTimeout +
 * CSS transition. Tidak ada queue persist, tidak ada helper variant.
 */
(function () {
  "use strict";
  window.graps = window.graps || {};

  const MAX_ALIVE = 3;
  const TTL_MS = 3000;
  const FADE_MS = 200;

  function container() {
    let el = document.getElementById("toast-container");
    if (!el) {
      // ponytail: kalau index.html lupa pasang container, bikin sendiri.
      el = document.createElement("div");
      el.id = "toast-container";
      document.body.appendChild(el);
    }
    return el;
  }

  function dismiss(node) {
    if (!node || !node.parentNode) return;
    node.classList.add("toast--leaving");
    setTimeout(() => node.parentNode && node.parentNode.removeChild(node), FADE_MS);
  }

  /**
   * Tampilkan toast.
   * @param {string} msg
   * @param {'info'|'success'|'error'} [type='info']
   */
  function toast(msg, type) {
    type = type || "info";
    const root = container();

    // Hapus yang paling tua kalau sudah penuh.
    while (root.children.length >= MAX_ALIVE) {
      dismiss(root.firstChild);
    }

    const el = document.createElement("div");
    el.className = "toast toast--" + type;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.textContent = msg;
    root.appendChild(el);

    setTimeout(() => dismiss(el), TTL_MS);
  }

  window.graps.toast = toast;
})();
