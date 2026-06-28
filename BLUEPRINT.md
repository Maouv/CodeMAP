# CodeMAP — Blueprint

> Status: Living Document — Source of Truth  
> Last updated: 2026-06-28  
> Contributors: Maou, Architect Agent, Security Agent, Packaging Agent, UX Agent

---

## 1. Project Overview

**codemap** adalah CLI tool open source yang membantu *semi-technical vibe coders* memahami codebase yang ditulis oleh AI agent mereka — melalui interactive visual dependency graph yang di-serve di localhost browser.

### Problem yang di-solve

Vibe coder (semi-technical) menghasilkan codebase yang mereka sendiri tidak confident untuk di-touch. Bukan karena tidak bisa baca syntax, tapi karena tidak punya **spatial awareness** — tidak tau dimana sesuatu berada, bagaimana semuanya terhubung, dan apa yang akan rusak kalau diubah.

### Core value proposition

> "Tunjukin aku peta, aku bisa navigate sendiri — tapi kasih tau kalau ada ranjau"

Bukan documentation generator. Bukan AI explainer. Tapi **living map of a codebase** yang memungkinkan vibe coder melakukan maintenance, debugging, dan refactoring dengan confident.

---

## 2. Target User

**Semi-technical vibe coder (User Type B)**

| Karakteristik | Detail |
|--------------|--------|
| Bisa baca code | Ya, kalau ditunjukin |
| Bisa tulis code | Sebagian, dengan bantuan AI |
| Pain point utama | Takut break things, tidak tau dampak perubahan |
| Tool comfort | CLI comfortable, familiar dengan localhost dev server |
| Tidak butuh | Explanation syntax dari nol, hand-holding ekstrem |

**Bukan target:**
- Pure non-technical (tidak ngerti syntax sama sekali)
- Senior developer (sudah punya mental model sendiri)

---

## 3. Distribution & Licensing

| Item | Detail |
|------|--------|
| **Package name** | `codemap` |
| **Distribution** | PyPI (`pip install codemap`) |
| **License** | MIT |
| **Language support** | Python only (MVP) |
| **AI layer** | BYOK — user set env variable sendiri |
| **Repository** | GitHub (open source) |

### AI Provider support

```bash
# Anthropic (default kalau keduanya ada)
export ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
export OPENAI_API_KEY=sk-...
```

Tool detect otomatis key mana yang tersedia. Kalau tidak ada key sama sekali, AI features disabled gracefully — tool tetap fully functional tanpa AI.

---

## 4. Architecture & Stack

```
CLI (Python / Typer)
    │
    ├── Scanner (Python AST — ast module, built-in)
    │       └── Output: graph data JSON
    │
    ├── Risk Analyzer (pure static analysis, no AI)
    │       └── Input: graph data JSON
    │       └── Output: risk flags per function
    │
    ├── Server (FastAPI — serve frontend + API endpoints)
    │       └── GET /api/graph  → return graph JSON
    │       └── POST /api/ai/summary → trigger AI call
    │
    └── Frontend (Vanilla JS + D3.js Canvas renderer)
            └── Render interactive graph
            └── Side panel for drill down
            └── AI summary on demand
```

### Stack decisions

- **Python AST (built-in):** Zero external dependency untuk core parsing. Deterministic, reliable.
- **FastAPI:** Lightweight, async, serve static files + API dalam satu process.
- **D3.js + Canvas2D:** Full control visual. Canvas renderer (bukan SVG) — keputusan final dari architect review untuk support 2000+ nodes.
- **Vanilla JS (no React, no build step):** Constraint dari distribusi PyPI. `pip install codemap` harus langsung jalan tanpa Node.js dependency.
- **Uvicorn hardcoded ke `host="127.0.0.1"`:** Keputusan security — tidak boleh bind ke 0.0.0.0.

### AST Parser — Hybrid Approach (dari Architect Review)

```
Layer 1: AST static analysis     →  80% cases (import, class, function, decorator)
Layer 2: Runtime import probe    →  metaclass, conditional import
Layer 3: C extension scanner     →  deteksi .so/.pyd, fallback ke warning
Layer 4: Type annotation resolver →  typing.get_type_hints() + string eval
```

Setiap layer adalah enhancement — Layer 1 wajib di Phase 1, Layer 2-4 bisa Phase berikutnya.

---

## 5. File Structure (Final)

```
codemap/
├── codemap/
│   ├── __init__.py                 # __version__ = "0.1.0"
│   ├── cli.py                      # Entry point — Typer CLI
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── ast_parser.py           # Core AST traversal + safe_parse()
│   │   ├── resolver.py             # Resolve relative imports → absolute paths
│   │   ├── risk_analyzer.py        # Static risk detection
│   │   └── graph_builder.py        # Assemble + sanitize final graph JSON
│   ├── server/
│   │   ├── __init__.py
│   │   └── app.py                  # FastAPI — StaticFiles + /api routes + security middleware
│   └── ai/
│       ├── __init__.py
│       ├── provider.py             # Abstraction: Anthropic / OpenAI
│       └── cache.py                # .codemap/cache.json read/write + invalidation
│
├── frontend/
│   ├── index.html                  # App shell
│   ├── style.css                   # Design tokens + all component styles
│   ├── graph.js                    # D3 force simulation + Canvas2D renderer
│   ├── panel.js                    # Side panel — open/close, expand/collapse
│   ├── filter.js                   # Filter state (high risk, dead code)
│   ├── search.js                   # Cmd+K search overlay
│   └── toast.js                    # Toast notification queue
│
├── tests/
│   ├── fixtures/                   # Sample .py files — defined by Testing Agent
│   │   ├── simple.py               # Basic function + import
│   │   ├── circular_a.py           # Circular import pair
│   │   ├── circular_b.py
│   │   ├── dynamic_import.py       # importlib.import_module()
│   │   ├── star_import.py          # from X import *
│   │   ├── conditional_import.py   # try/except import
│   │   ├── nested_functions.py     # Inner function patterns
│   │   ├── decorators.py           # @property, @classmethod, @staticmethod
│   │   ├── none_return.py          # None return unchecked
│   │   ├── dead_code.py            # Functions with zero callers
│   │   ├── type_checking.py        # TYPE_CHECKING pattern
│   │   └── large_file.py           # >1MB guard test
│   ├── test_ast_parser.py
│   ├── test_resolver.py
│   ├── test_risk_analyzer.py
│   ├── test_graph_builder.py
│   └── test_api.py
│
├── .github/
│   └── workflows/
│       ├── test.yml                # CI — run tests on push/PR
│       └── publish.yml             # PyPI publish on tag v* (pinned SHA)
│
├── BLUEPRINT.md                    # ← ini (source of truth)
├── SECURITY.md                     # Threat model + vuln reporting (Security Agent)
├── CONTRIBUTING.md                 # Dev setup + contribution guide
├── README.md
├── pyproject.toml                  # Hatchling build + frontend force-include
├── LICENSE                         # MIT
└── .gitignore                      # dist/ *.egg-info/ .codemap/ .venv/
```

**Yang di-reject / out of scope:**
- `minimap.js` — ditolak, bukan MVP
- React/Vite — tidak ada build step
- `__pycache__/` — masuk .gitignore

---

## 6. CLI Interface

```bash
# Basic
codemap .
codemap ./src

# Options
codemap ./src --port 8080
codemap ./src --exclude tests/ migrations/ __pycache__/
codemap ./src --no-browser
codemap ./src --no-cache
codemap ./src --ai-provider anthropic
codemap ./src --ai-provider openai
codemap --version
```

### Terminal output

```
codemap v0.1.0

  Scanning ./src...
  ├── Found 12 files
  ├── Found 47 functions
  ├── Found 89 import relationships
  └── Risk analysis complete: 3 high, 5 medium, 2 low

  Server running at http://localhost:8765
  Opening browser...

  Press Ctrl+C to stop
```

### Error output di terminal

```
# Port conflict
  ✗ Port 8765 already in use. Try: codemap . --port 8766

# No permission
  ✗ Cannot read directory ./src — permission denied

# No Python files
  ✗ No .py files found in ./src
```

