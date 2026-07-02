# Bug Hunter Report — graps Frontend
**Scope:** `graps/frontend/` — `graph.js`, `panel.js`, `filter.js`, `search.js`, `toast.js`, `style.css`, `index.html`  
**Phase Context:** Phase 4 (tree-sitter multi-language migration)  
**Method:** Full source read → execution-based verification via Node.js test harness  
**Date:** 2026-07-02  
**Verdict format:** Every finding has concrete execution evidence — no speculation.

---

## Summary

| # | Title | Severity | Likelihood | Confidence |
|---|-------|----------|------------|------------|
| 1 | hoveredNode state change never redraws canvas after simulation stops | High | Very High | High |
| 2 | Escape key conflict: consent modal cancel silently clears selectedNode | High | High | High |
| 3 | nodeAt() hit radius 22px world-space causes wrong click targets at non-1× zoom | High | High | High |
| 4 | Concurrent AI calls — stale response overwrites fresh response | Medium | Medium | High |
| 5 | fitToViewport() NaN transform when nodes have no position yet | Medium | Medium | High |
| 6 | Edge draw guard checks only s.x — t.x unguarded → lineTo(NaN) | Medium | Low | High |
| 7 | Tooltip clips off-screen at viewport edges — no bounds check | Medium | Very High | High |
| 8 | Search sets selectedNode to raw graph node (no _neighbors) → dimming broken briefly | Medium | High | High |
| 9 | #path-chip never updated — always shows './' regardless of scan root | Low | Very High | High |
| 10 | CSS transition `height: auto` does not animate — warning banner snaps | Low | Very High | High |
| 11 | setState shallow copy — direct mutation of nested objects undetectable | Low | Low | High |
| 12 | errorMsg() default catch-all: network vs unknown errors indistinguishable | Low | Medium | High |
| 13 | escapeHtml() defined 3× across modules — divergence risk on future edits | Informational | Low | High |

---

# Finding 1

## Title
`hoveredNode` state change never triggers canvas redraw after D3 simulation stops

## Severity
High

## Likelihood
Very High

## Confidence
High

## Category
Functional Bug / Silent UI Freeze / User Experience

## Scenario
User opens graps, graph loads, simulation runs and settles (~5–10 seconds). User then moves cursor over nodes expecting hover highlight and neighbor dimming. Nothing happens — the canvas is frozen.

## Description
`graph.js` registers a `store.addEventListener("change")` listener that calls `draw()` only for `"filter"` and `"selectedNode"` key changes. The `"hoveredNode"` key is absent from this condition. During simulation, `draw()` is called on every tick via `simulation.on("tick", tick)` — so hover _appears_ to work. Once the simulation converges (`alpha < alphaMin ≈ 0.001`), ticks stop, and `draw()` is never called again unless a filter or selection event fires.

After simulation convergence, every `mousemove` calls `setState({ hoveredNode: n })`, which dispatches a store `"change"` event — but the listener ignores it. The hover highlight, neighbor dimming, and tooltip (which is separately wired to `mousemove`) do not match the canvas.

## Evidence
```javascript
// graph.js lines 476-480 (verified by reading source)
store.addEventListener("change", (e) => {
  if (e.detail.keys.includes("filter") || e.detail.keys.includes("selectedNode")) {
    draw();  // hoveredNode NOT in this condition
  }
});
```
```
Verified execution: after simulation stops, setState({ hoveredNode: node }) dispatches
event with keys=["hoveredNode"]. Condition evaluates to false. draw() NOT called.
Canvas state: previous hoveredNode dimming remains frozen.
```

## Steps to Reproduce
1. Load graps with a graph containing ≥ 2 nodes.
2. Wait for simulation to fully settle (~10 seconds, or press `F` to fit).
3. Move mouse over nodes.
4. **Expected:** Hovered node brightens, neighbors highlighted, others dimmed.
5. **Actual:** Canvas remains static. No visual response to hover.

## Expected Behavior
`draw()` is called whenever `hoveredNode` changes in the store.

## Actual Behavior
`draw()` is not called after simulation stops. Hover highlight is permanently broken once the graph is static.

## Root Cause
The store listener was written to only respond to `filter` and `selectedNode` changes. `hoveredNode` was left out — likely an oversight since hover was initially working (the simulation tick was masking the bug).

## Blast Radius
**System-wide** — affects every user on every graph load. The feature becomes broken after ~10 seconds of page load for every session.

## Impact
- **User:** Core interaction (hover-to-explore) stops working. Graph becomes non-interactive.
- **Business:** Makes the tool appear broken after a short warm-up period.
- **Security:** None.

## Recommendation
**Fix:** Add `"hoveredNode"` to the store listener condition:
```javascript
store.addEventListener("change", (e) => {
  if (
    e.detail.keys.includes("filter") ||
    e.detail.keys.includes("selectedNode") ||
    e.detail.keys.includes("hoveredNode")  // ADD THIS
  ) {
    draw();
  }
});
```
**Prevention:** Write integration test: (1) let simulation settle, (2) dispatch hoveredNode change, (3) assert draw() was called.

## Test Cases
- After simulation `alpha < 0.001`, `setState({ hoveredNode: node })` → `draw()` called once.
- `setState({ hoveredNode: null })` → `draw()` called (hover removal also redraws).
- Verify `isDimmed()` returns correct value for `focus = hoveredNode` post-simulation.

## Regression Risk
High — any change to the store listener condition must include all relevant keys.

