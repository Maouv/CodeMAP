# TASK_PLAN.md — graps Phase 1 Implementation Plan

> Generated from: BLUEPRINT.md (Section 4, 5, 7, 11, 12, 13, 14, 15)
> Source of truth: BLUEPRINT.md — jangan buat keputusan arsitektur baru tanpa update BLUEPRINT.
> Code style: **Semua agent implementasi WAJIB menggunakan skill `ponytail` saat menulis code.**

---

## URUTAN IMPLEMENTASI (Dependency Order)

```
1.  graps/scanner/sanitize.py          ← no deps, security-critical
2.  graps/scanner/ast_parser.py        ← no deps, core parser
3.  tests/fixtures/ (all .py files)      ← butuh ast_parser shape final
4.  tests/test_ast_parser.py             ← butuh fixtures + ast_parser
5.  graps/scanner/resolver.py          ← butuh ast_parser.ParsedImport
6.  graps/scanner/risk_analyzer.py     ← butuh ast_parser.ParseResult
7.  graps/scanner/graph_builder.py     ← butuh ast_parser + resolver + sanitize + risk_analyzer
8.  tests/test_resolver.py               ← butuh resolver + fixtures
9.  tests/test_risk_analyzer.py          ← butuh risk_analyzer + fixtures
10. graps/ai/cache.py                  ← no deps on scanner
11. graps/ai/provider.py               ← butuh cache.py
12. graps/server/app.py                ← butuh graph_builder + ai/provider
13. graps/cli.py                       ← butuh server/app + scanner pipeline
14. graps/__init__.py                  ← standalone, version string only
15. frontend/ (index.html → style.css → graph.js → panel.js → filter.js → search.js → toast.js)
16. pyproject.toml                       ← butuh frontend final + semua graps/ modules
17. tests/test_graph_builder.py          ← butuh graph_builder + fixtures
18. tests/test_api.py                    ← butuh server/app + ai/provider (mockable)
19. .github/workflows/test.yml           ← butuh semua test + pyproject.toml
```

---

## PER-FILE DETAIL

---

### 1. `graps/scanner/sanitize.py`

**BLUEPRINT section:** §11 (Security — sanitize_constant_value), §7 (Data Contract — constants[].value)

**Input yang dibutuhkan:**
- Tidak ada import internal
- Stdlib: `re`

**Output yang dihasilkan:**
- `sanitize_constant_value(name: str, value: str) -> str`
- Returns `"[REDACTED]"` atau value asli

**Spec implementasi:**
- `SENSITIVE_NAME_KEYWORDS` set — copy exact dari §11
- `SENSITIVE_VALUE_PATTERNS` list of compiled `re.Pattern` — copy exact dari §11
- Logic: name check dulu (`any(keyword in name.lower())`), baru value pattern scan
- Doctest dari §11 harus pass
- Target coverage: **95%** (security-critical, §13.5)

**Context boundary — agent TIDAK perlu tahu:**
- Bagaimana `graph_builder.py` memanggil function ini
- Schema JSON (§7)
- FastAPI, CLI, frontend
- Risk analyzer logic
- AI layer

---

### 2. `graps/scanner/ast_parser.py`

**BLUEPRINT section:** §4 (Architecture — AST Parser Hybrid), §5 (File Structure), §11 (AST parser safety — safe_parse), §14 (Edge Cases — tabel Parser edge cases)

**Input yang dibutuhkan:**
- Stdlib: `ast`, `dataclasses`, `pathlib`, `tokenize`, `signal` (Unix) / `multiprocessing` (Windows)
- Tidak ada import internal

**Output yang dihasilkan:**
- Dataclasses: `ParsedFunction`, `ParsedImport`, `ParseResult`
- Functions: `safe_parse(path: Path) -> ParseResult | None`, `_decorator_name(node) -> str`
- Class: `_ScannerVisitor(ast.NodeVisitor)`

**Spec implementasi:**

`safe_parse()` guards (§11 + §14):
- File > 1MB → return None + log warning "too large"
- Parse timeout > 5s — Unix: signal.alarm; Windows: multiprocessing
- Non-UTF-8: tokenize.detect_encoding() sebelum open()
- Exceptions (TimeoutError, SyntaxError, MemoryError) → return None + log

