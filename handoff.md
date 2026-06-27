# codemap — Project Handoff Document

> Generated from planning session: 2026-06-27  
> Status: Ready for Phase 1 implementation  
> Author: Maou + Claude planning session

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
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

Tool detect otomatis key mana yang tersedia. Kalau keduanya ada, default ke Anthropic. Kalau tidak ada key sama sekali, AI features disabled gracefully — tool tetap fully functional tanpa AI.

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
    │       └── GET /api/graph → return graph JSON
    │       └── POST /api/ai/summary → trigger AI call
    │
    └── Frontend (Vanilla JS + D3.js)
            └── Render interactive graph
            └── Side panel for drill down
            └── AI summary on demand
```

### Why this stack

- **Python AST (built-in):** Zero external dependency untuk core parsing. `ast` module native Python, deterministic, reliable.
- **FastAPI:** Lightweight, async, bisa serve static files sekaligus. Tidak perlu dua process.
- **D3.js:** Full control atas visual. Force-directed graph dengan custom node/edge styling. Tantangan yang disengaja untuk kontrol penuh.
- **Vanilla JS (no React):** Mengurangi complexity frontend. D3 lebih natural di vanilla JS daripada di React.

---

## 5. File Structure

```
codemap/
├── codemap/
│   ├── __init__.py
│   ├── cli.py                  # Entry point — Typer CLI
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── ast_parser.py       # Core AST traversal logic
│   │   ├── resolver.py         # Resolve relative imports → absolute paths
│   │   ├── risk_analyzer.py    # Static risk detection
│   │   └── graph_builder.py    # Assemble final graph JSON
│   ├── server/
│   │   ├── __init__.py
│   │   └── app.py              # FastAPI app — serve frontend + /api routes
│   └── ai/
│       ├── __init__.py
│       ├── provider.py         # Abstraction: OpenAI / Anthropic
│       └── cache.py            # .codemap/cache.json read/write + invalidation
├── frontend/
│   ├── index.html
│   ├── graph.js                # D3.js force-directed graph
│   ├── panel.js                # Side panel logic
│   └── style.css
├── tests/
│   ├── fixtures/               # Sample Python files untuk test
│   └── test_ast_parser.py
├── pyproject.toml
├── README.md
└── .gitignore                  # include .codemap/
```

---

## 6. CLI Interface

```bash
# Basic — scan current directory
codemap .

# Scan specific directory
codemap ./src

# Custom port (default: 8765)
codemap ./src --port 8080

# Exclude directories
codemap ./src --exclude tests/ migrations/ __pycache__/

# Serve tapi tidak auto-open browser
codemap ./src --no-browser

# Force re-scan (ignore cache)
codemap ./src --no-cache

# Specify AI provider explicitly
codemap ./src --ai-provider anthropic
codemap ./src --ai-provider openai
```

### CLI output di terminal

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

---

## 7. Data Contract (Graph JSON Schema)

Ini kontrak antara Python scanner dan D3 frontend. **Jangan ubah shape ini tanpa update keduanya.**

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
      "real_path": "/absolute/path/services/user_service.py",
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
          "is_star": false
        }
      ],
      "constants": [
        {
          "name": "MAX_RETRY",
          "value": "3",
          "line": 8
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

---

## 8. UX Flow (Frontend)

### Level 0 — Graph Overview (default state)

- Semua file = node
- Benang = import relationship
- Ketebalan benang = `weight` (berapa banyak nama yang diimport)
- Warna node:
  - `#6B7280` abu-abu = clean, no issues
  - `#F59E0B` kuning = ada warnings medium/low
  - `#EF4444` merah = ada risk high / dead code / circular import
- Tidak ada label text di graph — hanya muncul saat hover
- Zoom + pan enabled (D3 zoom behavior)

### Level 1 — File Panel (klik node)

- Side panel slide in dari kanan — **graph tetap visible, tidak di-replace**
- Panel width: 320px
- Panel content:
  - Nama file + relative path
  - Badge: "X functions · Y warnings"
  - List fungsi dengan dot criticality (merah/kuning/hijau/hitam)
  - Fungsi collapsed by default
  - Constants section (collapsed)
  - Imports section (collapsed)

### Level 2 — Function Detail (klik fungsi di panel)