---

## 7. Data Contract (Graph JSON Schema)

Kontrak antara Python scanner dan D3 frontend. **Jangan ubah shape ini tanpa update keduanya.**

**Security note:** `constants[].value` di-sanitize sebelum masuk JSON — lihat Section 11 (Security).

```json
{
  "meta": {
    "root": "./src",
    "scanned_at": "2026-06-27T10:00:00",
    "total_files": 12,
    "total_functions": 47,
    "total_edges": 89,
    "has_warnings": true
  },
  "nodes": [
    {
      "id": "services/user_service.py",
      "type": "file",
      "path": "services/user_service.py",
      "risk_level": "yellow",
      "risk_summary": "2 high, 1 medium",
      "functions": [
        {
          "name": "get_user",
          "type": "function",
          "params": [
            { "name": "user_id", "annotation": "int" }
          ],
          "returns": "User | None",
          "line_start": 12,
          "line_end": 28,
          "criticality": "high",
          "callers": [
            "controllers/user_controller.py",
            "controllers/admin_controller.py"
          ],
          "callees": [
            { "name": "get_session", "resolved_file": "db.py" },
            { "name": "User.query.filter", "resolved_file": "models/user.py" }
          ],
          "decorators": [],
          "is_private": false,
          "is_dead_code": false,
          "risks": [
            {
              "type": "none_return_unchecked",
              "severity": "high",
              "detail": "2 callers tidak handle None return",
              "affected_files": [
                "controllers/user_controller.py",
                "controllers/admin_controller.py"
              ]
            }
          ],
          "ai_summary": null
        }
      ],
      "classes": [
        {
          "name": "UserService",
          "line_start": 70,
          "line_end": 120,
          "methods": ["get_user", "create_user"],
          "is_dataclass": false
        }
      ],
      "imports": [
        {
          "from": "models.user",
          "names": ["User", "UserSchema"],
          "resolved_path": "models/user.py",
          "is_dynamic": false,
          "is_star": false,
          "is_conditional": false
        }
      ],
      "constants": [
        {
          "name": "MAX_RETRY",
          "value": "3",
          "line": 8
        },
        {
          "name": "DB_PASSWORD",
          "value": "[REDACTED]",
          "line": 12
        }
      ],
      "has_all_definition": false,
      "exported_names": ["get_user", "create_user"],
      "file_modified_at": "2026-06-27T09:30:00"
    }
  ],
  "edges": [
    {
      "source": "main.py",
      "target": "services/user_service.py",
      "type": "imports",
      "weight": 2,
      "imported_names": ["get_user", "create_user"]
    }
  ],
  "warnings": [
    {
      "type": "dynamic_import",
      "file": "utils/loader.py",
      "detail": "importlib.import_module() detected — connection tidak bisa di-resolve",
      "line": 23
    },
    {
      "type": "star_import",
      "file": "main.py",
      "detail": "from utils import * — exported names unknown",
      "line": 5
    },
    {
      "type": "circular_import",
      "files": ["models/user.py", "services/user_service.py"],
      "detail": "Top-level circular import detected"
    },
    {
      "type": "scan_inconsistency",
      "detail": "3 files modified during scan — results may be inaccurate",
      "affected_files": ["main.py", "config.py", "db.py"]
    }
  ]
}
```

**Removed dari schema:** `real_path` (absolute path) — dihapus per security review M-03. Path yang tersimpan hanya relative terhadap scan root. Absolute path hanya di-compute in-memory saat "open in editor" dipanggil.

---

## 8. UX Flow (Frontend)

### Design System — Anthropic-Adapted Dark

```css
/* Base colors — warm dark, bukan cold */
--bg-base:      oklch(10% 0.008 75);
--bg-surface:   oklch(14% 0.008 75);
--bg-elevated:  oklch(18% 0.008 75);
--bg-border:    oklch(24% 0.008 75);

/* Text */
--ink-primary:   oklch(94% 0.006 75);
--ink-secondary: oklch(65% 0.008 75);
--ink-muted:     oklch(42% 0.006 75);

/* Accent */
--amber:        oklch(76% 0.15 75);   /* risk warn + UI accent */
--ai-purple:    oklch(68% 0.18 300);  /* AI features only */

/* Risk */
--risk-clean:   oklch(52% 0.02 250);
--risk-warn:    oklch(76% 0.15 75);
--risk-high:    oklch(58% 0.22 25);
```

Font: **Sora** (UI) + **JetBrains Mono** (code/paths). Canvas renderer pakai `--risk-*` colors sebagai ring/stroke pada node, bukan solid fill.

### Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  TOP BAR 48px — [◇ codemap] [./src] · 12 files 47 fns [filters] │
├──────────────────────────────────────────────────────────────────┤
│  ⚠ WARNING BANNER (amber, collapsible, conditional)              │
├───────────────────────────────────────┬──────────────────────────┤
│                                       │                          │
│         GRAPH CANVAS                  │   SIDE PANEL 320px       │
│         D3 + Canvas2D                 │   slide-in               │
│         flex: 1                       │   warm dark              │
│                                       │                          │
│  [edge legend]         [zoom% reset]  │                          │
└───────────────────────────────────────┴──────────────────────────┘
```

### Level 0 — Graph Overview

- Node = file, rendered sebagai circle dengan **ring (stroke)** bukan solid fill
- Ring color: abu (clean) / amber (warning) / merah (high risk)
- Ring thickness + node radius scale dengan degree (jumlah connections)
- High risk node: subtle glow merah
- Label: hanya muncul saat hover (tooltip card)
- Zoom + pan: D3 zoom behavior

### Level 1 — File Panel (klik node)

- Side panel slide in dari kanan, 220ms ease
- Graph **tetap visible** — panel tidak replace canvas
- Panel content:
  - Filename (Sora 700) + relative path (mono)
  - Badge row: risk counts + function count
  - Function list (accordion, collapsed by default)
  - Constants section (collapsed)
  - Imports section (collapsed)

### Level 2 — Function Detail (klik fungsi)

- Expand inline di panel
- Parameters + return type
- Line range
- Called by list (klikable → pan graph ke node itu)
- Calls list
- Decorators
- Risk flags (cards dengan severity color)
- `[✦ Generate AI Insight]` — disabled kalau no API key

### Level 3 — AI Insight

- Loading: spinner + "Analyzing..."
- Result: structured card (Role / Importance / Hidden assumption)
- Cached — invalidate kalau file modified

### Graph Interaction

- Hover node → highlight connected edges, dim semua lain
- Klik node → panel open, node pinned highlighted
- Hover fungsi di panel → highlight edge di graph
- Escape → close panel, reset highlight
- Cmd+K → search overlay
- F → fit graph to viewport

### Error States

Error states dibagi tiga layer: **CLI/terminal** (sebelum server up), **browser/frontend** (setelah server up), dan **dalam-panel** (saat interaksi AI). Setiap state punya: apa yang user lihat, copy teks exact, dan recovery action.

---

#### E1 — Scan Errors (CLI layer, sebelum browser terbuka)

---

**E1.1 — Port sudah dipakai**

Trigger: `OSError: [Errno 98] Address already in use`

Terminal output:
```
codemap v0.1.0

  ✗ Port 8765 is already in use.

  Try:
    codemap . --port 8766
    codemap . --port 8080

  Or find what's using it:
    lsof -i :8765       (macOS / Linux)
    netstat -ano | findstr :8765   (Windows)
```

Recovery: User re-run dengan `--port` berbeda. Tidak ada auto-retry ke port lain — ini keputusan user, bukan tool.

**Tidak boleh**: Auto-bind ke port random tanpa memberitahu user. User perlu tau URL yang harus dibuka.

---

**E1.2 — Directory tidak ada**

Trigger: `FileNotFoundError` atau path argument tidak resolve.

Terminal output:
```
codemap v0.1.0

  ✗ Directory not found: ./src/nonexistent

  Make sure the path exists and try again.