`_ScannerVisitor` methods:
- `visit_FunctionDef` + `visit_AsyncFunctionDef`: scope stack untuk is_nested, qualified_name, parent
- `visit_ClassDef`: push/pop scope stack
- `visit_Import` + `visit_ImportFrom`: extract ParsedImport, detect is_star
- `visit_Assign`: detect __all__ → exported_names; detect exec/eval → warning
- `visit_Call`: detect importlib.import_module() → warning + is_dynamic=True
- `visit_Try`: set is_conditional=True pada semua imports di dalam try/except blocks
- `result()`: return assembled ParseResult

Edge cases WAJIB di-handle (§14):
- importlib.import_module() → warning, edge tidak dibuat
- from X import * → is_star=True
- try/except import → keduanya is_conditional=True
- __all__ → override exported_names
- Nested functions → is_nested=True
- @property → is_property=True
- exec()/eval() → warning "dynamic_code"
- Non-UTF-8 encoding → detect sebelum parse

**Context boundary — agent TIDAK perlu tahu:**
- Cara resolver.py resolve relative imports
- Risk analysis logic
- graph_builder schema shape
- FastAPI, frontend, CLI
- sanitize_constant_value (itu dipanggil di graph_builder, bukan di sini)
- AI layer

---

### 3. `tests/fixtures/*.py`

**BLUEPRINT section:** §13.2 (Fixture Files Strategy — tabel lengkap)

**Input yang dibutuhkan:**
- Tidak ada — ini static .py files

**Output yang dihasilkan:**
- File .py kecil (~5-30 baris) masing-masing trigger satu edge case

**Daftar wajib dibuat:**

Dari §5: `simple.py`, `circular_a.py`, `circular_b.py`, `dynamic_import.py`, `star_import.py`, `conditional_import.py`, `nested_functions.py`, `decorators.py`, `none_return.py`, `dead_code.py`, `type_checking.py`

Tambahan §13.2: `syntax_error.py`, `exec_eval.py`, `latin1_encoded.py` (bytes), `relative_imports/__init__.py`, `relative_imports/sub.py`, `relative_imports/main.py`, `all_definition.py`, `secret_constants.py`

Tidak perlu dibuat sebagai file:
- `large_file.py` → generate in-test: `"x = 1\n" * 200_000`
- Symlink → buat via tmp_path di test runtime

**Context boundary — agent TIDAK perlu tahu:**
- ast_parser internals
- Risk analyzer, graph schema
- Server, frontend, CLI

---

### 4. `tests/test_ast_parser.py`

**BLUEPRINT section:** §13.3 (Unit Test Spec — tabel 17 test cases), §13.1

**Input yang dibutuhkan:**
- `graps.scanner.ast_parser`
- `tests/fixtures/` (semua .py files)
- Stdlib: `pytest`, `pathlib`

**Output yang dihasilkan:**
- ~17 test functions sesuai tabel §13.3

**Spec:**
- Format nama: `test_<area>__<scenario>` (double underscore)
- Setiap test ≤ 15 baris
- large_file → generate in-test
- timeout, MemoryError → monkeypatch

**Context boundary — agent TIDAK perlu tahu:**
- resolver, risk_analyzer, graph_builder
- FastAPI, frontend, CLI, AI layer

---

### 5. `graps/scanner/resolver.py`

**BLUEPRINT section:** §4, §5, §7 (imports[].resolved_path), §11 (Symlink depth limit), §14 (Relative imports, Symlinks)

**Input yang dibutuhkan:**
- `graps.scanner.ast_parser.ParsedImport`
- Stdlib: `pathlib`, `sys`

**Output yang dihasilkan:**
- `resolve_import(imp: ParsedImport, current_file: Path, root: Path) -> Path | None`
- `resolve_safe(path: Path, depth: int = 0) -> Path | None`

**Spec:**
- Relative imports → resolve relative ke current_file.parent
- Absolute imports → try dari root, fallback None
- resolve_safe(): max depth 5, return None kalau exceed
- Output: relative path dari root saja (bukan absolute, M-03)

**Context boundary — agent TIDAK perlu tahu:**
- Risk analysis, graph_builder schema lengkap
- FastAPI, frontend, CLI, AI layer, sanitize.py

---

### 6. `graps/scanner/risk_analyzer.py`