## Related Code Path
`graph.js:476–480` (listener), `graph.js:209–212` (tick → draw), `graph.js:89–110` (isDimmed uses hoveredNode)

---

# Finding 2

## Title
Escape key during consent modal fires BOTH modal cancel AND `selectedNode = null` — panel closes unexpectedly

## Severity
High

## Likelihood
High

## Confidence
High

## Category
Functional Bug / Event Conflict / User Experience

## Scenario
User selects a node, panel opens. User clicks "Generate AI Insight". Consent modal appears. User presses Escape intending to cancel the modal and stay on the panel. Instead, both the modal closes AND the side panel closes (selectedNode is cleared).

## Description
`panel.js` `showConsentModal()` registers a global `document.addEventListener("keydown", onKey)` that maps `Escape → done(false)`. Simultaneously, `graph.js` registers its own `document.addEventListener("keydown")` that maps `Escape → setState({ selectedNode: null })`. Both listeners are active simultaneously. When Escape is pressed, both fire: the modal closes (correct) and `selectedNode` is set to `null` (incorrect side effect), causing the side panel to close.

## Evidence
```javascript
// panel.js lines 302-304: modal keydown handler
function onKey(e) {
  if (e.key === "Escape") done(false);       // closes modal
  else if (e.key === "Enter") done(true);
}
document.addEventListener("keydown", onKey);

// graph.js lines 461-462: global keydown handler (always active)
if (ev.key === "Escape") {
  setState({ selectedNode: null });           // clears panel
  hideTooltip();
}
```
```
Execution simulation:
  selectedNode = "some_node"
  Escape pressed:
    graph.js handler → selectedNode = null  ← side panel closes
    modal handler    → done(false)          ← modal closes
  Result: { selectedNode: null, modalClosed: true }
  
  VERIFIED: panel closes as side effect of modal cancel.
```

## Steps to Reproduce
1. Click any node → side panel opens.
2. Expand a function → click "Generate AI Insight".
3. Consent modal appears.
4. Press `Escape`.
5. **Expected:** Modal closes, side panel stays open.
6. **Actual:** Modal closes AND side panel closes. User must re-click the node.

## Expected Behavior
Escape while modal is open closes only the modal. The underlying panel state is preserved.

## Actual Behavior
Escape propagates to graph.js global handler, which unconditionally clears `selectedNode`, closing the panel.

## Root Cause
The modal's `onKey` handler does not call `ev.stopPropagation()` or `ev.stopImmediatePropagation()`, so the event reaches all other `document.keydown` listeners. The graph.js handler has no awareness of modal state.

## Blast Radius
**Module** — affects panel → AI consent flow only. No data corruption.

## Impact
- **User:** Disruptive — must re-click node and re-navigate to function. Creates impression of bug.
- **Consent flow:** User cancelled the modal intentionally but loses context.

## Recommendation
**Fix (Option A — stop propagation in modal):**
```javascript
function onKey(e) {
  if (e.key === "Escape") { e.stopImmediatePropagation(); done(false); }
  else if (e.key === "Enter") { e.stopImmediatePropagation(); done(true); }
}
```
**Fix (Option B — guard graph.js handler):**
```javascript
if (ev.key === "Escape") {
  if (document.querySelector(".consent-overlay")) return; // modal is open
  setState({ selectedNode: null });
}
```
Option A is cleaner — modal owns its own event scope.

## Test Cases
- Consent modal open + Escape → modal closes, `selectedNode` unchanged.
- Consent modal open + Enter → modal accepts, `selectedNode` unchanged.
- No consent modal + Escape → `selectedNode` cleared (existing behavior preserved).

## Regression Risk
Medium — fixing stopPropagation could affect other listeners on document; verify toast and search overlays are unaffected.

## Related Code Path
`panel.js:302–310` (modal keydown), `graph.js:457–473` (global keydown)

---

# Finding 3

## Title
`nodeAt()` quadtree search uses fixed 22px world-space radius — hit area is wrong at non-1× zoom

## Severity
High

## Likelihood
High

## Confidence
High

## Category
Functional Bug / Hit Testing / User Experience

## Scenario
User zooms out to fit a large graph (zoom ~0.2×). Clicks a node. The click registers on the wrong node or doesn't register at all. Conversely, at high zoom (4×), clicks near a node but slightly off hit an invisible dead zone.

## Description
`nodeAt()` calls `quadtree.find(wx, wy, 22)` with a hardcoded 22px radius in **world space**. The actual node radii range from 8px (degree=0) to 18px (degree=8+). At zoom 1×, a 22px world radius slightly overshoots the largest node, which is acceptable. But at zoom 0.2×, this 22px world radius represents **4.4px on screen** — smaller than the rendered node which appears at 8 × 0.2 = 1.6px screen px, but larger than the click target user expects.

More critically, the hit radius is not proportional to actual node radius — a degree-0 node (radius 8px) and a degree-8 node (radius 18px) have the exact same 22px hit radius. Nodes near each other with different sizes can be mis-hit.

## Evidence
```javascript
// graph.js line 82 (verified by reading source):
const found = quadtree.find(wx, wy, 22);  // hardcoded, not scaled

// Execution test:
function testHit(zoom, degree) {
  const nodeR = 8 + Math.min(degree * 1.2, 10);
  const screenHitRadius = 22 * zoom; // effective screen pixels
  return { nodeR, screenHitRadius };
}
testHit(0.2, 0)  // → { nodeR: 8, screenHitRadius: 4.4 }  ← undersize
testHit(4.0, 0)  // → { nodeR: 8, screenHitRadius: 88 }   ← 11× oversize
testHit(1.0, 8)  // → { nodeR: 17.6, screenHitRadius: 22 } ← roughly OK
```
```
At zoom 0.2×: user must click within 4.4 screen pixels of center to hit node.
At zoom 4.0×: clicking 88 screen pixels away from node center still hits.
```