```

Recovery: Tidak ada — user harus fix path. Exit code 1.

---

**E1.3 — Permission denied**

Trigger: `PermissionError` saat `os.listdir()` atau `open()` file.

Terminal output:
```
codemap v0.1.0

  ✗ Cannot read directory ./private — permission denied.

  Try running with appropriate permissions, or scan
  a directory you have read access to.
```

Recovery: Tidak ada automated — user harus fix permission. Exit code 1.

---

**E1.4 — Zero .py files found**

Trigger: Scan selesai, `total_files == 0`.

Terminal output:
```
codemap v0.1.0

  Scanning ./node_modules...
  └── No Python files found.

  ✗ Nothing to visualize. Make sure you're pointing
    to a directory that contains .py files.

  Example:
    codemap ./src
    codemap ./app
```

Recovery: Tidak ada — exit tanpa membuka browser. Exit code 0 (bukan error, hanya tidak ada data). Jangan exit code 1 karena bukan crash.

---

**E1.5 — File corrupt / SyntaxError saat parse**

Trigger: `SyntaxError` di `safe_parse()`. Satu atau beberapa file tidak bisa di-parse.

**Ini bukan fatal error** — tool tetap jalan dengan file yang berhasil di-parse.

Terminal output (partial failures):
```
codemap v0.1.0

  Scanning ./src...
  ├── Found 11 files (1 skipped)
  ├── Found 42 functions
  ├── Found 76 import relationships
  └── Risk analysis complete: 2 high, 3 medium

  ⚠ 1 file skipped due to parse errors:
    • utils/broken.py — SyntaxError on line 47

  Server running at http://localhost:8765
  Opening browser...

  Press Ctrl+C to stop
```

Di browser — Warning Banner:
```
⚠  1 file could not be parsed  [show details ▾]
```

Expanded:
```
syntax_error   utils/broken.py:47   Invalid syntax — file excluded from graph
```

Recovery: User perlu fix file tersebut, lalu re-run `codemap`. Tidak ada auto-retry.

---

**E1.6 — File terlalu besar (>1MB)**

Trigger: `safe_parse()` size guard. Treated sama seperti SyntaxError — skip + warning.

Terminal output (sama pattern dengan E1.5):
```
  ⚠ 1 file skipped:
    • generated/migrations.py — file too large (4.2MB, limit 1MB)
```

Di browser — Warning Banner entry:
```
file_too_large   generated/migrations.py   4.2MB exceeds 1MB limit — excluded
```

---

**E1.7 — Scan crash di tengah jalan (partial results)**

Trigger: Unexpected exception di scanner loop — bukan per-file SyntaxError, tapi crash di level scanner itu sendiri.

Ini adalah **unexpected error**. Bedain dari E1.5 yang partial failure by design.

Terminal output:
```
codemap v0.1.0

  Scanning ./src...
  ├── Found 7 files
  ├── Analyzing...

  ✗ Scan crashed unexpectedly.

  Partial results (7 of ~12 estimated files) are available.
  The graph may be incomplete.

  Server running at http://localhost:8765 (partial data)
  Opening browser...

  Please report this at: github.com/Maouv/CodeMAP/issues
  Include: codemap --version output + error below

  Error: [exception type and message — sanitized, no paths]
```

Di browser — Warning Banner (merah, bukan amber — ini lebih serius dari warning biasa):
```
🔴  Scan incomplete — partial results only  [show details ▾]
```

Expanded:
```
scan_crash   Scanner stopped unexpectedly after processing 7 files.
             Graph may be missing nodes and edges.
             Re-run codemap to attempt a full scan.
```

Graph tetap di-render dengan data yang ada. User tidak di-block.

Recovery action di banner: `[Re-run scan]` button → trigger reload halaman (user harus manual re-run dari terminal, button ini hanya hint).

---

#### E2 — AI Error States (dalam-panel, saat user klik [Generate AI Insight])

Semua AI errors muncul di dalam AI result area di side panel. Tidak ada modal, tidak ada redirect.

---

**E2.1 — API key tidak ada (graceful disable)**

Trigger: `get_provider()` returns `None` — tidak ada env var.

Button state: disabled, greyed out.

```
[✦ Generate AI Insight]   ← disabled, opacity 0.35
```

Hover tooltip pada button:
```
Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable AI features.
export ANTHROPIC_API_KEY=sk-ant-...
```

Tidak ada error card — ini adalah expected state, bukan error.

---

**E2.2 — API key invalid (401)**

Trigger: Provider returns 401 / `AuthenticationError`.

AI result area:
```
┌─────────────────────────────────────────────────┐
│  ✦ AI Insight — Authentication Failed            │
│  ─────────────────────────────────────────────── │
│  Your API key was rejected by [anthropic/openai]. │
│                                                  │
│  Check that your key is valid and active:        │
│  export ANTHROPIC_API_KEY=sk-ant-...             │
│                                                  │
│  Then restart codemap.                           │
└─────────────────────────────────────────────────┘
```

Button kembali ke default state — user bisa retry setelah fix key dan restart.

**Penting**: Jangan tampilkan key fragment di error message. Exception dari provider di-sanitize sebelum ditampilkan.

---

**E2.3 — Rate limited (429)**

Trigger: Provider returns 429 / `RateLimitError`.

AI result area:
```
┌─────────────────────────────────────────────────┐
│  ✦ AI Insight — Rate Limited                     │
│  ─────────────────────────────────────────────── │
│  Too many requests to [anthropic/openai].        │
│  Please wait a moment before trying again.       │
│                                                  │
│                          [↻ Retry in 30s]        │
└─────────────────────────────────────────────────┘
```

Retry button: countdown timer 30s, lalu aktif. Auto-retry tidak dilakukan — user yang trigger.

Kalau provider return `Retry-After` header → gunakan nilai itu untuk countdown, bukan hardcode 30s.

---

**E2.4 — Request timeout**

Trigger: AI call tidak response dalam 30 detik (configurable via `AI_TIMEOUT` env, default 30s).

AI result area:
```
┌─────────────────────────────────────────────────┐
│  ✦ AI Insight — Request Timed Out               │
│  ─────────────────────────────────────────────── │
│  The AI provider took too long to respond.       │
│                                                  │
│                               [↻ Try Again]      │
└─────────────────────────────────────────────────┘
```

Recovery: Retry button, immediate. Tidak ada countdown.

---

**E2.5 — Network offline / connection refused**

Trigger: `httpx.ConnectError`, `httpx.NetworkError`, atau DNS resolution failure.

AI result area:
```
┌─────────────────────────────────────────────────┐
│  ✦ AI Insight — No Connection                   │
│  ─────────────────────────────────────────────── │
│  Could not reach [anthropic/openai].             │
│  Check your internet connection and try again.   │
│                                                  │
│                               [↻ Try Again]      │
└─────────────────────────────────────────────────┘
```

---

**E2.6 — Provider server error (5xx)**

Trigger: Provider returns 500/502/503.

AI result area:
```
┌─────────────────────────────────────────────────┐
│  ✦ AI Insight — Provider Error                  │
│  ─────────────────────────────────────────────── │
│  [anthropic/openai] returned a server error.     │
│  This is likely temporary.                       │
│                                                  │
│                               [↻ Try Again]      │
└─────────────────────────────────────────────────┘
```

---

**E2.7 — Unexpected AI response format**

Trigger: Provider response tidak bisa di-parse menjadi `{role, importance, hidden_assumption}` dict.

AI result area:
```
┌─────────────────────────────────────────────────┐
│  ✦ AI Insight — Unexpected Response              │
│  ─────────────────────────────────────────────── │
│  The AI returned an unrecognized format.         │
│  Raw response:                                   │
│  [truncated response text, max 200 chars]        │
│                                                  │
│  Please report this at github.com/Maouv/CodeMAP  │
└─────────────────────────────────────────────────┘
```

Ini developer-facing error. Tampilkan raw response (truncated) untuk debugging.

---

#### E3 — Runtime Error States (browser layer)

---

**E3.1 — Graph terlalu besar (>2000 nodes)**

Trigger: `meta.total_files > 2000` dalam graph JSON response.

**Ini bukan hard error** — graph masih di-render. Ini adalah performance warning.

Warning Banner (amber):
```
⚠  Large graph: 2,847 nodes detected  [show details ▾]
```

Expanded:
```
performance_warning   Graph with 2,847 nodes may render slowly on some machines.
                      
                      Tips:
                      • Use filters (High Risk / Dead Code) to focus view
                      • Scan a subdirectory instead: codemap ./src/core
                      • Use Cmd+K to navigate directly to specific files