**BLUEPRINT section:** §9 (Risk Flags — tabel + Conservative approach)

**Input yang dibutuhkan:**
- `graps.scanner.ast_parser.ParseResult`
- `list[ParseResult]` untuk cross-file analysis (dead_code, circular)

**Output yang dihasilkan:**
- `analyze_risks(result: ParseResult, all_results: list[ParseResult]) -> list[dict]`
- Risk dict: `{type, severity, detail, affected_files}`

**Phase 1 vs Phase 2:**
- Phase 1: `star_import` (bisa dari ParseResult tunggal)
- Phase 2: none_return_unchecked, uncaught_exception, dead_code, circular_import_toplevel, missing_type_annotation, unused_parameter

**Conservative rules (§9):**
- Jangan flag none_return_unchecked kalau caller pakai guard: `if result:`, `if result is not None:`, `assert result is not None`, `result or default`
- Jangan flag circular import kalau lazy import

**Context boundary — agent TIDAK perlu tahu:**
- graph_builder JSON shape
- resolver internals
- FastAPI, frontend, CLI, AI layer, sanitize.py

---

### 7. `graps/scanner/graph_builder.py`

**BLUEPRINT section:** §7 (Data Contract — full schema), §4, §11 (sanitize call pattern)

**Input yang dibutuhkan:**
- `graps.scanner.ast_parser.ParseResult` (list)
- `graps.scanner.resolver` (resolve_import)
- `graps.scanner.risk_analyzer` (analyze_risks)
- `graps.scanner.sanitize.sanitize_constant_value`
- Stdlib: `datetime`, `pathlib`, `json`

**Output yang dihasilkan:**
- `build_graph(results: list[ParseResult], root: Path) -> dict`
- Dict: `{meta, nodes, edges, warnings}` sesuai exact schema §7

**Kritis:**
- constants[] WAJIB memanggil sanitize_constant_value(name, value) sebelum append (§11 C-01)
- edges[].weight = -1 untuk star imports
- Relative paths only, bukan absolute (M-03)
- file_modified_at dipass dari scanner, bukan di-generate di sini

**Context boundary — agent TIDAK perlu tahu:**
- FastAPI internals, routing
- Frontend rendering
- CLI argument parsing
- AI layer, cache

---

### 8. `tests/test_resolver.py`

**BLUEPRINT section:** §13.1, §14 (Relative imports, Symlinks)

**Input yang dibutuhkan:**
- `graps.scanner.resolver`
- `tests/fixtures/relative_imports/`
- Stdlib: `pytest`, `tmp_path`

**Output:** Test suite resolver — relative import resolution, symlink depth guard

**Context boundary — agent TIDAK perlu tahu:**
- graph_builder, risk_analyzer, FastAPI, frontend, CLI, AI layer

---

### 9. `tests/test_risk_analyzer.py`

**BLUEPRINT section:** §9, §13.1

**Input yang dibutuhkan:**
- `graps.scanner.risk_analyzer`
- `graps.scanner.ast_parser.safe_parse`
- Fixtures: `none_return.py`, `dead_code.py`, `star_import.py`, `circular_a.py`, `circular_b.py`

**Output:** Test suite risk_analyzer

**Context boundary — agent TIDAK perlu tahu:**
- graph_builder, resolver, FastAPI, frontend, CLI, AI layer

---

### 10. `graps/ai/cache.py`

**BLUEPRINT section:** §10 (Cache structure, Cache file permissions)

**Input yang dibutuhkan:**
- Stdlib: `json`, `pathlib`, `os`, `datetime`

**Output yang dihasilkan:**
- `read_cache(cache_path: Path) -> dict`
- `write_cache(cache_path: Path, key: str, entry: dict) -> None`
- `is_valid(entry: dict, current_modified_at: str) -> bool`
- Permissions: `cache_path.touch(mode=0o600)`

**Schema cache key:** `"{file}::{function_name}"`

**Context boundary — agent TIDAK perlu tahu:**
- Provider abstraction
- FastAPI routing
- Scanner pipeline
- Frontend

---

### 11. `graps/ai/provider.py`

**BLUEPRINT section:** §10 (Provider abstraction, Secret scrubbing, When AI is called)

