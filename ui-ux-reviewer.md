# graps — UI/UX Planning & Design Specification (Anthropic Style)

> Source: `handoff.md` + `architect-review.md` (repo: Maouv/graps)  
> Skill: `/ui-ux` + `/impeccable` (brand.md + product.md + typeset.md + colorize.md)  
> Visual reference: anthropic.com (screenshot 2026-06-28)  
> Date: 2026-06-28  
> Status: Updated — Anthropic aesthetic adaptation

---

## 0. Anthropic Style Analysis (dari screenshot)

### Apa yang membuat anthropic.com terasa distinctive:

**1. Warna: Warm off-white, bukan cold gray**
- Background utama: `oklch(96% 0.008 75)` — warm sand, bukan pure white, bukan abu-abu
- Text utama: near-black `oklch(12% 0.005 75)` — warm dark, bukan `#000000`
- Accent gold/amber: hanya muncul di spot tertentu (Morocco chip di screenshot)
- Dark section footer: `oklch(10% 0.005 75)` — warm near-black, bukan `#000000` cold

**2. Typography: Confident + Editorial tapi tidak cliche**
- Display heading: **sangat besar, bold, black weight** — "AI research and products that put safety at the frontier"
- Teks heading tidak pakai italic (bukan editorial-serif cliche)
- Body text: medium weight, comfortable size, excellent line-height
- Underline-as-emphasis pada kata kunci di hero ("research" dan "products" digarisbawahi)

**3. Layout: Restraint yang deliberate**
- Margin kiri kanan lebar di mobile, tidak full-bleed
- Spacing antar section sangat generous
- Card dengan background warm sand (bukan white), border-radius bulat (16-20px)
- Grid bersih, tidak ramai

**4. Component DNA:**
- Cards: `background` slightly darker dari page bg, `border-radius: 16px`, no border/shadow yang keras
- Buttons: dark background (near-black), white text, rounded full, panah →
- Labels uppercase tracking: "MOROCCO", "DATE", "CATEGORY" — uppercase + tracked, tapi BUKAN untuk semua heading
- Navigation: minimal, hamburger menu, logo kiri

**5. Yang TIDAK ada di Anthropic style:**
- Gradient warna-warni
- Neon accent colors
- Drop shadows yang tebal
- Glassmorphism
- Banyak warna berbeda
- Icon yang besar-besar

---

## 0.1. Adaptasi untuk graps (developer tool)

graps adalah **product register** (tool, bukan marketing page). Tapi user request untuk "seperti Anthropic style" — jadi ini adalah **hybrid**:

> Ambil estetika visual Anthropic (warm palette, confident type, generous spacing, restraint), terapkan ke developer tool dark mode.

**Adaptation decisions:**
- Dark mode: tetap — ini developer tool, tidak bisa bright
- Warm dark: `oklch(10% 0.008 75)` bukan cold `#0D0F12` — warm near-black ala Anthropic footer
- Amber/gold accent: sesuai dengan Anthropic's golden accent — pakai untuk AI features dan highlights
- Typography: confident, heavyweight display untuk node labels/headers — bukan Inter thin
- Cards: rounded (12-16px), warm dark surface, no harsh borders
- Restraint: tidak banyak warna — hanya amber (AI/accent), risk colors (red/yellow/gray), dan warm neutrals

---

## 1. Design System — Anthropic-Adapted Dark

### 1.1 Color Tokens (OKLCH — perceptually uniform)