```

Graph tetap di-render. Tidak ada hard limit — ini hanya informasi.

**Di terminal juga muncul** (setelah scan selesai, sebelum server start):
```
  ⚠ Large codebase: 2,847 files found.
    Browser rendering may be slow.
    Consider scanning a subdirectory: codemap ./src/core
```

---

**E3.2 — Cache corrupt / unreadable**

Trigger: `.codemap/cache.json` ada tapi tidak bisa di-parse (`json.JSONDecodeError`, `PermissionError`, atau schema version mismatch).

**Ini bukan fatal** — tool berjalan normal, cache di-reset.

Terminal output (saat startup):
```
  ⚠ Cache at .codemap/cache.json is corrupt — resetting.
    Previous AI insights will need to be regenerated.
```

Tidak ada user-facing error di browser untuk ini. AI Insight button tetap available — hanya cache hilang.

Behavior di `cache.py`:
```python
def load_cache() -> dict:
    try:
        data = json.loads(cache_path.read_text())
        if data.get("version") != CACHE_VERSION:
            raise ValueError("version mismatch")
        return data
    except (json.JSONDecodeError, KeyError, ValueError, PermissionError):
        logger.warning("Cache corrupt — resetting")
        cache_path.write_text(json.dumps({"version": CACHE_VERSION, "entries": {}}))
        cache_path.chmod(0o600)
        return {"version": CACHE_VERSION, "entries": {}}
```

---

**E3.3 — `/api/graph` gagal (server error)**

Trigger: Frontend fetch ke `GET /api/graph` return non-200, atau network error ke localhost.

Ini seharusnya sangat jarang — server dan frontend dalam process yang sama.

Browser menampilkan full-screen error state (replace loading state):

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│                      ◇ codemap                           │
│                                                          │
│               Failed to load graph data                  │
│                                                          │
│  The local server returned an error.                     │
│                                                          │
│  Try stopping and restarting codemap:                    │
│  Ctrl+C, then: codemap .                                 │
│                                                          │
│  If this keeps happening, please report at:              │
│  github.com/Maouv/CodeMAP/issues                         │
│                                                          │
│                    [↻ Retry]                             │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

Retry button: re-fetch `/api/graph` setelah 2 detik delay.

---

**E3.4 — Graph JSON malformed (schema mismatch)**

Trigger: Server return 200 tapi JSON tidak conform ke expected schema (missing `nodes`, `edges`, `meta`).

Ini adalah developer-facing error — hanya muncul kalau ada bug di backend.

Browser:
```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│                      ◇ codemap                           │
│                                                          │
│              Unexpected graph data format                │
│                                                          │
│  The server returned data in an unrecognized format.     │
│  This is likely a version mismatch.                      │
│                                                          │
│  Make sure you're running the latest version:            │
│  pip install --upgrade codemap                           │
│                                                          │
│  Please report at: github.com/Maouv/CodeMAP/issues       │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

#### Error State Visual Spec (Frontend)

**Error card dalam panel** (AI errors E2.x):
```css
.error-card {
  margin-top: var(--space-3);
  padding: var(--space-4);
  background: oklch(58% 0.22 25 / 0.06);
  border: 1px solid oklch(58% 0.22 25 / 0.25);
  border-radius: var(--radius-md);
}

.error-card-title {
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--risk-high);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-2);
}

.error-card-body {
  font-size: var(--text-sm);
  color: var(--ink-secondary);
  line-height: 1.6;
}

.error-card-code {
  font-family: var(--font-code);
  font-size: var(--text-xs);
  color: var(--ink-muted);
  margin-top: var(--space-2);
}

.error-retry-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: var(--space-3);
  padding: 6px 12px;
  border-radius: var(--radius-full);
  background: var(--bg-elevated);
  border: 1px solid var(--bg-border);
  color: var(--ink-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  float: right;
  transition: all 120ms ease-out;
}

.error-retry-btn:hover {
  background: var(--bg-border);
  color: var(--ink-primary);
}
```

**Full-screen error state** (E3.3, E3.4):
```css
.error-screen {
  /* sama dengan .empty-state layout */
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: var(--space-10);
  text-align: center;
  gap: var(--space-4);
}

.error-screen-icon {
  width: 40px;
  height: 40px;
  color: var(--risk-high);
  opacity: 0.6;
}

.error-screen-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--ink-primary);
}

.error-screen-body {
  font-size: var(--text-sm);
  color: var(--ink-secondary);
  line-height: 1.7;
  max-width: 360px;
}

.error-screen-cmd {
  font-family: var(--font-code);
  font-size: var(--text-sm);
  color: var(--ink-secondary);
  background: var(--bg-surface);
  border: 1px solid var(--bg-border);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-4);
}
```

---

#### Error State Summary Table

| ID | Layer | Trigger | Fatal? | Recovery |
|----|-------|---------|--------|----------|
| E1.1 | CLI | Port in use | Yes | `--port` flag |
| E1.2 | CLI | Directory not found | Yes | Fix path |
| E1.3 | CLI | Permission denied | Yes | Fix permissions |
| E1.4 | CLI | Zero .py files | Soft (exit 0) | Scan different dir |
| E1.5 | CLI+Browser | SyntaxError per file | No (partial) | Fix file, re-run |
| E1.6 | CLI+Browser | File >1MB | No (partial) | Split file or ignore |
| E1.7 | CLI+Browser | Scan crash | No (partial) | Re-run, report bug |
| E2.1 | Panel | No API key | No (disabled) | Set env var, restart |
| E2.2 | Panel | API key invalid (401) | No | Fix key, restart |
| E2.3 | Panel | Rate limited (429) | No | Wait + retry |
| E2.4 | Panel | AI timeout | No | Retry |
| E2.5 | Panel | Network offline | No | Check connection, retry |
| E2.6 | Panel | Provider 5xx | No | Retry |
| E2.7 | Panel | Bad response format | No | Report bug |
| E3.1 | Browser | >2000 nodes | No (warning) | Filter / subdirectory |
| E3.2 | Startup | Cache corrupt | No (auto-reset) | None needed |
| E3.3 | Browser | /api/graph 500 | Yes | Restart codemap |
| E3.4 | Browser | JSON schema mismatch | Yes | Upgrade codemap |

---

### Frontend State Management

**Pattern: satu shared state object + native `EventTarget`** (`frontend/store.js`, zero dependency, no build step). State terpisah dari bus karena `graph.js` perlu *baca* state sinkron saat render, dan komponen yang mount belakangan (panel setelah klik) butuh current state — bukan replay event.

```js
// store.js — single source of truth + event bus
const state = {
  selectedNodeId: null,
  hoveredNodeId: null,
  hoveredEdge: null,       // {from, to} — panel→graph cross-highlight
  filters: { highRiskOnly: false, deadCode: false },
  selectedFunction: null,  // {nodeId, fnName}
  searchOpen: false,
};
const bus = new EventTarget();
function setState(patch, event) {       // mutator tunggal
  Object.assign(state, patch);
  bus.dispatchEvent(new CustomEvent(event, { detail: { ...state, patch } }));
}
function resetSelection() { /* clear selected/hovered/fn → 'reset' */ }
window.Store = { state, bus, setState, resetSelection };  // no bundler → global
```

`index.html`: load `store.js` sebelum graph/panel/filter/search.

**Channels:** `node:select`, `node:hover`, `edge:hover`, `filters`, `pan`, `reset`, `search:open`. Tiap file subscribe via `Store.bus.addEventListener(...)`, dispatch via `Store.setState(patch, channel)`.

**Ditolak:** custom pub/sub class (reinvent EventTarget), `document.dispatchEvent` (collision native event), Proxy reactive (emit tersembunyi → debug susah), Redux/Zustand (dependency + build step, langgar constraint PyPI).