**Input yang dibutuhkan:**
- `graps.ai.cache`
- Optional: `anthropic` SDK, `openai` SDK
- Stdlib: `os`, `re`, `logging`

**Output yang dihasilkan:**
- Abstract `AIProvider` dengan method `generate_summary(file_content, function_context) -> dict`
- `AnthropicProvider` — model: `claude-haiku-4-5-20251001`
- `OpenAIProvider` — model: `gpt-4o-mini`
- `get_provider() -> AIProvider | None`
- `scrub_secrets(source: str) -> str`

**Security rules (§10):**
- Jangan store API key sebagai instance attribute — baca dari env setiap call
- Sanitize exception sebelum log — key fragment tidak boleh muncul
- scrub_secrets() wajib dipanggil sebelum kirim ke AI

**Context boundary — agent TIDAK perlu tahu:**
- Scanner pipeline internals
- FastAPI routing detail
- Frontend
- Risk analyzer

---

### 12. `graps/server/app.py`

**BLUEPRINT section:** §4 (FastAPI + StaticFiles), §11 (CORS, Origin validation, DNS rebinding, host=127.0.0.1), §12 (Frontend path runtime), §10 (POST /api/ai/summary)

**Input yang dibutuhkan:**
- `graps.scanner.graph_builder.build_graph`
- `graps.ai.provider.get_provider`, `AIProvider`
- `graps.ai.cache`
- Runtime: `fastapi`, `uvicorn`

**Output yang dihasilkan:**
- `create_app(graph_data: dict, port: int) -> FastAPI`
- `GET /api/graph` → JSON
- `POST /api/ai/summary` → AI call + cache
- StaticFiles: `FRONTEND_DIR = Path(__file__).parent.parent / "frontend"`
- `uvicorn.run(app, host="127.0.0.1", port=port)` — HARDCODE

**Security middleware WAJIB (§11):**
1. CORSMiddleware
2. enforce_origin (POST/PUT/DELETE validation)
3. validate_host (DNS rebinding protection)

**AI endpoint responses:**
- No key → `{"enabled": false, "reason": "no_api_key"}`
- AuthenticationError → `{"error_type": "auth_failed"}` tanpa key fragment
- RateLimitError → `{"error_type": "rate_limited", "retry_after": N}`
- Timeout → `{"error_type": "timeout"}`

**Context boundary — agent TIDAK perlu tahu:**
- CLI argument parsing
- Scanner internals (hanya butuh graph_data dict)
- Frontend JS internals
- Test runner setup

---

### 13. `graps/cli.py`

**BLUEPRINT section:** §6 (CLI Interface), §4, §15 (Phase 1 — auto-open browser)

**Input yang dibutuhkan:**
- `graps.scanner.ast_parser.safe_parse`
- `graps.scanner.resolver`
- `graps.scanner.graph_builder.build_graph`
- `graps.server.app.create_app`
- Runtime: `typer`
- Stdlib: `pathlib`, `webbrowser`

**Output yang dihasilkan:**
- `app = typer.Typer()`
- Command: `graps [PATH] [--port PORT] [--no-browser]`
- Flow: scan → build_graph → create_app → uvicorn + auto-open browser

**Penting:**
- Scan recursive semua `.py` files dari PATH
- Snapshot file_modified_at sebelum scan
- `webbrowser.open(f"http://localhost:{port}")` setelah server ready

**Context boundary — agent TIDAK perlu tahu:**
- FastAPI internals
- Frontend JS
- AI layer detail
- Cache implementation

---

### 14. `graps/__init__.py`

**BLUEPRINT section:** §5

**Input:** None
**Output:** `__version__ = "0.1.0"` — satu baris saja

**Context boundary:** Tidak perlu tahu apapun selain version string.

---

### 15. `frontend/` (7 files)

**BLUEPRINT section:** §8 (UX Flow + Design System), §4 (Vanilla JS, Canvas2D, D3.js), §7 (Data Contract yang di-consume)

**Urutan implementasi internal:**
```
index.html  →  style.css  →  toast.js  →  filter.js  →  graph.js  →  panel.js  →  search.js
```

**Stack constraint (§4 + §18):**
- Vanilla JS — NO React, NO build step, NO TypeScript
- Canvas2D renderer (bukan SVG) — untuk 2000+ nodes
- D3.js via CDN
- Shared state: plain object + EventTarget