```css
/* === BASE — warm dark (Anthropic footer energy) === */
--bg-base:      oklch(10% 0.008 75);   /* warm near-black — bukan cold #0D0F12 */
--bg-surface:   oklch(14% 0.008 75);   /* panel, card */
--bg-elevated:  oklch(18% 0.008 75);   /* hover, elevated card */
--bg-border:    oklch(24% 0.008 75);   /* dividers */

/* === INK — warm (bukan cold gray) === */
--ink-primary:   oklch(94% 0.006 75);  /* primary text — warm off-white */
--ink-secondary: oklch(65% 0.008 75);  /* secondary — warm mid-gray */
--ink-muted:     oklch(42% 0.006 75);  /* muted / disabled */

/* === ACCENT — Anthropic amber/gold === */
--amber:         oklch(76% 0.15 75);   /* Anthropic's golden accent — Morocco chip */
--amber-dim:     oklch(76% 0.15 75 / 0.15);   /* amber tint background */
--amber-border:  oklch(76% 0.15 75 / 0.35);   /* amber border */

/* === RISK COLORS (dari handoff.md — tetap) === */
--risk-clean:   oklch(52% 0.02 250);   /* abu-abu cool — clean file */
--risk-warn:    oklch(76% 0.15 75);    /* amber — same as accent — medium/low risk */
--risk-high:    oklch(58% 0.22 25);    /* red — high risk */

/* === CRITICALITY DOTS === */
--crit-high:    oklch(58% 0.22 25);    /* red */
--crit-medium:  oklch(76% 0.15 75);    /* amber */
--crit-low:     oklch(62% 0.12 250);   /* blue */
--crit-clean:   oklch(32% 0.008 75);   /* dark warm gray */

/* === AI ACCENT — purple (tetap, diferensiasi dari amber) === */
--ai-purple:    oklch(68% 0.18 300);
--ai-dim:       oklch(68% 0.18 300 / 0.12);
--ai-border:    oklch(68% 0.18 300 / 0.3);

/* === EDGES === */
--edge-default: oklch(65% 0.008 75 / 0.2);
--edge-active:  oklch(94% 0.006 75 / 0.75);
--edge-dimmed:  oklch(65% 0.008 75 / 0.05);

/* === INTERACTIVE === */
--focus-ring:   oklch(68% 0.15 250);   /* blue focus */
```

**Kenapa amber bukan purple/blue untuk accent?**
Anthropic menggunakan warm gold/amber sebagai satu-satunya warna accent di atas warm neutrals. Ini consistent dengan "Morocco" chip yang berwarna golden di screenshot. Purple tetap dipakai untuk AI features karena harus berbeda dari risk colors.

### 1.2 Typography (Anthropic-Adapted)

```css
/* === FONTS === */
/* Display: Something with personality — bukan Inter */
/* Anthropic pakai font yang feel corporate-but-warm, bukan editorial */
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* 
  Sora: geometric sans, slightly friendly, bold weight terasa confident
  Bukan Inter (terlalu generic), bukan mono sebagai shorthand "technical"
  JetBrains Mono: untuk code, paths, function names (legitimate use)
*/

--font-ui:      'Sora', system-ui, sans-serif;
--font-code:    'JetBrains Mono', monospace;

/* === SCALE — fixed rem (product register) === */
--text-2xs: 0.6875rem;   /* 11px */
--text-xs:  0.75rem;     /* 12px */
--text-sm:  0.8125rem;   /* 13px */
--text-base: 0.875rem;   /* 14px — body default */
--text-md:  1rem;        /* 16px */
--text-lg:  1.125rem;    /* 18px */
--text-xl:  1.25rem;     /* 20px */
--text-2xl: 1.5rem;      /* 24px */

/* Ratio: 1.125 antar step — product register appropriate */
```

**Catatan font**: Anthropic pakai font proprietary. Untuk graps open source, Sora adalah padanan yang tepat — geometric, confident, tidak masuk reflex-reject list.

### 1.3 Spacing & Radius

```css
/* Spacing — generous, Anthropic-like */
--space-1:  0.25rem;   /* 4px */
--space-2:  0.5rem;    /* 8px */
--space-3:  0.75rem;   /* 12px */
--space-4:  1rem;      /* 16px */
--space-5:  1.25rem;   /* 20px */
--space-6:  1.5rem;    /* 24px */
--space-8:  2rem;      /* 32px */
--space-10: 2.5rem;    /* 40px */
--space-12: 3rem;      /* 48px */

/* Border radius — Anthropic cards pakai radius besar */
--radius-sm:  6px;
--radius-md:  10px;
--radius-lg:  14px;     /* panel, card utama */
--radius-xl:  20px;     /* modal, large card */
--radius-full: 9999px;  /* pills, buttons */

/* Z-index scale */
--z-canvas:   1;
--z-panel:    10;
--z-banner:   20;
--z-topbar:   30;
--z-tooltip:  40;
--z-toast:    60;
```