- Expand inline di panel yang sama
- Content:
  - Parameters + type annotations
  - Return type
  - Line range (klikable → buka file di editor jika bisa)
  - "Called by" list
  - "Calls" list
  - Decorators (kalau ada)
  - ⚠️ Risk flags — full detail
  - `[Generate AI Insight]` tombol — disabled kalau no API key

### Level 3 — AI Insight (klik Generate)

- Loading state: spinner + "Analyzing..."
- Result muncul di bawah tombol, dalam card terpisah
- Cached — kalau sudah pernah di-generate dan file tidak berubah, langsung show cached result
- Format structured:
  ```
  Role dalam file: [satu kalimat]
  Kenapa penting: [satu kalimat]
  Hidden assumption: [kalau ada]
  ```

### Graph highlight behavior

- Hover node → highlight semua edge yang terhubung, dim yang lain
- Klik node → panel open + node di-pin highlighted
- Hover fungsi di panel → highlight edge yang relevan di graph
- Escape → close panel, reset highlight

---

## 9. Risk Flags Specification

Semua risk flags adalah **pure static analysis — no AI required.**

### Implemented di Phase 2

| Flag Type | Severity | Detection Logic |
|-----------|----------|----------------|
| `none_return_unchecked` | high | Fungsi return `X \| None`, caller tidak ada `if result:` atau `is not None` check |
| `uncaught_exception` | medium | Call ke fungsi yang bisa raise, tidak ada `try/except` di caller maupun callee |
| `dead_code` | medium | Fungsi defined, zero callers di seluruh codebase |
| `star_import` | medium | `from X import *` — bad practice, exported names unknown |
| `circular_import_toplevel` | high | A import B di top-level, B import A di top-level |
| `missing_type_annotation` | low | Public function tanpa type hints |
| `unused_parameter` | low | Parameter di-declare tapi tidak dipakai dalam function body |

### Conservative approach — penting

**Hanya flag yang obvious.** False positive lebih berbahaya dari false negative karena merusak kepercayaan user terhadap tool.

Contoh: jangan flag `none_return_unchecked` kalau caller menggunakan `assert result is not None` — itu valid check meskipun tidak conventional.

---

## 10. AI Layer Specification

### When AI is called

- **Never** saat initial scan
- **Only** saat user explicitly klik `[Generate AI Insight]`
- Cache result — invalidate kalau `file_modified_at` berubah

### Cache structure

```
.codemap/
└── cache.json
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
        "importance": "8 downstream functions assume return tidak None — kalau behavior ini berubah, semua akan error",
        "hidden_assumption": "Expects database connection sudah initialized sebelum dipanggil"
      }
    }
  }
}
```

### AI prompt structure

```
System:
You are a code analyst. Analyze the given Python function in context 
of its file. Respond ONLY in JSON, no markdown, no explanation outside JSON.

User:
File: services/user_service.py
File role: [inferred from filename + imports]

Full file content:
[entire file content]

Target function: get_user
- Called by: [list]
- Calls: [list]  
- Returns: User | None
- Risk flags detected: [list]

Respond with JSON:
{
  "role": "one sentence — what this function's job is",
  "importance": "one sentence — why it matters in this codebase",
  "hidden_assumption": "one sentence — what must be true for this to work, or null"
}
```

### Provider abstraction

```python
# codemap/ai/provider.py

class AIProvider:
    def generate_summary(self, file_content: str, function_context: dict) -> dict:
        raise NotImplementedError

class AnthropicProvider(AIProvider):
    model = "claude-haiku-4-5-20251001"  # cheapest, cukup untuk summary
    ...

class OpenAIProvider(AIProvider):
    model = "gpt-4o-mini"
    ...

def get_provider() -> AIProvider | None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return None  # AI disabled, graceful
```

---

## 11. Edge Cases & Known Limitations

### Parser edge cases — harus di-handle

| Case | Behavior |
|------|----------|
| `importlib.import_module()` dynamic import | Add ke `warnings[]` dengan type `dynamic_import`, edge tidak dibuat |
| `from X import *` star import | Edge dibuat ke source file, weight unknown (-1), flag sebagai warning |
| `try: import X except: import Y` conditional import | Buat kedua edge, mark dengan `is_conditional: true` |
| Relative imports (`from . import X`) | Resolve ke absolute path berdasarkan file location sebelum buat edge |
| `__all__` definition | Prioritaskan sebagai exported_names, override konvensi underscore |
| Nested functions | Tampilkan sebagai child di parent function, tidak sebagai top-level node |
| `@property` decorator | Flag sebagai property, note bahwa caller detection via attribute access (tidak terdeteksi) |
| Symlinks | Resolve ke real path sebelum assign node ID — cegah duplicate nodes |