**Skipped:** immutability, middleware, devtools → tambah kalau state >10 keys atau ada race condition async.

---

## 9. Risk Flags Specification

Pure static analysis — no AI required.

| Flag Type | Severity | Detection Logic |
|-----------|----------|----------------|
| `none_return_unchecked` | high | Return `X \| None`, caller tidak check None |
| `uncaught_exception` | medium | Call ke fungsi yang bisa raise, tidak ada try/except |
| `dead_code` | medium | Fungsi defined, zero callers di seluruh codebase |
| `star_import` | medium | `from X import *` |
| `circular_import_toplevel` | high | Top-level circular import |
| `missing_type_annotation` | low | Public function tanpa type hints |
| `unused_parameter` | low | Parameter tidak dipakai dalam body |

### Conservative approach

Hanya flag yang obvious. False positive lebih berbahaya dari false negative.

Jangan flag `none_return_unchecked` kalau caller menggunakan:
- `if result:`
- `if result is not None:`
- `assert result is not None`
- `result or default_value`

Jangan flag circular import kalau lazy import (import di dalam function body).

---

## 10. AI Layer Specification

### When AI is called

- **Never** saat initial scan
- **Only** saat user explicitly klik `[Generate AI Insight]`
- Cache result, invalidate kalau `file_modified_at` berubah

### Cache structure

```
.codemap/
└── cache.json        ← permissions 600, masuk .gitignore
```

```json
{
  "version": "1",
  "entries": {
    "services/user_service.py::get_user": {
      "generated_at": "2026-06-27T10:00:00",
      "file_modified_at": "2026-06-27T09:30:00",
      "provider": "anthropic",
      "summary": {
        "role": "Primary data access point untuk user entity",
        "importance": "8 downstream functions assume return tidak None",
        "hidden_assumption": "Expects DB connection sudah initialized"
      }
    }
  }
}
```

### Secret scrubbing sebelum kirim ke AI

```python
SENSITIVE_PATTERNS = [
    r'(?i)(password|passwd|pwd)\s*=\s*["\']?.+',
    r'(?i)(api_key|apikey|secret|token)\s*=\s*["\']?.+',
    r'(?i)(auth|credential)\s*=\s*["\']?.+',
]

def scrub_secrets(source: str) -> str:
    for pattern in SENSITIVE_PATTERNS:
        source = re.sub(pattern, lambda m: m.group().split('=')[0] + '= "[REDACTED]"', source)
    return source
```

**User harus lihat consent notice** pertama kali AI dipanggil: *"File content akan dikirim ke [provider]. Pastikan tidak ada credentials hardcoded."*

### Provider abstraction

```python
class AIProvider:
    def generate_summary(self, file_content: str, function_context: dict) -> dict:
        raise NotImplementedError

class AnthropicProvider(AIProvider):
    model = "claude-haiku-4-5-20251001"

class OpenAIProvider(AIProvider):
    model = "gpt-4o-mini"

def get_provider() -> AIProvider | None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return None
```

**Jangan store API key sebagai instance attribute.** Baca dari env setiap call. Sanitize exception sebelum log — jangan log error message raw dari provider karena bisa berisi key fragment.

---

## 11. Security Implementation

*Source: Security Review (codemap-security-review.md)*

### Wajib sebelum baris kode pertama

```python
# app.py — hardcode 127.0.0.1, TIDAK 0.0.0.0
uvicorn.run(app, host="127.0.0.1", port=port)
```

### Wajib di Phase 1 saat server dibuat

```python
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{PORT}",
        f"http://127.0.0.1:{PORT}",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Origin validation middleware
@app.middleware("http")
async def enforce_origin(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin", "")
        allowed = (f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}")
        if origin and not any(origin.startswith(a) for a in allowed):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
    return await call_next(request)

# DNS rebinding protection
@app.middleware("http")
async def validate_host(request: Request, call_next):
    host = request.headers.get("host", "")
    if host not in (f"localhost:{PORT}", f"127.0.0.1:{PORT}"):
        return JSONResponse({"error": "Invalid Host"}, status_code=400)
    return await call_next(request)
```

### Sanitize constants sebelum masuk graph JSON

File: `codemap/scanner/sanitize.py`

```python
import re

# Name-based: jika nama variabel mengandung keyword ini → redact
SENSITIVE_NAME_KEYWORDS = {
    "password", "passwd", "pwd",
    "secret", "token",
    "api_key", "apikey", "api_secret",
    "auth", "credential", "credentials",
    "private_key", "privkey",
    "access_key", "access_secret",
    "client_secret", "client_id",
    "signing_key", "encryption_key",
    "webhook_secret", "jwt_secret",
    "db_pass", "database_pass",
}

# Value-based: tangkap pola credential umum terlepas dari nama variabel
SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}"),                    # Anthropic API key
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),                            # OpenAI API key
    re.compile(r"(?i)(postgres|mysql|mongodb|redis)://[^\s]+@"),   # DB connection string
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9\-_.]{20,}"),             # Bearer token
    re.compile(r"(?i)basic\s+[a-zA-Z0-9+/=]{20,}"),               # Basic auth
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),                            # GitHub PAT
    re.compile(r"whsec_[a-zA-Z0-9]{32,}"),                         # Stripe webhook secret
    re.compile(r"xoxb-[0-9]+-[a-zA-Z0-9\-]+"),                    # Slack bot token
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),         # PEM private key
]


def sanitize_constant_value(name: str, value: str) -> str:
    """
    Returns '[REDACTED]' jika nama atau nilai konstanta terdeteksi sebagai credential.
    Dipanggil di graph_builder.py sebelum constants[] dipopulate.

    >>> sanitize_constant_value("MAX_RETRY", "3")
    '3'
    >>> sanitize_constant_value("DB_PASSWORD", "hunter2")
    '[REDACTED]'
    >>> sanitize_constant_value("API_URL", "sk-ant-abc123xyz...")
    '[REDACTED]'
    """
    name_lower = name.lower()

    if any(keyword in name_lower for keyword in SENSITIVE_NAME_KEYWORDS):
        return "[REDACTED]"

    for pattern in SENSITIVE_VALUE_PATTERNS:
        if pattern.search(value):
            return "[REDACTED]"

    return value
```

**Known limitation:** Nama variabel tidak konvensional (misal `PROD_DB_PASS_V2`, `key_for_stripe`) mungkin tidak terdeteksi lewat name-based check. Value-based patterns meng-cover kasus ini untuk format credential yang dikenal.

**Dipanggil di:** `graph_builder.py`

```python
from codemap.scanner.sanitize import sanitize_constant_value

# Saat populate constants[]:
constants.append({
    "name": const_name,
    "value": sanitize_constant_value(const_name, const_value),
    "line": node.lineno,
})
```

### AST parser safety

```python
def safe_parse(source: str, filename: str) -> ast.AST | None:
    if len(source.encode()) > 1_000_000:  # 1MB guard
        logger.warning(f"Skip {filename}: file too large")
        return None
    try:
        with parse_timeout(5):  # Unix: SIGALRM, Windows: multiprocessing
            return ast.parse(source, filename=filename)
    except (TimeoutError, SyntaxError, MemoryError) as e:
        logger.warning(f"Skip {filename}: {type(e).__name__}")
        return None
```

### Cache file permissions

```python
# Set permissions 600 saat create cache
cache_path.touch(mode=0o600)
```

### Symlink depth limit

```python
MAX_SYMLINK_DEPTH = 5

def resolve_safe(path: Path, depth: int = 0) -> Path | None:
    if depth > MAX_SYMLINK_DEPTH:
        return None
    if path.is_symlink():
        return resolve_safe(path.resolve(), depth + 1)
    return path
```