---

## 2. Information Architecture

```
graps UI
├── Top Bar (48px — warm dark surface)
├── Warning Banner (conditional, collapsible — amber tinted)
├── Graph Canvas (D3 force-directed, Canvas renderer)
└── Side Panel (slide-in 320px, warm dark, rounded left edge)
    ├── File Header (filename, path, badges)
    ├── Function List (accordion items, criticality dots)
    │   └── Function Expand
    │       ├── Params / Return / Line range
    │       ├── Called by / Calls (clickable → graph pan)
    │       ├── Risk Flags (amber/red cards)
    │       └── AI Insight (purple, on demand)
    └── Constants / Imports (collapsed sections)
```

---

## 3. Layout Blueprint

```
┌──────────────────────────────────────────────────────────────────┐
│  TOP BAR — warm dark, 48px                                       │
│  [graps]  [./src]  ·  12 files  47 fns  [⬤ High×3] [💀 Dead×2] │
├──────────────────────────────────────────────────────────────────┤
│  ⚠ BANNER (amber, 36px, collapsible)                             │
├───────────────────────────────────────────┬──────────────────────┤
│                                           │                      │
│                                           │  SIDE PANEL          │
│           GRAPH CANVAS                    │  320px               │
│           (D3 + Canvas2D)                 │  warm dark           │
│           flex: 1                         │  slide-in            │
│                                           │  rounded-l-lg        │
│                                           │                      │
└───────────────────────────────────────────┴──────────────────────┘
```

**CSS Layout:**
```css
body {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-base);
  color: var(--ink-primary);
  font-family: var(--font-ui);
}

.top-bar {
  height: 48px;
  flex-shrink: 0;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--bg-border);
}

.main-area {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.canvas-wrap { flex: 1; position: relative; }

.side-panel {
  width: 0;
  transition: width 220ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
  overflow: hidden;
  background: var(--bg-surface);
  border-left: 1px solid var(--bg-border);
}

.side-panel.open { width: 320px; }
```

---

## 4. Component Specifications

---

### 4.1 Top Bar (Anthropic-adapted)

**Anthropic reference**: Minimal, logo kiri, hamburger kanan, tidak ramai.

```
[◇ graps]  [./src chip]  ·  12 files  47 fns     [⬤ High Risk ×3] [☠ Dead ×2]
```

**Visual:**
- Height: 48px
- Logo `◇ graps`: Sora 700, --text-md, --ink-primary. Simbol diamond (◇) sebagai logo mark — simple, tidak butuh SVG icon
- Path chip: `--font-code`, `--text-xs`, `--bg-elevated`, `--ink-secondary`, radius-sm, padding 4px 8px
- Stats: `--text-sm`, `--ink-muted`
- Filter pills: rounded-full, subtle

**Filter pills (Anthropic-adapted):**
```css
.filter-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  border: 1px solid var(--bg-border);
  background: transparent;
  color: var(--ink-secondary);
  font-family: var(--font-ui);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms ease-out;
}

.filter-pill:hover {
  background: var(--bg-elevated);
  color: var(--ink-primary);
}

.filter-pill.active[data-type="high"] {
  border-color: var(--risk-high);
  background: oklch(58% 0.22 25 / 0.1);
  color: var(--risk-high);
}

.filter-pill.active[data-type="dead"] {
  border-color: var(--amber);
  background: var(--amber-dim);
  color: var(--amber);
}
```

---

### 4.2 Graph Canvas (Force-Directed, Canvas2D)

**Anthropic reference**: Anthropic's globe visualization (dots on globe) — sparse, elegant, meaningful. Bukan ramai dengan warna.

**Node visual philosophy (Anthropic-adapted):**
- Nodes: circles dengan fill warm dark + colored ring (stroke) — bukan solid fill
- Ini lebih elegant: ring menunjukkan risk level, fill tetap gelap = konsisten
- Hub nodes (banyak edges): radius lebih besar, ring lebih tebal