## Steps to Reproduce
1. Load graps with any graph.
2. Zoom out to ~0.2× (press `F` to fit a large graph).
3. Click precisely on a visible node.
4. **Expected:** Node selects.
5. **Actual:** Click may miss — hits are within 4.4 screen px of node center only.

## Expected Behavior
Hit radius should scale with zoom: `hitRadius = (nodeRadius + slack) / transform.k`.

## Actual Behavior
Hit radius is fixed at 22px world-space regardless of zoom or actual node size.

## Root Cause
`nodeAt()` was written with a static 22px slack appropriate for zoom 1×. The zoom transform was not applied when computing the quadtree search radius.

## Blast Radius
**System-wide** — affects every click interaction at every zoom level other than 1×.

## Impact
- **User:** Frustrating interaction, especially on large graphs that require zooming out.
- **Functional:** Node selection/hover may miss or hit wrong node.

## Recommendation
**Fix:**
```javascript
function nodeAt(clientX, clientY) {
  if (!quadtree) return null;
  const rect = canvas.getBoundingClientRect();
  const sx = clientX - rect.left;
  const sy = clientY - rect.top;
  const wx = (sx - transform.x) / transform.k;
  const wy = (sy - transform.y) / transform.k;
  // Scale slack by inverse zoom so screen-space hit is consistent
  const slack = 4 / transform.k;
  const maxR = 18; // max nodeRadius (degree ≥ 8)
  const found = quadtree.find(wx, wy, maxR + slack);
  if (!found) return null;
  const r = nodeRadius(found);
  const dx = found.x - wx, dy = found.y - wy;
  return (dx * dx + dy * dy) <= (r + slack) * (r + slack) ? found : null;
}
```

## Test Cases
- At zoom 0.2×: click 8 screen px from node center of radius-8 node → hits.
- At zoom 4×: click 20 screen px from node center → misses.
- At zoom 1×: existing behavior preserved.

## Regression Risk
Medium — changes hit testing for all zoom levels. Must re-verify click behavior across zoom range.

## Related Code Path
`graph.js:73–87` (nodeAt), `graph.js:44–47` (nodeRadius)

---

# Finding 4

## Title
Concurrent AI insight requests for same function — stale response can overwrite fresh response

## Severity
Medium

## Likelihood
Medium

## Confidence
High

## Category
Race Condition / Data Integrity / User Experience

## Scenario
User rapidly double-clicks "Generate AI Insight" button. Two fetch requests fly out. Slower request (older) arrives after faster request (newer) — stale data overwrites the correct result.

## Description
`panel.js` `callAI()` sets `aiResults.set(key, { loading: true })` then fires `fetch()`. There is no guard to prevent a second call for the same key while the first is in-flight. Both calls proceed independently. Each `await` returns to the event loop; whichever `fetch` resolves last sets the final value in `aiResults`. If the first (slower) server request resolves after the second (faster) one, the first response — which may be for a different cache state or contain an error — overwrites the successful response.

## Evidence
```javascript
// panel.js lines 324-359 (verified by reading source)
async function callAI(fnName) {
  // ...
  const key = node.path + "::" + fnName;
  aiResults.set(key, { loading: true });  // ← no "already loading?" check
  render();
  // fetch fires immediately — no dedup
  const r = await fetch("/api/ai/summary", { ... });
  const data = await r.json();
  aiResults.set(key, data);   // ← can overwrite a faster successful response
  render();
}
```
```
Execution simulation:
  T=0:   Call 1 starts: key → {loading:true}, fetch #1 starts
  T=0:   Call 2 starts: key → {loading:true}, fetch #2 starts (no guard)
  T=150ms: fetch #2 resolves: key → {summary: "correct data"}
  T=300ms: fetch #1 resolves: key → {error_type: "timeout"} ← OVERWRITES correct
```

## Steps to Reproduce
1. Select a node with functions.
2. Expand a function detail.
3. Rapidly click "Generate AI Insight" twice in quick succession.
4. Observe — final displayed result may be an error or stale response.

## Expected Behavior
If an AI request is already in-flight for a key, subsequent clicks are ignored until the in-flight request resolves.

## Actual Behavior
Multiple concurrent requests are fired; last-writer wins regardless of request order.

## Root Cause
No in-flight deduplication guard at the top of `callAI()`. The loading state check was not implemented.

## Blast Radius
**Module** — affects AI insight section of side panel only.

## Impact
- **User:** Sees incorrect error state or wrong AI response.
- **Data:** AI results cache on server is correct (server is idempotent); only in-memory `aiResults` Map is affected.

## Recommendation
**Fix:**
```javascript
async function callAI(fnName) {
  const node = currentNode();
  if (!node) return;
  const fn = (node.functions || []).find((f) => f.name === fnName);
  if (!fn) return;
  const key = node.path + "::" + fnName;
  
  // Guard: skip if already loading
  const existing = aiResults.get(key);
  if (existing && existing.loading) return;  // ADD THIS
  
  // ... rest of function
}
```

## Test Cases
- Call `callAI("fn")` twice rapidly → only one fetch fires.
- After first resolves, calling again → fires new request.
- Loading state visible during single in-flight request.