### Risk matrix summary

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| C-01 | CRITICAL | constants[].value expose credentials | → `sanitize_constant_value()` |
| C-02 | CRITICAL | Source code ke AI tanpa scrubbing | → `scrub_secrets()` + consent |
| H-01 | HIGH | Uvicorn bind 0.0.0.0 | → hardcode `127.0.0.1` |
| H-02 | HIGH | Tidak ada CORS + Origin validation | → middleware Phase 1 |
| H-03 | HIGH | Cache bisa ter-commit ke Git | → `.gitignore` + `chmod 600` |
| M-01 | MEDIUM | API key leak via exception | → sanitize exception log |
| M-02 | MEDIUM | AST DoS via deeply nested code | → `safe_parse()` timeout |
| M-03 | MEDIUM | `real_path` expose absolute path | → removed dari schema |
| L-01 | LOW | CI/CD tanpa tag protection | → GitHub Environments + pinned SHA |

---

## 12. Packaging (pyproject.toml)

*Source: Python Packaging Review (python-packaging-reviewer.md)*

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "codemap"
version = "0.1.0"
description = "Interactive visual dependency graph for Python codebases"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
keywords = ["codebase", "visualization", "ast", "dependency-graph", "cli"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Console",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
]

dependencies = [
  "typer>=0.12.0",
  "fastapi>=0.111.0",
  "uvicorn[standard]>=0.30.0",
]

[project.optional-dependencies]
anthropic = ["anthropic>=0.28.0"]
openai    = ["openai>=1.30.0"]
ai        = ["anthropic>=0.28.0", "openai>=1.30.0"]
dev = [
  "pytest>=8.0.0",
  "pytest-asyncio>=0.23.0",
  "httpx>=0.27.0",
  "ruff>=0.4.0",
  "mypy>=1.10.0",
]

[project.scripts]
codemap = "codemap.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["codemap"]

[tool.hatch.build.targets.wheel.force-include]
"frontend" = "codemap/frontend"

[tool.hatch.build.targets.sdist]
include = ["codemap/", "frontend/", "tests/", "pyproject.toml", "README.md", "LICENSE"]
```

### Verifikasi wajib setelah build

```bash
python -m build
unzip -l dist/codemap-0.1.0-py3-none-any.whl | grep frontend
# Harus muncul: codemap/frontend/index.html, graph.js, panel.js, style.css, dll
```

### Frontend path di runtime

```python
# codemap/server/app.py
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
```

---

## 13. Testing Strategy

*Source: Testing Agent. Prinsip: test yang berharga untuk solo developer, bukan angka coverage. Lazy = efisien: pakai pytest + httpx yang sudah di-dev deps (Section 12), tidak menambah dependency baru.*

### 13.1 Test Pyramid (Realistis Solo Dev)

| Layer | Ratio | Jumlah Target Phase 1 | Tools |
|-------|-------|----------------------|-------|
| **Unit** | ~75% | ~40-50 test | pytest, fixtures `.py` files |
| **Integration** | ~20% | ~10-15 test | pytest + FastAPI `TestClient` (httpx-based) |
| **End-to-end** | ~5% | 2-3 smoke test | subprocess `codemap ./tests/fixtures` |

**Kenapa berat di unit:** Core value codemap ada di scanner/parser/sanitize — logic deterministik yang gampang di-test isolated dengan fixture `.py` files kecil. Setiap edge case dari Section 14 = satu unit test, cheap dan fast.

**Kenapa tipis di e2e:** E2E butuh browser automation (Playwright/Selenium) untuk frontend Canvas — overhead besar untuk solo dev, ROI rendah karena D3 rendering bukan business logic yang berubah-ubah. Cukup smoke test "CLI run, server up, `/api/graph` returns valid schema" — sisanya manual saat dev. Frontend JS di-cover lewat manual interaction selama development, bukan automated.

**Yang TIDAK di-test:**
- Frontend JS (D3 rendering, panel UX) — manual QA, di luar Python coverage.
- Visual regression — overkill untuk Phase 1.
- Performance benchmark — baru relevan kalau ada complaint nyata.
- Real AI provider calls — selalu mock, tidak boleh hit API beneran di CI.

---

### 13.2 Fixture Files Strategy

Setiap fixture adalah `.py` file kecil (~5-30 baris) yang trigger exactly satu parser edge case. Tidak boleh kompleks — kalau fixture butuh penjelasan panjang, fixture-nya yang salah.

#### Fixtures dari Section 5

| File | Edge Case (Section 14) | Isi Minimal |
|------|-----------------------|-------------|
| `simple.py` | Happy path baseline | `import os`<br>`def hello(name: str) -> str:`<br>`    return f"hi {name}"` |
| `circular_a.py` | Top-level circular import | `from circular_b import B`<br>`class A: pass` |
| `circular_b.py` | Pair untuk circular_a | `from circular_a import A`<br>`class B: pass` |
| `dynamic_import.py` | `importlib.import_module()` warning | `import importlib`<br>`mod = importlib.import_module("os.path")` |
| `star_import.py` | `from X import *` warning | `from os import *`<br>`def use(): return getcwd()` |
| `conditional_import.py` | try/except import | `try:`<br>`    import ujson as json`<br>`except ImportError:`<br>`    import json` |
| `nested_functions.py` | Inner function tidak top-level | `def outer():`<br>`    def inner(): return 1`<br>`    return inner()` |
| `decorators.py` | `@property`, `@classmethod`, `@staticmethod` | `class C:`<br>`    @property`<br>`    def p(self): return 1`<br>`    @classmethod`<br>`    def cm(cls): return 2`<br>`    @staticmethod`<br>`    def sm(): return 3` |
| `none_return.py` | `none_return_unchecked` risk (Phase 2) | `def get_user(uid: int) -> "User | None":`<br>`    return None`<br>`def caller():`<br>`    u = get_user(1)`<br>`    return u.name  # unchecked` |
| `dead_code.py` | Function tanpa caller | `def orphan(): return 42`<br>`def used(): return orphan()  # used by no one either`<br>`# only used() referenced externally via __all__` |
| `type_checking.py` | `if TYPE_CHECKING:` pattern | `from typing import TYPE_CHECKING`<br>`if TYPE_CHECKING:`<br>`    from models import User`<br>`def f(u: "User"): pass` |
| `large_file.py` | >1MB size guard | Generated runtime di test: `"x = 1\n" * 200_000` (~1.4MB), atau commit file generator script. **Jangan commit 1MB file ke Git.** |

#### Fixtures Tambahan (cover sisa Section 14)

| File | Edge Case | Isi |
|------|-----------|-----|
| `syntax_error.py` | SyntaxError → skip + warning | `def broken(:\n    pass` (intentional invalid syntax) |
| `exec_eval.py` | exec/eval warning | `exec("x = 1")`<br>`eval("1 + 1")` |
| `latin1_encoded.py` | Non-UTF-8 encoding detection | File ditulis bytes dengan `# -*- coding: latin-1 -*-` header + char non-ASCII (`é`). Test pakai `tokenize.detect_encoding()`. |
| `relative_imports/__init__.py` + `relative_imports/sub.py` + `relative_imports/main.py` | Relative import resolution | `main.py`: `from .sub import helper` — expected resolve ke `relative_imports/sub.py` |
| `all_definition.py` | `__all__` override | `__all__ = ["public"]`<br>`def public(): pass`<br>`def _private(): pass` |
| `symlink_target.py` + symlink dibuat di test runtime | Symlink resolve + max depth | Test bikin symlink di tmpdir, bukan commit ke Git. |
| `secret_constants.py` | `sanitize_constant_value()` coverage | `MAX_RETRY = 3`<br>`DB_PASSWORD = "hunter2"`<br>`API_KEY = "sk-ant-abcdefghij1234567890xyz"`<br>`POSTGRES_URL = "postgres://user:pass@host/db"` |

**Yang TIDAK perlu fixture file:**
- C extension `.so` — di-test dengan `tmp_path` create empty `foo.so`, assert warning emitted. Tidak perlu real binary.
- Parse timeout — sulit di-trigger deterministik dengan fixture; pakai monkeypatch pada `parse_timeout` context manager.
- File modified during scan — pakai `tmp_path` + `os.utime()` runtime, bukan static fixture.

---

### 13.3 Unit Test Spec — `test_ast_parser.py`

Format: `test_<area>__<scenario>`. Setiap test ≤15 baris. Pakai `pytest.fixture` untuk path fixture base.