```javascript
function drawNode(ctx, node, state) {
  const { x, y, risk_level, degree } = node;
  
  // Base radius + degree scaling
  const r = 8 + Math.min(degree * 1.2, 10); // 8-18px
  
  // Colors by risk
  const ringColor = {
    'clean':  'oklch(52% 0.02 250)',
    'yellow': 'oklch(76% 0.15 75)',
    'red':    'oklch(58% 0.22 25)',
  }[risk_level];
  
  const ringWidth = {
    'clean': 1.5,
    'yellow': 2,
    'red': 2.5,
  }[risk_level];
  
  // Opacity by state
  const opacity = state === 'dimmed' ? 0.1 : 
                  state === 'hovered' ? 1.0 : 
                  state === 'connected' ? 0.8 : 0.65;
  
  ctx.globalAlpha = opacity;
  
  // Fill: warm dark
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = 'oklch(18% 0.008 75)';
  ctx.fill();
  
  // Ring (risk color)
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.strokeStyle = ringColor;
  ctx.lineWidth = ringWidth;
  ctx.stroke();
  
  // Glow untuk high risk
  if (risk_level === 'red' && state !== 'dimmed') {
    ctx.shadowColor = 'oklch(58% 0.22 25)';
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.strokeStyle = ringColor;
    ctx.lineWidth = ringWidth;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
  
  // Selected state: outer ring
  if (state === 'selected') {
    ctx.beginPath();
    ctx.arc(x, y, r + 5, 0, Math.PI * 2);
    ctx.strokeStyle = 'oklch(94% 0.006 75 / 0.4)';
    ctx.lineWidth = 1;
    ctx.stroke();
  }
  
  ctx.globalAlpha = 1;
}
```

**Edge visual:**
```javascript
function drawEdge(ctx, source, target, weight, state) {
  const lineWidth = 0.5 + Math.min(weight * 0.35, 2.5);
  
  ctx.globalAlpha = state === 'dimmed' ? 0.04 : 
                    state === 'active' ? 0.7 : 0.18;
  
  ctx.beginPath();
  ctx.moveTo(source.x, source.y);
  ctx.lineTo(target.x, target.y);
  ctx.strokeStyle = state === 'active' ? 
    'oklch(94% 0.006 75)' : 
    'oklch(65% 0.008 75)';
  ctx.lineWidth = lineWidth;
  ctx.stroke();
  
  ctx.globalAlpha = 1;
}
```

**Hover Tooltip (Anthropic card style):**
```
┌─────────────────────────────────┐
│  user_service.py                │  ← Sora 600, --text-sm
│  services/user_service.py       │  ← mono, --text-xs, --ink-muted
│  ─────────────────────────────  │
│  ⬤ 2 high  •  1 medium         │  ← risk summary
└─────────────────────────────────┘
```

```css
.tooltip {
  position: fixed;
  pointer-events: none;
  padding: 10px 14px;
  background: var(--bg-elevated);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 32px oklch(0% 0 0 / 0.5);
  font-family: var(--font-ui);
  min-width: 180px;
  z-index: var(--z-tooltip);
}

.tooltip-filename {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink-primary);
  margin-bottom: 2px;
}

.tooltip-path {
  font-family: var(--font-code);
  font-size: var(--text-xs);
  color: var(--ink-muted);
  margin-bottom: 8px;
}

.tooltip-divider {
  height: 1px;
  background: var(--bg-border);
  margin-bottom: 8px;
}
```

**Zoom indicator (bottom-right, Anthropic-subtle):**
```
87%  [reset]
```
```css
.zoom-indicator {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-code);
  font-size: var(--text-xs);
  color: var(--ink-muted);
  background: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
}
```

**Edge Weight Legend (bottom-left):**
```css
.edge-legend {
  position: absolute;
  bottom: 16px;
  left: 16px;
  padding: 8px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-2xs);
  color: var(--ink-muted);
}
```

---

### 4.3 Side Panel (Anthropic card aesthetic)

**Anthropic reference**: Cards di screenshot pakai background slightly darker dari page background, radius besar, tidak ada hard drop shadow.

