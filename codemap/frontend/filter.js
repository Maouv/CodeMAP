/* CodeMAP — shared state via EventTarget (Task_plan keputusan final).
 *
 * Public API:
 *   window.CodeMAP.store           — EventTarget dengan property .state
 *   window.CodeMAP.setState(part)  — Object.assign + dispatch 'change'
 *
 * Listener: store.addEventListener('change', e => { e.detail.prev, e.detail.next })
 *
 * ponytail: plain object, bukan Proxy. Caller wajib pakai setState() supaya
 * event ke-fire. Mutation langsung ke store.state tidak akan dispatch.
 */
(function () {
  "use strict";
  window.CodeMAP = window.CodeMAP || {};

  const store = new EventTarget();
  store.state = {
    graph: null,        // {meta, nodes, edges, warnings}
    selectedNode: null, // node object (bukan id)
    hoveredNode: null,
    filter: { risk: null, dead: false }, // risk: null|'high'
  };

  function setState(partial) {
    const prev = Object.assign({}, store.state);
    Object.assign(store.state, partial);
    store.dispatchEvent(new CustomEvent("change", {
      detail: { prev: prev, next: store.state, keys: Object.keys(partial) },
    }));
  }

  window.CodeMAP.store = store;
  window.CodeMAP.setState = setState;

  // Wire filter pills di top-bar setelah DOM ready.
  function wireFilterPills() {
    const pills = document.querySelectorAll(".filter-pill[data-filter]");
    pills.forEach((pill) => {
      pill.addEventListener("click", () => {
        const kind = pill.dataset.filter; // 'high' | 'dead'
        const cur = store.state.filter;
        const next = Object.assign({}, cur);
        if (kind === "high") {
          next.risk = cur.risk === "high" ? null : "high";
        } else if (kind === "dead") {
          next.dead = !cur.dead;
        }
        setState({ filter: next });
      });
    });
    // Reflect ke kelas .active.
    store.addEventListener("change", () => {
      const f = store.state.filter;
      pills.forEach((p) => {
        const kind = p.dataset.filter;
        const active = (kind === "high" && f.risk === "high") ||
                       (kind === "dead" && f.dead);
        p.classList.toggle("active", active);
        p.setAttribute("aria-checked", active ? "true" : "false");
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireFilterPills);
  } else {
    wireFilterPills();
  }
})();