### Circular import nuance

```python
# BAD — flag sebagai circular_import_toplevel
# a.py: import b
# b.py: import a

# OK — jangan flag
# a.py: 
def get_thing():
    from b import something  # lazy import, valid pattern
    return something
```

### File modified during scan

- Snapshot semua `file_modified_at` di awal scan
- Post-scan: compare ulang
- Kalau ada yang berubah → tambahkan ke `warnings[]` dengan type `scan_inconsistency`
- Jangan fail — tetap render graph, tapi user di-inform

### None check false positive prevention

Jangan flag sebagai `none_return_unchecked` kalau caller menggunakan salah satu dari:
- `if result:`
- `if result is not None:`
- `assert result is not None`
- `result or default_value`

---

## 12. Phase Breakdown

### Phase 1 — Core Visual (Target: 2-3 minggu)

```
[ ] CLI entry point (Typer)
[ ] Python AST scanner — files, functions, imports, exports, constants
[ ] Import resolver — relative → absolute paths
[ ] Graph JSON builder
[ ] FastAPI server — serve frontend + GET /api/graph
[ ] D3.js force-directed graph — nodes + edges
[ ] Zoom + pan behavior
[ ] Node color berdasarkan risk_level (placeholder, belum real risk analysis)
[ ] Hover behavior — highlight connected edges
[ ] Klik node → side panel
[ ] Side panel — function list dengan criticality dot
[ ] Function expand — callers, callees, params, returns
[ ] Auto-open browser
[ ] pyproject.toml + PyPI ready structure
```

### Phase 2 — Risk Analysis (Target: 1-2 minggu)

```
[ ] none_return_unchecked detection
[ ] uncaught_exception detection  
[ ] dead_code detection
[ ] star_import warning
[ ] circular_import_toplevel detection
[ ] missing_type_annotation (low severity)
[ ] unused_parameter (low severity)
[ ] Risk flags tampil di panel
[ ] Node color update berdasarkan real risk data
[ ] warnings[] tampil di UI (collapsible banner)
```

### Phase 3 — AI Layer (Target: 1 minggu)

```
[ ] Provider abstraction (Anthropic + OpenAI)
[ ] Cache read/write + invalidation logic
[ ] POST /api/ai/summary endpoint
[ ] [Generate AI Insight] button di panel
[ ] Loading state + error state
[ ] Graceful disable kalau no API key
[ ] README documentation untuk BYOK setup
```

---

## 13. Explicitly Out of Scope (MVP)

Semua ini valid future features — tapi bukan Phase 1, 2, atau 3.

```
✗ Multi-language support (JavaScript, TypeScript, Go, dll)
✗ Runtime / dynamic analysis
✗ Git history analysis ("fungsi ini sering diubah")
✗ Test coverage mapping
✗ requirements.txt / dependency graph (third-party packages)
✗ Type inference yang complex (butuh full type checker / mypy integration)
✗ VS Code extension
✗ Real-time file watching (graph auto-update saat file save)
✗ Collaborative features (share graph ke tim)
✗ Cloud hosting / SaaS version
✗ Export graph sebagai image/SVG
```

---

## 14. Development Notes

### Bootstrap command untuk mulai Phase 1

```bash
mkdir codemap && cd codemap
python -m venv .venv && source .venv/bin/activate
pip install typer fastapi uvicorn

# Buat struktur folder
mkdir -p codemap/{scanner,server,ai} frontend tests/fixtures

# Test AST parser dengan sample file dulu
# Sebelum sentuh D3, pastikan JSON output dari scanner sudah benar
```

### D3.js timebox warning

D3 force-directed graph dengan interactivity penuh bisa jadi rabbit hole. Set timebox:
- **Hari 1:** Node + edge render + zoom/pan
- **Hari 2:** Hover highlight + klik behavior
- **Hari 3:** Node color + label on hover

Kalau Hari 3 belum selesai dan belum ada progress → scope down D3, fokus ke Python scanner dulu. Visual bisa dipoles belakangan, data harus benar dulu.

### File yang paling kritis di Phase 1

`codemap/scanner/ast_parser.py` — ini jantung dari seluruh tool. Test ini paling dulu dengan berbagai fixture sebelum build apapun di atas.

---

*End of handoff document. Generated: 2026-06-27*