**Panel open animation:**
```css
.side-panel {
  width: 0;
  overflow: hidden;
  transition: width 220ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
  background: var(--bg-surface);
  border-left: 1px solid var(--bg-border);
}

.side-panel.open {
  width: 320px;
}

/* Panel inner scroll */
.panel-scroll {
  width: 320px;   /* fixed width untuk hindari reflow */
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: var(--bg-border) transparent;
}
```

#### 4.3.1 File Info Header

```
┌─────────────────────────────────────────────────────────────────┐
│                                                          [×]    │
│                                                                 │
│  user_service.py                                                │
│  services/user_service.py                                       │
│                                                                 │
│  [⬤ 2 high]  [● 1 medium]  [◯ 7 functions]                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

```css
.panel-header {
  padding: var(--space-5) var(--space-5) var(--space-4);
  border-bottom: 1px solid var(--bg-border);
}

.panel-close {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  color: var(--ink-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 120ms ease-out;
}

.panel-close:hover {
  background: var(--bg-elevated);
  color: var(--ink-primary);
}

.panel-filename {
  font-family: var(--font-ui);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--ink-primary);
  margin-bottom: 2px;
  font-feature-settings: 'ss01' 1;
}

.panel-filepath {
  font-family: var(--font-code);
  font-size: var(--text-xs);
  color: var(--ink-muted);
  margin-bottom: var(--space-4);
}

.badge-row {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 500;
  border: 1px solid;
}

.badge--high   { color: var(--risk-high); border-color: oklch(58% 0.22 25 / 0.35); background: oklch(58% 0.22 25 / 0.08); }
.badge--medium { color: var(--amber); border-color: var(--amber-border); background: var(--amber-dim); }
.badge--count  { color: var(--ink-secondary); border-color: var(--bg-border); background: var(--bg-elevated); }
```

#### 4.3.2 Function List

```
Functions                                              7
──────────────────────────────────────────────────────
⬤  get_user                           → User | None  ▸
──────────────────────────────────────────────────────
●  create_user                         → User         ▸
──────────────────────────────────────────────────────
○  _validate_email                     → bool         ▸
   dead code
──────────────────────────────────────────────────────
```

```css
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-5);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--ink-muted);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  border-bottom: 1px solid var(--bg-border);
}

/* Anthropic "DATE / CATEGORY" uppercase label style */
.section-count {
  font-family: var(--font-code);
  font-weight: 400;
  color: var(--ink-muted);
}

.fn-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 11px var(--space-5);
  cursor: pointer;
  transition: background 120ms ease-out;
  border-bottom: 1px solid var(--bg-border);
  min-height: 44px;
}

.fn-row:hover {
  background: var(--bg-elevated);
}

.fn-row.active {
  background: var(--bg-elevated);
  border-left: 2px solid var(--amber);
}

/* Criticality dot */
.crit-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.crit-dot--high   { background: var(--crit-high); box-shadow: 0 0 6px oklch(58% 0.22 25 / 0.5); }
.crit-dot--medium { background: var(--crit-medium); }
.crit-dot--low    { background: transparent; border: 1.5px solid var(--crit-low); }
.crit-dot--clean  { background: var(--crit-clean); }