**Data contract dari API:**
- GET /api/graph → {meta, nodes, edges, warnings} sesuai §7
- POST /api/ai/summary → {file, function} → {role, importance, hidden_assumption}

**Context boundary — agent TIDAK perlu tahu:**
- Python scanner internals
- FastAPI routing implementation
- pyproject.toml packaging
- Test suite

---

### 16. `pyproject.toml`

**BLUEPRINT section:** §12 (Packaging — full toml spec)

**Output:** Copy exact dari §12

**Kritis:**
- `[tool.hatch.build.targets.wheel.force-include]` `"frontend" = "graps/frontend"` — ini yang bundling frontend ke wheel
- Optional deps: anthropic, openai, ai, dev sesuai §12
- Entry point: `graps = "graps.cli:app"`

**Verifikasi wajib:**
```bash
python -m build
unzip -l dist/graps-*.whl | grep frontend
```

**Context boundary:** Tidak perlu tahu implementation detail apapun.

---

### 17. `tests/test_graph_builder.py`

**BLUEPRINT section:** §7 (schema assertions), §13.4 (pattern referensi)

**Input yang dibutuhkan:**
- `graps.scanner.graph_builder.build_graph`
- `graps.scanner.ast_parser.safe_parse`
- Fixtures: `secret_constants.py`, `simple.py`, `circular_a.py` + `circular_b.py`

**Key assertions:**
- Output punya keys: meta, nodes, edges, warnings
- meta punya: root, scanned_at, total_files, total_functions, total_edges, has_warnings
- Node dengan DB_PASSWORD = "hunter2" → constants[].value == "[REDACTED]"

**Context boundary — agent TIDAK perlu tahu:**
- FastAPI, frontend, AI layer, CLI

---

### 18. `tests/test_api.py`

**BLUEPRINT section:** §13.4 (Integration Test Spec — 15 test cases)

**Input yang dibutuhkan:**
- `graps.server.app.create_app`
- `graps.ai.provider.AnthropicProvider`
- `fastapi.testclient.TestClient`
- Stdlib: `pytest`, monkeypatch

**Pattern:**
```python
from fastapi.testclient import TestClient
from graps.server.app import create_app

def make_client(graph_data, port=8765):
    app = create_app(graph_data=graph_data, port=port)
    return TestClient(app, base_url="http://localhost:8765")
```

**15 test cases wajib:** Semua ada di tabel §13.4 — baca ulang sebelum implementasi.

**Mocking:** `monkeypatch.setattr("graps.ai.provider.AnthropicProvider.generate_summary", ...)` — tidak boleh hit API beneran.

**Context boundary — agent TIDAK perlu tahu:**
- Scanner internals, frontend, CLI, pyproject.toml

---

### 19. `.github/workflows/test.yml`

**BLUEPRINT section:** §13.6 (CI Setup — full YAML spec)

**Output:** Copy near-exact dari §13.6

**Kritis:**
- SHA pinning — lookup SHA terbaru, jangan pakai tag @v4
- Matrix: Python 3.10, 3.11, 3.12
- Steps: ruff check → ruff format → mypy → pytest + coverage
- `fail_under = 80`
- Tidak ada Codecov upload, tidak ada matrix OS lain

**Context boundary:** Hanya perlu tahu test command yang benar.

---

## RINGKASAN DEPENDENCY GRAPH

```
sanitize.py ──────────────────────────────────┐
                                               ▼
ast_parser.py ──────────────────────────► graph_builder.py ──► server/app.py ──► cli.py
      │                                        ▲                     │
      ├──► resolver.py ───────────────────────┤                     │
      │                                        │                     ▼
      └──► risk_analyzer.py ─────────────────┘              ai/provider.py
                                                                     │
                                                             ai/cache.py
```

**Aturan emas:**
- Setiap agent hanya perlu baca BLUEPRINT section yang tercantum di file-nya
- Jangan buat keputusan arsitektur baru — semua sudah ada di BLUEPRINT
- Selalu gunakan skill `ponytail` saat menulis code
- Test ditulis setelah implementasi target-nya selesai

---

*TASK_PLAN.md — Generated 2026-06-28. Update kalau BLUEPRINT berubah.*