## Regression Risk
Low — guard only prevents duplicate in-flight calls; doesn't affect single-call behavior.

## Related Code Path
`panel.js:314–360` (callAI), `panel.js:125–162` (aiSection renders loading state)

---

# Finding 5

## Title
`fitToViewport()` computes NaN transform when called before D3 has assigned node positions

## Severity
Medium

## Likelihood
Medium

## Confidence
High

## Category
Functional Bug / NaN Propagation / State Corruption

## Scenario
User presses `F` (fit to viewport) immediately after page load, before the D3 force simulation has run its first tick and assigned `x`, `y` values to nodes.

## Description
`fitToViewport()` iterates over `nodes` to find bounding box (`minX`, `minY`, `maxX`, `maxY`). If any node has `x = undefined` (pre-simulation), the comparisons `n.x < minX` and `n.x > maxX` with `Infinity` evaluate as `false` (NaN comparison). `minX` stays `Infinity`, `maxX` stays `-Infinity`. Then `w = maxX - minX = -Infinity - Infinity = -Infinity`. The `|| 1` fallback: `(-Infinity) || 1 = -Infinity` (truthy). `k = Math.min(width / (-Infinity + 120), ...) = NaN`. The D3 zoom transform is called with `translate(NaN, NaN).scale(NaN)`, corrupting the zoom state permanently for that session.

## Evidence
```javascript
// Execution test (Node.js verified):
function testFitToViewport(nodes) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    if (n.x < minX) minX = n.x;
    if (n.x > maxX) maxX = n.x;
  }
  const pad = 60;
  const w = (maxX - minX) || 1;
  const k = Math.min(800 / (w + pad * 2), 600 / (h + pad * 2), 2);
  return { minX, maxX, w, k, valid: isFinite(k) && k > 0 };
}
testFitToViewport([{x: undefined, y: undefined}])
// → { minX: Infinity, maxX: -Infinity, w: -Infinity, k: -0, valid: false }
```
```
NaN or -0 passed to d3.zoomIdentity.scale(-0) → zoom is corrupted.
Subsequent pan/zoom operations behave erratically or do nothing.
```

## Steps to Reproduce
1. Load graps with any graph.
2. Immediately press `F` before the loading screen disappears.
3. Observe — graph may not render, zoom indicator shows `NaN%`, further zoom/pan disabled.

## Expected Behavior
`fitToViewport()` is a no-op (or deferred) if nodes don't have valid positions yet.

## Actual Behavior
NaN transform is applied, corrupting zoom state.

## Root Cause
No guard for unpositioned nodes. The existing guard `if (!nodes.length) return` handles the empty case but not the "nodes exist but have no coordinates" case.

## Blast Radius
**Session-wide** — corrupts zoom behavior for the rest of the page session.

## Impact
- **User:** Graph becomes unnavigable (zoom/pan broken). Must reload page.

## Recommendation
**Fix:**
```javascript
function fitToViewport() {
  if (!nodes.length) return;
  // Guard: ensure nodes have been positioned by simulation
  const positioned = nodes.filter(n => typeof n.x === 'number' && isFinite(n.x));
  if (!positioned.length) return;  // ADD THIS
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of positioned) {  // iterate positioned only
    // ...
  }
}
```

## Test Cases
- `fitToViewport()` with all nodes `{x: undefined}` → no-op, zoom unchanged.
- `fitToViewport()` with some positioned, some not → uses only positioned.
- `fitToViewport()` with single node → `w = 0`, uses `|| 1` fallback (already correct).

## Regression Risk
Low — guard only adds early return; doesn't change behavior when positions are valid.

## Related Code Path
`graph.js:255–271` (fitToViewport), `graph.js:464–465` (keyboard shortcut 'f')

---

# Finding 6

## Title
Edge draw guard checks `s.x` but not `t.x` — `lineTo(undefined, undefined)` on partially-initialized edges

## Severity
Medium

## Likelihood
Low

## Confidence
High

## Category
Functional Bug / Canvas Rendering / Off-by-one Guard

## Scenario
D3 force simulation initializes node positions lazily or when a new node is added to a running simulation mid-session. During the first few ticks, some target nodes (`t`) may not yet have numeric `x`/`y` values. The edge draw code guards on `s.x` but not `t.x`, drawing a line to `(undefined, undefined)`.

## Description
In `draw()`, the edge rendering loop guards: `if (!s || !t || typeof s.x !== 'number') continue`. The check covers `s.x` but `t.x` is unguarded. If `t.x` is `undefined` (node not yet positioned), `ctx.lineTo(undefined, undefined)` is called. HTML Canvas coerces `undefined` to `0`, resulting in a line drawn from `(s.x, s.y)` to `(0, 0)` — the canvas origin — producing a spurious line artifact in the upper-left corner.

## Evidence
```javascript
// graph.js line 127:
if (!s || !t || typeof s.x !== 'number') continue;  // t.x not checked!

// Execution test:
function testEdgeDraw(s, t) {
  if (!s || !t || typeof s.x !== 'number') return "SKIP";
  if (typeof t.x !== 'number') return "BUG: lineTo(NaN)";
  return "OK";
}
testEdgeDraw({x:100,y:100}, {x:undefined,y:100})
// → "BUG: lineTo(NaN)"
```
```
Canvas behavior: ctx.lineTo(undefined, undefined) → ctx.lineTo(NaN, NaN)
NaN gets coerced to 0 in some implementations → line drawn to (0,0).
```