.fn-name {
  flex: 1;
  font-family: var(--font-code);
  font-size: var(--text-sm);
  color: var(--ink-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fn-return {
  font-family: var(--font-code);
  font-size: var(--text-xs);
  color: var(--ink-muted);
  white-space: nowrap;
}

.fn-dead {
  font-style: italic;
  opacity: 0.6;
}

.fn-chevron {
  color: var(--ink-muted);
  transition: transform 150ms ease-out;
  font-size: 10px;
}

.fn-row.active .fn-chevron {
  transform: rotate(90deg);
}
```

#### 4.3.3 Function Detail Expand

```
▾  get_user
   ──────────────────────────────────────────────────
   PARAMETERS
   user_id   int

   RETURNS
   User | None

   LINES
   12 – 28   [open in editor ↗]

   ──────────────────────────────────────────────────
   CALLED BY   2
   → user_controller.py
   → admin_controller.py

   CALLS   2
   → get_session       db.py
   → User.query.filter models/user.py

   ──────────────────────────────────────────────────
   ⚠ RISKS
   ┌────────────────────────────────────────────────┐
   │  HIGH  None return unchecked                   │
   │  2 callers tidak handle None return:           │
   │  • user_controller.py                          │
   │  • admin_controller.py                         │
   └────────────────────────────────────────────────┘

   ──────────────────────────────────────────────────
   [✦ Generate AI Insight]
```

```css
.fn-detail {
  padding: 0 var(--space-5) var(--space-5);
  background: var(--bg-base);   /* sedikit lebih gelap dari panel */
  border-bottom: 1px solid var(--bg-border);
}

/* Meta label Anthropic style — uppercase tracked */
.detail-label {
  font-size: var(--text-2xs);
  font-weight: 600;
  color: var(--ink-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-top: var(--space-4);
  margin-bottom: var(--space-2);
}

.detail-value {
  font-family: var(--font-code);
  font-size: var(--text-sm);
  color: var(--ink-primary);
}

/* Caller/callee items — clickable */
.caller-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 0;
  font-family: var(--font-code);
  font-size: var(--text-sm);
  color: var(--ink-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color 120ms;
}

.caller-item:hover {
  color: var(--amber);  /* Anthropic amber on hover */
}

.caller-item::before {
  content: '→';
  color: var(--ink-muted);
  font-size: 11px;
}

/* Risk card — Anthropic card aesthetic */
.risk-card {
  margin-top: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid;
}

.risk-card--high {
  border-color: oklch(58% 0.22 25 / 0.3);
  background: oklch(58% 0.22 25 / 0.06);
}

.risk-card--medium {
  border-color: var(--amber-border);
  background: var(--amber-dim);
}

.risk-card--low {
  border-color: oklch(62% 0.12 250 / 0.3);
  background: oklch(62% 0.12 250 / 0.06);
}

.risk-title {
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-2);
}

.risk-card--high .risk-title   { color: var(--risk-high); }
.risk-card--medium .risk-title { color: var(--amber); }
.risk-card--low .risk-title    { color: oklch(62% 0.12 250); }

.risk-desc {
  font-size: var(--text-sm);
  color: var(--ink-secondary);
  line-height: 1.6;
}

.risk-files {
  margin-top: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.risk-file {
  font-family: var(--font-code);
  font-size: var(--text-xs);
  color: var(--ink-muted);
}

.risk-file::before { content: '• '; }
```

#### 4.3.4 AI Insight Button + Result

**Anthropic reference**: Tombol di screenshot adalah "Read more →" — dark background, white text, rounded-full, arrow.

```css
/* Button: Anthropic dark-button style */
.btn-ai {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 10px 16px;
  border-radius: var(--radius-full);
  background: var(--ai-dim);
  border: 1px solid var(--ai-border);
  color: var(--ai-purple);
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms ease-out;
  margin-top: var(--space-4);
}

.btn-ai:hover {
  background: oklch(68% 0.18 300 / 0.2);
  border-color: oklch(68% 0.18 300 / 0.5);
}

.btn-ai:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.btn-ai .icon { font-size: 14px; }

/* AI Result Card — Anthropic card style */
.ai-card {
  margin-top: var(--space-3);
  padding: var(--space-4);
  background: var(--bg-elevated);
  border: 1px solid var(--ai-border);
  border-radius: var(--radius-lg);
}

.ai-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.ai-card-title {
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--ai-purple);
  text-transform: uppercase;
  letter-spacing: 0.07em;
}

.ai-card-provider {
  font-size: var(--text-2xs);
  color: var(--ink-muted);
  font-family: var(--font-code);
}

.ai-field {
  margin-bottom: var(--space-3);
}

.ai-field-label {
  font-size: var(--text-2xs);
  font-weight: 600;
  color: var(--ink-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 4px;
}

.ai-field-value {
  font-size: var(--text-sm);
  color: var(--ink-primary);
  line-height: 1.65;
}

.ai-card-meta {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--bg-border);
  font-size: var(--text-2xs);
  color: var(--ink-muted);
  font-family: var(--font-code);
}
```

---

### 4.4 Warning Banner (Anthropic amber)

```css
.warning-banner {
  overflow: hidden;
  transition: height 200ms ease-out;
  background: oklch(76% 0.15 75 / 0.06);
  border-bottom: 1px solid oklch(76% 0.15 75 / 0.2);
}

.warning-banner.collapsed { height: 36px; }
.warning-banner.expanded  { height: auto; max-height: 160px; overflow-y: auto; }

.warning-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-5);
  height: 36px;
}