| Test Name | Input | Assertion |
|-----------|-------|-----------|
| `test_parse_simple__extracts_function` | `fixtures/simple.py` | `result.functions` punya 1 entry `name="hello"`, `params=[{name:"name", annotation:"str"}]`, `returns="str"` |
| `test_parse_simple__extracts_import` | `fixtures/simple.py` | `result.imports` punya 1 entry `from="os"`, `is_star=False` |
| `test_parse_star_import__flags_is_star` | `fixtures/star_import.py` | `imports[0].is_star == True`, warning emitted |
| `test_parse_dynamic_import__emits_warning` | `fixtures/dynamic_import.py` | `warnings` mengandung `{type: "dynamic_import"}`, edge tidak dibuat |
| `test_parse_conditional_import__both_branches` | `fixtures/conditional_import.py` | 2 imports extracted, keduanya `is_conditional=True` |
| `test_parse_nested_functions__inner_not_toplevel` | `fixtures/nested_functions.py` | Top-level `functions` cuma `["outer"]`, `inner` di-attach sebagai nested |
| `test_parse_decorators__detects_property` | `fixtures/decorators.py` | Method `p` punya `decorators=["property"]` |
| `test_parse_type_checking__import_not_runtime` | `fixtures/type_checking.py` | Import `User` di-flag `is_conditional=True` (TYPE_CHECKING block) |
| `test_parse_all_definition__overrides_exports` | `fixtures/all_definition.py` | `exported_names == ["public"]`, bukan `["public", "_private"]` |
| `test_parse_syntax_error__returns_none` | `fixtures/syntax_error.py` | `safe_parse()` returns `None`, warning logged |
| `test_safe_parse__large_file_skipped` | Source string `"x=1\n" * 200_000` | `safe_parse()` returns `None`, log message contains "too large" |
| `test_safe_parse__size_guard_at_boundary` | Source exactly 1_000_000 bytes | Parsed OK (boundary inclusive); 1_000_001 bytes → skipped |
| `test_safe_parse__syntax_error_returns_none` | `"def broken(:\n"` | Returns `None`, no exception bubbles up |
| `test_safe_parse__timeout_returns_none` | Monkeypatch `parse_timeout` to raise `TimeoutError` immediately | Returns `None`, log contains "TimeoutError" |
| `test_safe_parse__memory_error_returns_none` | Monkeypatch `ast.parse` to raise `MemoryError` | Returns `None`, no crash |
| `test_parse_latin1_encoded__detects_encoding` | `fixtures/latin1_encoded.py` (bytes) | Parsed OK via `tokenize.detect_encoding()`, no UnicodeDecodeError |
| `test_parse_exec_eval__emits_warning` | `fixtures/exec_eval.py` | Warning `{type: "dynamic_code"}` emitted untuk exec dan eval |

Test resolver, risk_analyzer, graph_builder, sanitize mengikuti pola yang sama — satu fixture, satu assertion fokus. Sanitize sudah punya doctest di Section 11; tambahkan `test_sanitize_constant_value.py` dengan parametrize untuk SEMUA pattern di `SENSITIVE_VALUE_PATTERNS` dan keyword di `SENSITIVE_NAME_KEYWORDS`.

---

### 13.4 Integration Test Spec — `test_api.py`

Pakai FastAPI `TestClient` (wraps httpx, sudah di dev deps). Setiap test: spin up app, hit endpoint, assert shape. Tidak boleh bind socket beneran.

```python
# Sketch pola — bukan kode lengkap
from fastapi.testclient import TestClient
from codemap.server.app import create_app

def make_client(graph_data):
    app = create_app(graph_data=graph_data, port=8765)
    return TestClient(app, base_url="http://localhost:8765")
```

| Test Name | Skenario | Assertion |
|-----------|----------|-----------|
| `test_get_graph__returns_200_with_schema` | GET `/api/graph` dengan pre-scanned fixture data | Status 200; response punya keys `meta`, `nodes`, `edges`, `warnings`; `meta.total_files > 0` |
| `test_get_graph__nodes_match_section7_schema` | Sama | Setiap node punya `id`, `type`, `path`, `risk_level`, `functions[]`; setiap function punya `name`, `params`, `returns`, `criticality` |
| `test_get_graph__sanitized_constants` | Fixture dengan `DB_PASSWORD = "hunter2"` | Response constants entry `value == "[REDACTED]"` |
| `test_security__invalid_host_header_400` | GET `/api/graph` dengan header `Host: evil.com` | Status 400, body `{"error": "Invalid Host"}` |
| `test_security__valid_host_passes` | Header `Host: localhost:8765` | Status 200 |
| `test_security__valid_127_host_passes` | Header `Host: 127.0.0.1:8765` | Status 200 |
| `test_security__post_invalid_origin_403` | POST `/api/ai/summary` dengan `Origin: http://evil.com` | Status 403, body `{"error": "Forbidden"}` |
| `test_security__post_no_origin_allowed` | POST tanpa Origin header (curl-style) | Bukan 403 (Origin check hanya reject kalau ada DAN invalid — sesuai middleware Section 11) |
| `test_security__post_valid_origin_passes` | POST dengan `Origin: http://localhost:8765` | Bukan 403 (lolos ke handler) |
| `test_ai_summary__no_api_key_returns_disabled` | Monkeypatch env: hapus `ANTHROPIC_API_KEY` & `OPENAI_API_KEY`; POST `/api/ai/summary` | Status 200 atau 503 dengan body `{"enabled": false, "reason": "no_api_key"}` — disable graceful |
| `test_ai_summary__mocked_anthropic_returns_summary` | Set `ANTHROPIC_API_KEY=test`; monkeypatch `AnthropicProvider.generate_summary` return dict valid; POST dengan body `{file, function}` | Status 200, body punya `role`, `importance`, `hidden_assumption` |
| `test_ai_summary__mocked_provider_401_returns_error` | Mock provider raise `AuthenticationError` | Response body punya `error_type: "auth_failed"`, key fragment TIDAK muncul di error message |
| `test_ai_summary__mocked_provider_429_returns_rate_limit` | Mock raise `RateLimitError` dengan `retry_after=15` | Response body punya `error_type: "rate_limited"`, `retry_after: 15` |
| `test_ai_summary__mocked_timeout` | Mock raise `httpx.TimeoutException` | Response `error_type: "timeout"` |
| `test_ai_summary__caches_result` | Call mock provider sekali, panggil endpoint 2x dengan same `(file, function)` | Provider mock dipanggil 1x saja (cache hit kedua) |

**Mocking AI provider:** pakai `monkeypatch.setattr("codemap.ai.provider.AnthropicProvider.generate_summary", ...)`. Tidak butuh `responses` atau `vcr.py` — provider abstraction sudah testable. Kalau pakai SDK Anthropic/OpenAI langsung tanpa wrapper, baru pertimbangkan `respx` (sudah satu family dengan httpx, lightweight) — tapi hanya kalau perlu.

---

### 13.5 Coverage Threshold (Phase 1)

| Module | Target | Alasan |
|--------|--------|--------|
| `codemap/scanner/sanitize.py` | **95%** | Security-critical, semua pattern wajib ada test (lihat C-01) |
| `codemap/scanner/ast_parser.py` | **85%** | Core logic, edge cases banyak tapi beberapa branch hardware-dependent (timeout SIGALRM vs multiprocessing) |
| `codemap/scanner/resolver.py` | **85%** | Deterministik, gampang di-cover |
| `codemap/scanner/graph_builder.py` | **80%** | Mostly assembly logic |
| `codemap/server/app.py` | **75%** | Middleware ter-cover via integration test; error handlers sulit di-trigger semua |
| `codemap/ai/*` | **70%** | Provider real path tidak ter-test (mocked); fokus pada error handling + cache |
| `codemap/cli.py` | **50%** | Mostly Typer glue + print statements; smoke test cukup |

**Overall threshold: 80% lines, 70% branches.**