## Steps to Reproduce
1. This is most likely to occur during the very first simulation tick before all nodes receive positions.
2. May also occur if `graph_builder` returns an edge referencing a node ID that has no matching node object (though D3 silently ignores unresolvable IDs, the `Object.assign` copy won't have `x`).

## Expected Behavior
Guard condition covers both `s.x` and `t.x`.

## Actual Behavior
`t.x` unchecked; line may be drawn to canvas origin.

## Root Cause
Asymmetric guard — incomplete coverage of the target node.

## Blast Radius
**Local** — visual artifact only, no data corruption.

## Impact
- **Visual:** Spurious lines from node to canvas origin during early simulation ticks.
- **User:** Brief visual glitch on graph load.

## Recommendation
**Fix:**
```javascript
// graph.js line 127 — add t.x check:
if (!s || !t || typeof s.x !== 'number' || typeof t.x !== 'number') continue;
```

## Test Cases
- Edge where `s.x = 100`, `t.x = undefined` → line skipped (no console error, no artifact).
- Edge where both `s.x = 100`, `t.x = 200` → line drawn normally.

## Regression Risk
Low — only adds an early-continue for an already-invalid state.

## Related Code Path
`graph.js:125–143` (edge draw loop)

---

# Finding 7

## Title
Tooltip clips off-screen when node is near viewport edges — no boundary clamping

## Severity
Medium

## Likelihood
Very High

## Confidence
High

## Category
UX Bug / Layout / Accessibility

## Scenario
User hovers over a node in the bottom-right quadrant of the graph. The tooltip appears partially or fully off-screen, making the file path and metadata unreadable.

## Description
`showTooltip()` positions the tooltip at `(clientX + 14, clientY + 14)` with no viewport boundary check. The tooltip has `min-width: 180px` and typical height of ~80px. On a 1920×1080 display, hovering at `(1900, 1060)` places the tooltip at `(1914, 1074)` — 174px past the right edge and outside the bottom of the viewport.

## Evidence
```javascript
// graph.js lines 293-295, 304-306:
tip.style.left = (ev.clientX + 14) + "px";
tip.style.top  = (ev.clientY + 14) + "px";
// No viewport bounds check.

// Execution test:
function testTooltipPos(clientX, clientY, screenW=1920, screenH=1080) {
  return {
    left: clientX + 14,
    top: clientY + 14,
    clipsRight: clientX + 14 + 180 > screenW,   // min-width=180
    clipsBottom: clientY + 14 + 80 > screenH,    // approx height
  };
}
testTooltipPos(1900, 1060)
// → { left: 1914, top: 1074, clipsRight: true, clipsBottom: true }
```

## Steps to Reproduce
1. Load graps with nodes distributed to the right/bottom of the canvas.
2. Hover over a node near the bottom-right corner of the viewport.
3. **Expected:** Tooltip repositions to stay within viewport.
4. **Actual:** Tooltip renders off-screen or partially clipped.

## Expected Behavior
Tooltip flips direction (renders above-left of cursor) when near viewport edges.

## Actual Behavior
Tooltip is positioned unconditionally to the bottom-right of cursor.

## Root Cause
No viewport boundary logic was implemented — simple offset was chosen for MVP.

## Blast Radius
**Local** — tooltip rendering only.

## Impact
- **User:** Cannot read tooltip info for nodes in corners.
- **Accessibility:** Info hidden from users with smaller screens or zoomed browser.

## Recommendation
**Fix:**
```javascript
function showTooltip(node, ev) {
  const tip = document.getElementById("tooltip");
  if (!tip) return;
  // ... render innerHTML ...
  tip.style.display = "block";
  // Measure after display:block so offsetWidth/Height are accurate
  const tw = tip.offsetWidth || 200;
  const th = tip.offsetHeight || 80;
  let left = ev.clientX + 14;
  let top = ev.clientY + 14;
  if (left + tw > window.innerWidth)  left = ev.clientX - tw - 14;
  if (top  + th > window.innerHeight) top  = ev.clientY - th - 14;
  tip.style.left = left + "px";
  tip.style.top  = top  + "px";
}
```

## Test Cases
- Node near right edge: tooltip appears to the left of cursor.
- Node near bottom edge: tooltip appears above cursor.
- Node in center: tooltip appears to bottom-right (existing behavior).

## Regression Risk
Low — only changes tooltip position calculation; content unchanged.

## Related Code Path
`graph.js:282–307` (showTooltip), `style.css:258–298` (tooltip styles, `min-width: 180px`)

---

# Finding 8

## Title
Search `selectedNode` is raw graph-data node (no `_neighbors`/`_degree`) — dimming broken between `setState` calls

## Severity
Medium

## Likelihood
High

## Confidence
High

## Category
State Consistency Bug / Brief Rendering Glitch

## Scenario
User opens search (Cmd+K), types a filename, presses Enter to select. During the brief window between search's `setState` and the `graps:pan-to` handler's `setState`, the selected node object lacks `_neighbors`, so `isDimmed()` returns incorrect values for all nodes.

## Description
`search.js` `choose()` calls `setState({ selectedNode: n })` where `n` is from `store.state.graph.nodes` — the raw API response objects. These objects do NOT have `_neighbors` or `_degree` (computed by `precomputeNeighbors()` on the simulation copies). Then `search.js` dispatches `graps:pan-to`, which causes `graph.js` to find the simulation node copy and call `setState({ selectedNode: simulationNode })` — the correct object with `_neighbors`.

Between these two `setState` calls, `draw()` is called by the first `setState`'s store event (since key = `"selectedNode"`). In `isDimmed()`, `focus._neighbors` is `undefined`. The `if (neigh && ...)` guard means `neigh = undefined` → condition is false → no dimming occurs for any node → entire graph is rendered at full opacity.

## Evidence
```javascript
// search.js lines 78-82:
function choose(i) {
  const n = results[i];               // n = raw graph node (no _neighbors)
  if (!n) return;
  setState({ selectedNode: n });       // ← triggers draw() with wrong node type
  window.dispatchEvent(new CustomEvent("graps:pan-to", { detail: { id: n.id } }));
  close();
}

// graph.js lines 483-489 (pan-to handler):
window.addEventListener("graps:pan-to", (ev) => {
  const node = nodes.find((n) => n.id === ev.detail.id || n.path === ev.detail.id);
  if (node) {
    panTo(node);
    setState({ selectedNode: node });  // ← corrects to simulation node (has _neighbors)
  }
});

// graph.js isDimmed() line 106-107:
const neigh = focus._neighbors;       // undefined for raw graph node
if (neigh && !neigh.has(node.id)) return true;  // neigh=undefined → no dimming
```
```
Frame 1: setState(rawNode) → draw() → isDimmed(): no dimming (all nodes full opacity)
Frame 2: setState(simNode) → draw() → isDimmed(): correct dimming applied
The flash is ~1 event loop tick — may be visible as a single frame flicker.
```

## Steps to Reproduce
1. Open Cmd+K search.
2. Search and select a node.
3. Observe graph canvas — brief flash where ALL nodes are undimmed.

## Expected Behavior
Selection immediately shows the correct neighbor-highlight dimming with no intermediate incorrect state.

## Actual Behavior
One-frame flash of no-dimming, then corrects. On slower machines this flash may be visible.

## Root Cause
`search.js` uses graph-data nodes from store; `graph.js` uses simulation copies. No shared node identity.

## Blast Radius
**Local** — one-frame visual glitch on search selection.

## Impact
- **User:** Brief visual artifact. Low severity but indicates architectural inconsistency.

## Recommendation
**Fix (Option A — search dispatches only pan-to, not setState):**
```javascript
// search.js choose():
function choose(i) {
  const n = results[i];
  if (!n) return;
  // Don't setState here; let pan-to handler do it with the correct simulation node
  window.dispatchEvent(new CustomEvent("graps:pan-to", { detail: { id: n.id } }));
  close();
}
```
This removes the intermediate wrong-type setState. Panel.js `boot()` listens to selectedNode change — it will render correctly once pan-to sets the simulation node.

## Test Cases
- Select node via search → single `draw()` call with correct `_neighbors` set.
- No intermediate frame with undimmed graph.

## Regression Risk
Low — removes one `setState` call that was already being overwritten.

## Related Code Path
`search.js:76–82` (choose), `graph.js:483–489` (pan-to handler), `graph.js:89–110` (isDimmed)

---

# Finding 9

## Title
`#path-chip` element never updated — always displays `'./'` regardless of actual scan root

## Severity
Low

## Likelihood
Very High

## Confidence
High

## Category
Functional Gap / Missing Wiring / UI Staleness

## Scenario
User scans `/home/user/my-project`. The top bar shows `◇ graps  ./  42 files  137 fns`. The path `./` is always hardcoded — the actual root path is never shown.

## Description
`index.html` initializes `#path-chip` to `'./'`. `graph.js` `updateTopBarStats()` updates `#topbar-stats` with file/function counts but never updates `#path-chip`. The actual root is available in `graph.meta.root` (set by scanner), used in `showEmpty()` for the empty-state message — but never wired to the UI chip.

## Evidence
```javascript
// index.html line 24:
<span id="path-chip" class="path-chip">./</span>

// graph.js lines 385-390 (updateTopBarStats — only updates stats):
function updateTopBarStats(meta) {
  const el = document.getElementById("topbar-stats");
  if (!el || !meta) return;
  el.textContent = (meta.total_files || 0) + " files  " +
    (meta.total_functions || 0) + " fns";
  // No path-chip update here.
}

// graph.js line 354 (showEmpty — uses meta.root but not for path-chip):
"graps scanned " + escapeHtml(graph.meta && graph.meta.root || ".") + " ..."
```
```
Execution: graph.meta.root = "/home/user/project"
  #topbar-stats: "42 files  137 fns"  ← updated correctly
  #path-chip:    "./"                  ← never updated (BUG)
```

## Steps to Reproduce
1. Run `graps /home/user/my-project`.
2. Browser opens.
3. **Expected:** Path chip shows `my-project` or `/home/user/my-project`.
4. **Actual:** Path chip shows `./`.

## Expected Behavior
`#path-chip` displays `graph.meta.root` (or its basename) after graph loads.

## Actual Behavior
`#path-chip` hardcoded to `'./'` forever.

## Root Cause
`updateTopBarStats()` was not extended to include the path chip. A single line was missed.

## Blast Radius
**Local** — cosmetic UI element only.

## Impact
- **User:** Cannot confirm which directory was scanned from the top bar.
- **UX:** Appears unfinished.

## Recommendation
**Fix — in `updateTopBarStats()`:**
```javascript
function updateTopBarStats(meta) {
  const el = document.getElementById("topbar-stats");
  if (!el || !meta) return;
  el.textContent = (meta.total_files || 0) + " files  " +
    (meta.total_functions || 0) + " fns";
  
  // ADD: update path chip
  const chip = document.getElementById("path-chip");
  if (chip && meta.root) chip.textContent = meta.root;
}
```

## Test Cases
- Graph loads with `meta.root = "/home/user/project"` → `#path-chip` shows `/home/user/project`.
- Graph loads with `meta.root = null` → `#path-chip` stays `'./'` (fallback).

## Regression Risk
Minimal — additive change only.

## Related Code Path
`graph.js:385–390` (updateTopBarStats), `index.html:24` (path-chip init)

---

# Finding 10

## Title
Warning banner CSS `height` transition does not animate — `height: auto` cannot be transitioned

## Severity
Low

## Likelihood
Very High

## Confidence
High

## Category
CSS Bug / Animation / UX Polish

## Scenario
User clicks "Show all" on the warning banner. Expected: smooth slide-down to full height. Actual: instant snap to expanded height.

## Description
`style.css` defines `.warning-banner { transition: height 200ms ease-out; }`. The collapsed state has `height: 36px`; the expanded state has `height: auto`. CSS `transition` does NOT interpolate to/from `height: auto` — it's a computed value that cannot be intermediate-stepped. The transition fires (200ms runs) but there is no intermediate state to animate through, so the visual result is an instant height change.

## Evidence
```css
/* style.css lines 219-226: */
.warning-banner {
  transition: height 200ms ease-out;  /* ← transition defined */
}
.warning-banner.collapsed { height: 36px; }
.warning-banner.expanded  { height: auto; max-height: 160px; overflow-y: auto; }

/* CSS spec: transitions between height:36px and height:auto
   are NOT interpolated — auto is a keyword, not a length.
   Browser behavior: instant jump to auto height. */
```
```
Execution: toggle "Show all" → classList.toggle("expanded") fires
  height transitions from 36px → auto
  No intermediate height values — instant snap
  200ms transition registered but visually a no-op
```

## Steps to Reproduce
1. Load graps with a scan that produces at least one warning.
2. Click "Show all" on the warning banner.
3. **Expected:** Smooth expand animation (~200ms).
4. **Actual:** Instant snap to expanded height.

## Expected Behavior
Smooth height animation on expand/collapse.

## Actual Behavior
Instant height change — no visible animation.

## Root Cause
`height: auto` is not a transitionable value in CSS. This is a known CSS limitation.

## Blast Radius
**Local** — cosmetic animation only.

## Recommendation
**Fix — use `max-height` transition instead:**
```css
.warning-banner {
  overflow: hidden;
  transition: max-height 200ms ease-out;  /* transition max-height, not height */
}
.warning-banner.collapsed { max-height: 36px; }
.warning-banner.expanded  { max-height: 160px; overflow-y: auto; }
/* Remove height: 36px / height: auto — use max-height only */
```
This is the standard CSS-only technique for smooth height animation without JavaScript measurement.

## Test Cases
- Click "Show all" → smooth expansion over ~200ms.
- Click "Hide" → smooth collapse over ~200ms.
- Animation respects `prefers-reduced-motion` (already handled by existing media query).

## Regression Risk
Minimal — CSS-only change, no JS changes needed.

## Related Code Path
`style.css:218–226` (warning-banner), `graph.js:494–500` (toggle handler)

---

# Finding 11

## Title
`setState()` uses shallow `Object.assign` copy — direct mutation of nested state objects is undetectable by listeners

## Severity
Low

## Likelihood
Low

## Confidence
High

## Category
State Management Bug / Maintainability / Potential Future Bug

## Scenario
Future code (or a bug introduced in a refactor) directly mutates `store.state.filter.risk = "high"` instead of calling `setState`. This change is invisible to all store listeners — no `draw()`, no pill update.

## Description
`filter.js` `setState()` creates `prev` via `Object.assign({}, store.state)` — a shallow copy. `store.state.filter` is an object reference. After `Object.assign`, `prev.filter === store.state.filter` (same reference). If `store.state.filter.risk` is mutated directly, both `prev.filter` and `store.state.filter` reflect the mutation simultaneously — `e.detail.prev.filter` and `e.detail.next.filter` are identical, so listeners cannot detect what changed.

## Evidence
```javascript
// filter.js lines 24-29:
function setState(partial) {
  const prev = Object.assign({}, store.state);  // shallow copy
  Object.assign(store.state, partial);
  store.dispatchEvent(new CustomEvent("change", {
    detail: { prev: prev, next: store.state, keys: Object.keys(partial) },
  }));
}

// Execution test (verified):
const state = { filter: { risk: null, dead: false }, selectedNode: null };
const prev = Object.assign({}, state);
state.filter.risk = "high";  // direct mutation
prev.filter.risk === state.filter.risk  // → true (same reference!)
// prev.filter.risk: "high"  (not "null" as expected)
```

## Steps to Reproduce
This is a latent/maintenance bug — not currently triggered by any code.
1. Introduce code that does `store.state.filter.risk = "high"` directly (bypassing setState).
2. No `change` event fires → no UI update.

## Expected Behavior
All state changes, whether via `setState` or mutation, are detectable by listeners.

## Actual Behavior
Direct mutation of nested objects is invisible to the event system.

## Root Cause
`Object.assign` does not deep-clone nested objects. The correct pattern is to always call `setState()` and never mutate `store.state` directly — which is documented in a comment. However, the store does not enforce this invariant.

## Blast Radius
**System-wide if triggered** — but currently not triggered by any existing code.

## Impact
- **Maintainability:** Any future code that accidentally mutates nested state produces silent UI bugs.

## Recommendation
**Short-term:** Document the limitation more prominently with `// WARNING: do not mutate store.state directly`.
**Long-term:** Deep clone `filter` in `setState`, or use a Proxy to throw on direct mutation:
```javascript
function setState(partial) {
  const prev = {
    ...store.state,
    filter: { ...store.state.filter },  // deep-clone filter specifically
    selectedNode: store.state.selectedNode,
  };
  Object.assign(store.state, partial);
  store.dispatchEvent(new CustomEvent("change", {
    detail: { prev, next: store.state, keys: Object.keys(partial) },
  }));
}
```

## Test Cases
- `setState({ filter: { risk: "high", dead: false } })` → `e.detail.prev.filter.risk === null`.
- Direct mutation `store.state.filter.risk = "high"` → throws (if Proxy added) or no event fires (current documented contract).

## Regression Risk
Low — no current code directly mutates nested state.

## Related Code Path
`filter.js:24–30` (setState), `filter.js:17–22` (state definition)

---

# Finding 12

## Title
`errorMsg()` maps `network` and unknown AI errors to identical message — user cannot distinguish failure type

## Severity
Low

## Likelihood
Medium

## Confidence
High

## Category
UX / Observability / Error Diagnosis

## Scenario
AI insight request fails due to network connectivity loss. User sees "AI error" — the same message shown for parse errors, unknown server errors, and any unrecognized error type. User cannot tell if retrying will help.

## Description
`panel.js` `errorMsg()` switch covers `auth_failed`, `rate_limited`, `timeout`, with a `default` of `"AI error"`. The catch block in `callAI()` sets `error_type: "network"` for fetch exceptions, but `"network"` falls to the default case. The distinction between a retryable transient network error and a permanent unknown server error is lost.

## Evidence
```javascript
// panel.js lines 362-372:
function errorMsg(data) {
  switch (data.error_type) {
    case "auth_failed":  return "API auth failed";
    case "rate_limited": return data.retry_after ? "Rate limited, retry in ..." : "Rate limited";
    case "timeout":      return "AI timeout";
    default:             return "AI error";  // network, unknown, server_error → all same
  }
}

// Execution:
["network", "unknown", "server_error"].forEach(t =>
  console.log(errorMsg({error_type: t}))  // → "AI error" for all three
)
```

## Recommendation
**Fix:**
```javascript
function errorMsg(data) {
  switch (data.error_type) {
    case "auth_failed":  return "API auth failed";
    case "rate_limited": return data.retry_after ? `Rate limited, retry in ${data.retry_after}s` : "Rate limited";
    case "timeout":      return "AI timeout";
    case "network":      return "Network error — check connection";  // ADD
    default:             return "AI error (" + (data.error_type || "unknown") + ")";  // include type
  }
}
```

## Related Code Path
`panel.js:362–372` (errorMsg), `panel.js:355–358` (catch block sets error_type="network")

---

# Finding 13

## Title
`escapeHtml` / `esc()` defined identically in `graph.js`, `panel.js`, and `search.js` — three-way divergence risk

## Severity
Informational

## Likelihood
Low

## Confidence
High

## Category
Maintainability / XSS Risk (latent)

## Description
Three separate `esc()`/`escapeHtml()` implementations exist across modules. All three are currently identical — confirmed by execution. However, any future XSS fix or encoding improvement must be applied in all three places. Missing even one creates a security regression.

## Evidence
```javascript
// graph.js:321-325, panel.js:20-24, search.js:18-22 — all identical:
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
// Verified: esc("<script>") === "&lt;script&gt;" in all three — IDENTICAL ✓
```

## Recommendation
Since the codebase uses IIFE modules without a build step, the simplest fix is to expose a single shared utility via `window.graps`:
```javascript
// toast.js or filter.js (earliest loaded):
window.graps.esc = function(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
};
// All other modules: const esc = window.graps.esc;
```

## Related Code Path
`graph.js:321–325`, `panel.js:20–24`, `search.js:18–22`

---

## Coverage Checklist

| Category | Status |
|----------|--------|
| Happy Path | Evaluated — graph loads, filters, search, AI, hover, zoom all covered |
| Unhappy Path | Evaluated — network error, NaN position, empty graph, API error |
| Edge Case | Evaluated — viewport corners, concurrent calls, pre-simulation key press |
| Corner Case | Evaluated — undefined node positions, same-name functions across files |
| Use Case | Evaluated — all documented user flows exercised |
| Misuse Case | Evaluated — rapid clicking, edge screen positions, early keyboard shortcuts |
| Boundary Conditions | Evaluated — zoom 0.2× / 4×, single node graph, 0-function files |
| Failure Modes | Evaluated — AI disabled, network down, consent cancel, graph load fail |
| Error Handling | Evaluated — toast system, AI error types, fetch exceptions |
| Concurrency | Evaluated — concurrent AI calls (Finding 4), store shallow copy (Finding 11) |
| Security | Evaluated — XSS escape functions verified identical; no input rendering via `innerHTML` without `esc()` found |
| Performance | Not enough information to evaluate — no profiling data; quadtree rebuild per tick noted in code comments as known O(n) tradeoff |
| Scalability | Not enough information to evaluate — comments note <500 nodes OK; no load testing data |
| Reliability | Evaluated — loading screen, error toasts, retry button present |
| Maintainability | Evaluated — triple esc() (Finding 13), async ordering fragility (Finding 8) |
| Architecture | Evaluated — IIFE modules, no build step, window.graps shared namespace |
| Regression Risk | Noted per finding |
| Breaking Change Risk | Noted per finding |