.warning-icon {
  color: var(--amber);
  font-size: 13px;
}

.warning-summary {
  flex: 1;
  font-size: var(--text-xs);
  font-weight: 500;
  color: oklch(76% 0.15 75);   /* amber text */
}

.warning-toggle {
  font-size: var(--text-xs);
  color: var(--ink-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: color 120ms;
}

.warning-toggle:hover { color: var(--ink-primary); }
```

---

### 4.5 Loading State

**Anthropic reference**: Clean, centered, tidak berlebihan.

```css
.loading-screen {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-5);
  background: var(--bg-base);
  z-index: 50;
}

.loading-logo {
  font-family: var(--font-ui);
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--ink-primary);
}

.loading-status {
  font-family: var(--font-code);
  font-size: var(--text-sm);
  color: var(--ink-secondary);
}

/* Progress bar — subtle amber */
.loading-bar-track {
  width: 200px;
  height: 2px;
  background: var(--bg-border);
  border-radius: 1px;
  overflow: hidden;
}

.loading-bar-fill {
  height: 100%;
  background: var(--amber);
  border-radius: 1px;
  transition: width 300ms ease-out;
}

.loading-stats {
  font-size: var(--text-xs);
  color: var(--ink-muted);
  font-family: var(--font-code);
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .loading-bar-fill { transition: none; }
}
```

---

### 4.6 Empty States (Anthropic card aesthetic)

```css
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: var(--space-10);
  text-align: center;
}

/* Anthropic-style: clean, no emoji yang noisy */
.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: var(--space-5);
  color: var(--ink-muted);
}

.empty-title {
  font-family: var(--font-ui);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--ink-primary);
  margin-bottom: var(--space-3);
}

.empty-desc {
  font-size: var(--text-sm);
  color: var(--ink-secondary);
  line-height: 1.7;
  max-width: 380px;
  margin-bottom: var(--space-6);
}

/* Command hint — Anthropic-style code chip */
.empty-cmd {
  font-family: var(--font-code);
  font-size: var(--text-sm);
  color: var(--ink-secondary);
  background: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-4);
}
```

**Three empty state variants:**

**Case 1: No Python files**
```
        ◇
     
  No Python files found
  
  graps scanned ./empty-folder
  and found 0 .py files to analyze.
  
  graps ./src
```

**Case 2: Single file (no edges)**
```
   ◉ main.py (solo)

  This file has no import
  relationships with other files.
```

**Case 3: Zero functions**
```
         ◇

  Files found, no functions detected

  Your Python files may contain only
  constants, imports, or module-level code.
```

---

## 5. Motion Specification

```
Principle: Motion yang menyampaikan state, bukan dekorasi (product register).
Reference: Anthropic.com motion adalah minimal — tidak ada page-load choreography.
```

| Trigger | Property | Duration | Easing |
|---------|----------|----------|--------|
| Panel slide in | width 0 → 320px | 220ms | cubic-bezier(0.25, 0.46, 0.45, 0.94) |
| Panel slide out | width 320px → 0 | 180ms | cubic-bezier(0.55, 0, 1, 0.45) |
| Warning banner expand | height | 200ms | ease-out |
| Function expand | height | 150ms | ease-out |
| Tooltip appear | opacity + translateY(4px → 0) | 100ms | ease-out |
| Filter active state | background, border | 150ms | ease-out |
| AI result appear | opacity 0 → 1, translateY(6px → 0) | 250ms | ease-out |
| Node hover (canvas) | radius +2, glow | ~2 frames | rAF |
| Toast appear | translateY(12px → 0), opacity | 200ms | ease-out |

```css
@media (prefers-reduced-motion: reduce) {
  .side-panel { transition: none !important; }
  .fn-detail  { transition: none !important; }
  .warning-banner { transition: none !important; }
  /* Opacity still ok — hanya skip transform/size transitions */
}
```

---

## 6. Accessibility

### ARIA
```html
<canvas role="img" aria-label="Dependency graph — 12 files, 47 functions, 3 high risk" tabindex="0" />