**Di-exclude dari coverage** (`.coveragerc` / `pyproject.toml [tool.coverage.run]`):
```toml
[tool.coverage.run]
source = ["codemap"]
omit = [
  "codemap/__init__.py",          # version string only
  "codemap/server/app.py:*uvicorn.run*",  # tidak bisa di-test tanpa bind socket
]

[tool.coverage.report]
exclude_lines = [
  "pragma: no cover",
  "if TYPE_CHECKING:",
  "raise NotImplementedError",
  "if __name__ == .__main__.:",
]
fail_under = 80
```

**Frontend (`frontend/*.js`) di luar coverage Python sepenuhnya** — manual test selama development. Kalau di Phase 2+ frontend grow signifikan, pertimbangkan Vitest + jsdom, tapi YAGNI sekarang.

**Bukan 100% karena:** branch error handler tertentu (MemoryError, OSError exotic) hanya bisa di-trigger lewat heroic monkeypatching yang menguji mock framework, bukan logic. ROI rendah.

---

### 13.6 CI Setup — `.github/workflows/test.yml`

```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - name: Checkout
        # actions/checkout@v4.1.7
        uses: actions/checkout@692973e3d937129bcbf40652eb9f2f61becf3332

      - name: Setup Python ${{ matrix.python-version }}
        # actions/setup-python@v5.1.1
        uses: actions/setup-python@39cd14951b08e74b54015e9e001cdefcf80e669f
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev,ai]"

      - name: Lint (ruff)
        run: ruff check codemap/ tests/

      - name: Format check (ruff)
        run: ruff format --check codemap/ tests/

      - name: Type check (mypy)
        run: mypy codemap/

      - name: Run tests with coverage
        run: |
          pip install coverage
          coverage run -m pytest tests/ -v
          coverage report --fail-under=80
          coverage xml

      - name: Upload coverage artifact
        if: matrix.python-version == '3.12'
        # actions/upload-artifact@v4.3.6
        uses: actions/upload-artifact@834a144ee995460fba8ed112a2fc961b36a5ec5a
        with:
          name: coverage-report
          path: coverage.xml
          retention-days: 14
```

**Catatan SHA pinning (konsisten dengan L-01):** SHA di atas adalah contoh format — saat implementasi, lookup SHA terbaru dari masing-masing action's release page dan pin. Jangan pakai tag `@v4` karena tag bisa di-overwrite (supply chain risk). Comment di atas SHA = tag yang setara untuk readability.

**Yang sengaja tidak ada di CI:**
- Codecov upload — tambahin kalau project tumbuh dan butuh PR coverage diff. Artifact upload cukup untuk solo dev.
- Matrix OS (Windows/macOS) — Phase 1 Linux saja; Windows-specific code path (`parse_timeout` multiprocessing) bisa di-test lokal manual. Tambah `windows-latest` saat ada bug report Windows-specific.
- Real AI provider integration test — TIDAK pernah. Selalu mock.

---

---

## 14. Edge Cases & Known Limitations

### Parser edge cases

| Case | Behavior |
|------|----------|
| `importlib.import_module()` | Add ke `warnings[]`, edge tidak dibuat |
| `from X import *` | Edge dibuat, weight = -1 (unknown), warning |
| `try: import X except: import Y` | Kedua edge dibuat, `is_conditional: true` |
| Relative imports | Resolve ke absolute path sebelum buat edge |
| `__all__` definition | Override exported_names dari konvensi underscore |
| Nested functions | Child di parent function, tidak top-level |
| `@property` | Flag sebagai property, caller via attribute access tidak terdeteksi |
| Symlinks | Resolve real path, max depth 5, cegah duplicate nodes |
| `exec()` / `eval()` | Warning: dynamic code tidak bisa di-analyse |
| C extensions (`.so`) | Warning: no Python source, skip |
| File > 1MB | Skip + warning |
| Parse timeout > 5s | Skip + warning |
| File encoding non-UTF-8 | `tokenize.detect_encoding()` sebelum parse |

### File modified during scan

- Snapshot `file_modified_at` di awal scan
- Post-scan compare → kalau berubah, `scan_inconsistency` warning
- Jangan crash — tetap render, tapi user di-inform

---

## 15. Phase Breakdown

### Phase 1 — Core Visual (2-3 minggu)

```
[ ] CLI entry point (Typer)
[ ] safe_parse() + encoding detection
[ ] AST scanner — files, functions, imports, exports, constants
[ ] sanitize_constant_value() di graph_builder
[ ] Import resolver — relative → absolute paths
[ ] Graph JSON builder
[ ] FastAPI server — 127.0.0.1 only, CORS + Origin + Host middleware
[ ] StaticFiles mount via Path(__file__)
[ ] D3.js Canvas renderer — nodes + edges
[ ] Zoom + pan (D3 zoom behavior)
[ ] Node visual: ring/stroke bukan solid fill
[ ] Hover tooltip (filename, path, risk summary)
[ ] Hover behavior — highlight connected edges, dim others
[ ] Klik node → side panel slide in
[ ] Side panel — function list dengan criticality dot
[ ] Function expand — callers, callees, params, returns, decorators
[ ] Filter pills — high risk, dead code
[ ] Warning banner (collapsible, amber)
[ ] Loading state + progress bar
[ ] Empty states (3 variants)
[ ] Error states (port conflict, no permission, no files)
[ ] Toast notifications
[ ] Cmd+K search overlay
[ ] Auto-open browser
[ ] pyproject.toml + frontend force-include
[ ] Verifikasi wheel isi frontend assets
```

### Phase 2 — Risk Analysis (1-2 minggu)

```
[ ] none_return_unchecked detection
[ ] uncaught_exception detection
[ ] dead_code detection
[ ] star_import warning
[ ] circular_import_toplevel detection
[ ] missing_type_annotation (low)
[ ] unused_parameter (low)
[ ] Node color update berdasarkan real risk data
[ ] Risk cards di function detail panel
```

### Phase 3 — AI Layer (1 minggu)

```
[ ] Provider abstraction (Anthropic + OpenAI)
[ ] scrub_secrets() sebelum kirim ke AI
[ ] Consent notice pertama kali AI dipanggil
[ ] Cache read/write + invalidation + chmod 600
[ ] .gitignore check untuk .codemap/ pada startup
[ ] POST /api/ai/summary endpoint
[ ] [Generate AI Insight] button
[ ] Loading + error states untuk AI
[ ] Graceful disable kalau no API key
[ ] SECURITY.md di repo
[ ] GitHub Environments + pinned SHA di publish.yml
```

---

## 16. Explicitly Out of Scope (MVP)

```
✗ Minimap — ditolak
✗ Multi-language support
✗ Runtime / dynamic analysis
✗ Git history analysis
✗ Test coverage mapping
✗ requirements.txt / third-party dependency graph
✗ Full type inference (mypy integration)
✗ VS Code extension
✗ Real-time file watching
✗ Collaborative / share features
✗ Cloud hosting / SaaS
✗ Export graph sebagai image/SVG
✗ React / build step apapun
```

---

## 17. Development Bootstrap

```bash
# Setup
git clone https://github.com/Maouv/CodeMAP.git
cd CodeMAP
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Mulai dari sini — test parser dulu sebelum sentuh frontend
python -m pytest tests/test_ast_parser.py -v

# Build dan verifikasi wheel
python -m build
unzip -l dist/codemap-*.whl | grep frontend
```

### D3 timebox warning

- Hari 1: Node + edge Canvas render + zoom/pan
- Hari 2: Hover highlight + klik behavior
- Hari 3: Node color + tooltip

Lewat Hari 3 belum progress → scope down D3, fokus ke scanner dulu.

---

## 18. Decision Log
| Keputusan | Alasan | Tanggal |
|-----------|--------|---------|
| Vanilla JS, no React | PyPI distribution — no build step | 2026-06-27 |
| Canvas bukan SVG | >2000 nodes performance | 2026-06-27 |
| host=127.0.0.1 | Security — no 0.0.0.0 | 2026-06-27 |
| Minimap ditolak | Scope MVP | 2026-06-28 |
| Frontend state: shared object + EventTarget | Simple, no deps, no build step | 2026-06-28 |

---

*BLUEPRINT.md — Living document. Update setiap kali ada keputusan arsitektur baru.*  
*Last updated: 2026-06-28*
