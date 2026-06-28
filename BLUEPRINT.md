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

### Error States (dari UX Agent — akan diisi)

*Section ini akan diisi oleh UX Agent dengan spec error states lengkap.*

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

*Section ini akan diisi oleh Testing Agent.*

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

*BLUEPRINT.md — Living document. Update setiap kali ada keputusan arsitektur baru.*  
*Last updated: 2026-06-28*