<aside role="complementary" aria-label="File detail" aria-hidden="true" />
<!-- aria-hidden="false" saat panel open -->

<button role="switch" aria-checked="false" aria-label="Filter: high risk only" class="filter-pill" />
```

### Keyboard
```
Tab       → focus: top bar elements, filter pills, panel close, AI button
Escape    → close panel / dismiss tooltip
Enter     → activate focused button
F         → fit graph to viewport
H         → toggle high-risk filter
D         → toggle dead-code filter
Cmd+K     → open node search (tambahan)
```

### Contrast Check (OKLCH)
- `--ink-primary` (94%) on `--bg-base` (10%): **~13:1** ✓ AAA
- `--ink-secondary` (65%) on `--bg-base` (10%): **~6.8:1** ✓ AA
- `--amber` (76% oklch) on `--bg-base` (10%): **~7.2:1** ✓ AA
- `--risk-high` (58% oklch) on `--bg-elevated` (18%): **~4.8:1** ✓ AA

---

## 7. Additions — Tidak Melanggar Handoff.md

Fitur-fitur berikut **tidak ada di handoff.md** tapi tidak bertentangan dengan scope MVP dan menambah value nyata:

### 7.1 Minimap (bottom-left)
- 120×80px canvas mini
- Dots kecil dengan risk color
- Viewport rect sebagai overlay
- Klik → pan ke area

### 7.2 Node Search (Cmd+K)
```css
.search-overlay {
  position: fixed;
  inset: 0;
  background: oklch(0% 0 0 / 0.5);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 15vh;
  z-index: var(--z-modal);
}

.search-box {
  width: 480px;
  background: var(--bg-elevated);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: 0 24px 80px oklch(0% 0 0 / 0.6);
}

.search-input {
  width: 100%;
  padding: 14px 20px;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--bg-border);
  font-family: var(--font-ui);
  font-size: var(--text-md);
  color: var(--ink-primary);
  outline: none;
}
```

### 7.3 Toast Notifications
```
┌────────────────────────────────────────┐
│  ✓  AI Insight cached                  │
└────────────────────────────────────────┘
```
Position: bottom-right, 3s auto-dismiss.

---

## 8. File Structure

```
frontend/
├── index.html      ← app shell
├── style.css       ← semua tokens + component styles
├── graph.js        ← canvas renderer, d3 simulation, hover/click
├── panel.js        ← panel logic, expand/collapse, AI call
├── filter.js       ← filter state management
├── search.js       ← Cmd+K search overlay
└── toast.js        ← toast notification queue
```

---

## 9. Critical Decisions (Updated)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Warm vs cold dark | **Warm** `oklch(10% 0.008 75)` | Anthropic DNA — tidak cold/sterile |
| Accent color | **Amber** `oklch(76% 0.15 75)` | Anthropic golden accent, matches risk-warn |
| Node visual | **Ring** (stroke) bukan solid fill | Lebih elegant, warm dark center = consistent |
| Font | **Sora** | Confident, tidak masuk reflex-reject list, ada personality |
| Card radius | **14px** | Anthropic's card radius — tidak terlalu boxy |
| AI accent | **Purple** | Diferensiasi dari amber yang dipakai untuk risk/warn |
| Canvas vs SVG | **Canvas** | Arsitektur decision dari architect-review.md: 2000+ nodes |
| Label strategy | **On-hover only** | Sesuai handoff, readability pada banyak nodes |

---

*End of Document*  
*Impeccable refs used: brand.md (aesthetic analysis), product.md (register), typeset.md (font decision), colorize.md (OKLCH strategy)*  
*Handoff.md constraints: fully respected — no scope changes*
