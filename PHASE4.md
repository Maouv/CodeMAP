# Phase 4 — Tree-sitter Migration & Multi-language Support

> Reference: BLUEPRINT.md §4 (BaseParser Interface, Phase 4 Migration Plan)
> Pre-condition: BaseParser Protocol sudah ada, ASTParser sudah implement BaseParser — VERIFIED.
> Scope: 306 bahasa via `tree-sitter-language-pack` (core: Python, TypeScript, JavaScript, Go, Rust; semua bahasa lain otomatis available).
> Java, C++ — tersedia di library, tidak perlu defer.

---

## 0. Keputusan yang Sudah Final (Jangan Re-discuss)

| Keputusan | Alasan |
|-----------|--------|
| Pakai `tree-sitter-language-pack` (xberg-io) | Satu library: 306 bahasa, code intelligence API (`process()`), on-demand download + local cache. Hapus grammar_manager + language_registry + per-language extractors |
| Pin `tree-sitter-language-pack>=1.12.0,<2.0.0` | API bergerak cepat (0.1→1.12 in 2yr). Upper bound proteksi dari breaking v2 |
| `process()` return `ProcessResult` → adapter map ke `ParsedFile` | Direct 1-to-1 mapping. `tree_sitter_parser.py` jadi adapter layer, bukan parser |
| Python tetap sebagai base app language | Rewrite premature — catat sebagai known limitation |
| `ASTParser` tetap ada sebagai Python fallback | tree-sitter primary, ast module safety net |
| Grammar download on-demand, cached locally | Library handle ini. Offline setelah first download. `prefetch()` available untuk pre-warm |
| `graph_builder.py`, `server/app.py` — TIDAK BOLEH DISENTUH | BaseParser interface melindungi. Perubahan hanya kalau ada bug eksplisit |

---

## 1. Prinsip Wajib

Sama seperti PHASE3.md — berlaku semua task:

1. Simple tapi works.
2. Minimalisir bug — defensive terhadap parser failure per-file, jangan crash seluruh scan.
3. Gampang di-refactor — BaseParser interface tetap menjadi satu-satunya kontrak.
4. Riset library dulu — jangan reinvent wheel.
5. Jangan build dari nol kalau ada yang sudah dibangun.

**Tambahan spesifik Phase 4:**
- Setiap parser failure pada satu file = warning + skip, BUKAN crash seluruh scan.
- Grammar download failure = graceful degrade, file muncul sebagai "unsupported" node.
- `graph_builder.py`, `server/app.py` — **TIDAK BOLEH DISENTUH** kecuali ada bug eksplisit.

---

## 2. Library yang Dipakai (Sudah Diputuskan)

### tree-sitter-language-pack

```bash
pip install tree-sitter-language-pack>=1.12.0,<2.0.0
```

**Repo:** https://github.com/xberg-io/tree-sitter-language-pack
**License:** MIT
**Maintainer:** Na'aman Hirschfeld (nhirschfeld / Goldziher)
**Stats:** 412 stars, 65 forks, 1 open issue, 1406 commits, 187 tags

**Wheel size (verified 2026-07-01):**

| Platform | Wheel Size |
|----------|-----------|
| Linux x86_64 (manylinux_2_34) | 2.3 MB |
| Windows amd64 | 2.1 MB |
| Windows arm64 | 2.0 MB |
| macOS x86_64 | ~2.2 MB |
| macOS arm64 | ~2.0 MB |
| Source tarball | 81.8 kB |

Grammars **tidak** di-bundle di wheel — di-download on-demand dari GitHub releases, cached locally untuk reuse offline.

### Yang TIDAK dipakai

```
✗ tree-sitter (standalone) — butuh manual grammar management, reinvent wheel
✗ tree-sitter-python/typescript/javascript/go/rust (per-grammar packages) — 
  library ini sudah bundle semua + code intelligence API
✗ tree_sitter_languages (all-in-one bundle) — outdated, 50MB+, no code intelligence
✗ Custom grammar download dari GitHub release — reinvent wheel
```

---

## 3. Architecture Overview

```
cli.py
  └── scan()
        └── dispatch_parser(file_path) → BaseParser
              ├── .py files     → TreeSitterParser(lang="python")
              │                   fallback: ASTParser() kalau tree-sitter fail
              ├── .ts/.tsx      → TreeSitterParser(lang="typescript")
              ├── .js/.jsx      → TreeSitterParser(lang="javascript")
              ├── .go           → TreeSitterParser(lang="go")
              ├── .rs           → TreeSitterParser(lang="rust")
              ├── 300+ lainnya  → TreeSitterParser(lang=detect_language_from_path())
              └── unknown ext   → None → UnsupportedFileNode (warning di graph)

graps/scanner/
  ├── __init__.py          → BaseParser, ParsedFile (sudah ada, tidak diubah)
  ├── ast_parser.py        → ASTParser (sudah ada, tetap sebagai Python fallback)
  ├── tree_sitter_parser.py → TreeSitterParser (BARU — adapter only)
  ├── resolver.py          → tidak diubah
  ├── risk_analyzer.py     → di-extend untuk language-aware (PERLU UPDATE)
  ├── graph_builder.py     → tidak diubah (BaseParser interface melindungi ini)
  └── sanitize.py          → tidak diubah
```

**Yang dihapus dari original PHASE4 plan:**
- ~~`grammar_manager.py`~~ → library handle download + cache
- ~~`language_registry.py`~~ → library punya `detect_language_from_path()` untuk 306 bahasa

---

## 4. File Baru — Detail Spec

### 4.1 `graps/scanner/tree_sitter_parser.py`

Adapter layer. Map `ProcessResult` → `ParsedFile`. Tidak ada manual tree walking.

```python
# graps/scanner/tree_sitter_parser.py

from __future__ import annotations
import logging
from pathlib import Path

from graps.scanner import BaseParser, ParsedFile, ParsedFunction, ParsedImport

logger = logging.getLogger(__name__)


class TreeSitterParser:
    """
    Multi-language parser menggunakan tree-sitter-language-pack.
    Implement BaseParser Protocol.

    Satu instance per-scan session (bukan per-file).
    Grammar di-load lazily oleh library (on-demand download + local cache).
    """

    def supported_extensions(self) -> list[str]:
        """
        Return semua extension yang didukung library.
        Pakai available_languages() + library's internal extension map.
        """
        try:
            from tree_sitter_language_pack import detect_language_from_path
            # Library handle 306 bahasa — kita tidak maintain list sendiri.
            # Untuk discover, cli.py pakai detect_language_from_path() per file.
            # Method ini ada untuk Protocol compliance; return [] artinya
            # "cek via detect_language_from_path()".
            return []
        except ImportError:
            return [".py"]  # fallback: Python only

    def parse_file(self, path: Path, root: Path) -> ParsedFile | None:
        """
        Parse satu file. Return None kalau:
        - Library tidak terinstall ( ImportError )
        - File tidak bisa dibaca (encoding error, permission)
        - File > 1MB (sama dengan safe_parse limit di ASTParser)
        - Language tidak terdeteksi (unknown extension)
        - process() raise exception (grammar download gagal, parse error berat)
        """
        try:
            from tree_sitter_language_pack import (
                process,
                ProcessConfig,
                detect_language_from_path,
            )
        except ImportError:
            logger.debug("tree-sitter-language-pack not installed")
            return None

        # Detect language dari path — library handle 306 bahasa
        lang = detect_language_from_path(str(path))
        if lang is None:
            return None  # extension tidak dikenal

        # 1MB guard — konsisten dengan ASTParser
        try:
            size = path.stat().st_size
        except OSError:
            return None
        if size > 1_000_000:
            logger.warning(f"Skip {path}: file too large ({size} bytes)")
            return None

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as e:
            logger.warning(f"Cannot read {path}: {e}")
            return None

        # Config: structure + imports + exports (default True), sisanya False
        config = ProcessConfig(language=lang)

        try:
            result = process(source, config)
        except Exception as e:
            logger.warning(f"process() failed for {path} ({lang}): {e}")
            return None

        rel = str(path.relative_to(root))

        # ── Map ProcessResult → ParsedFile ──────────────────────────────────

        functions = self._extract_functions(result.structure)
        imports = self._extract_imports(result.imports)
        classes = self._extract_classes(result.structure)
        exported_names = self._extract_exports(result.exports)

        # Diagnostics → warnings (syntax errors dari tree-sitter)
        warnings = []
        for diag in result.diagnostics:
            warnings.append(f"line {diag.span.start_line + 1}: {diag.message}")

        return ParsedFile(
            id=rel,
            path=path,
            functions=functions,
            imports=imports,
            constants=[],      # ProcessResult tidak extract constants — Phase 4 ext
            classes=classes,
            exported_names=exported_names,
            file_modified_at=str(path.stat().st_mtime),
            language=lang,
            warnings=warnings,
        )

    # ── Adapter methods: ProcessResult → ParsedFile fields ─────────────────

    @staticmethod
    def _extract_functions(structure: list) -> list[ParsedFunction]:
        """
        Flatten StructureItem tree → flat ParsedFunction list.
        Recurse into children (methods dalam class, dll).

        StructureItem.kind: FUNCTION, METHOD, CLASS, STRUCT, etc.
        Kita ambil FUNCTION dan METHOD, skip CLASS/STRUCT (masuk ke classes).
        """
        results = []

        def _flatten(item, parent_name=None):
            kind_str = str(item.kind).upper() if item.kind else ""

            if "FUNCTION" in kind_str or "METHOD" in kind_str:
                name = item.name or "<anonymous>"
                is_private = TreeSitterParser._detect_is_private(
                    item.visibility, name
                )
                results.append(ParsedFunction(
                    name=name,
                    params=[],           # signature ada di item.signature, parse later
                    returns=None,        # ada di signature, parse later
                    line_start=(item.span.start_line + 1) if item.span else 0,
                    line_end=(item.span.end_line + 1) if item.span else 0,
                    decorators=list(item.decorators) if item.decorators else [],
                    is_private=is_private,
                    callers=[],           # diisi oleh graph_builder
                    callees=[],           # diisi oleh graph_builder
                    parent=parent_name,
                ))

            # Recurse into children (methods dalam class, nested functions)
            if item.children:
                for child in item.children:
                    _flatten(child, parent_name=item.name)

        for item in structure:
            _flatten(item)

        return results

    @staticmethod
    def _extract_imports(imports: list) -> list[ParsedImport]:
        """Map ImportInfo → ParsedImport."""
        results = []
        for imp in imports:
            results.append(ParsedImport(
                target=imp.source,
                lineno=(imp.span.start_line + 1) if imp.span else 0,
                is_conditional=False,   # tidak ada di ImportInfo — Python-specific
                is_star=imp.is_wildcard,
                is_dynamic=False,        # tidak ada di ImportInfo — Python-specific
            ))
        return results

    @staticmethod
    def _extract_classes(structure: list) -> list[dict]:
        """
        Map StructureItem dengan kind=CLASS → dict (sesuai ParsedFile.classes format).
        """
        results = []

        def _find_classes(item):
            kind_str = str(item.kind).upper() if item.kind else ""
            if "CLASS" in kind_str:
                results.append({
                    "name": item.name or "<anonymous>",
                    "line_start": (item.span.start_line + 1) if item.span else 0,
                    "line_end": (item.span.end_line + 1) if item.span else 0,
                    "decorators": list(item.decorators) if item.decorators else [],
                    "methods": [
                        c.name for c in (item.children or [])
                        if "FUNCTION" in str(c.kind).upper() or "METHOD" in str(c.kind).upper()
                    ],
                })
            if item.children:
                for child in item.children:
                    _find_classes(child)

        for item in structure:
            _find_classes(item)

        return results

    @staticmethod
    def _extract_exports(exports: list) -> list[str]:
        """Map ExportInfo → list[str] (nama yang di-export)."""
        return [exp.name for exp in exports if exp.name]

    @staticmethod
    def _detect_is_private(visibility: str | None, name: str) -> bool:
        """
        Detect private berdasarkan visibility modifier atau naming convention.
        - visibility "pub"/"public" → False (public)
        - visibility None + name starts with _ → True (Python convention)
        - visibility None + name starts lowercase (Go) → True (Go unexported)
        - visibility "private"/"internal" → True
        """
        if visibility:
            vis = visibility.lower()
            if vis in ("pub", "public", "exported"):
                return False
            if vis in ("private", "internal"):
                return True
        # Fallback ke naming convention
        if name.startswith("_"):
            return True
        return False
```

**Yang sengaja di-simplify untuk Phase 4:**
- `params` dan `returns` di `ParsedFunction` → kosong dulu. `item.signature` ada string full signature, tapi parsing per-bahasa adalah Phase 4 extension. Tidak breaking — graph tetap render.
- `constants` → `[]`. `ProcessResult` tidak extract constants. Phase 4 extension.
- `is_conditional` / `is_dynamic` di `ParsedImport` → `False`. Tidak ada di `ImportInfo`. Python-specific, bisa di-extend nanti via ASTParser fallback.

**Yang sudah full untuk Phase 4:**
- Function extraction untuk semua 306 bahasa (library handle)
- Import extraction untuk semua bahasa
- Export extraction untuk semua bahasa
- Class extraction (flatten dari StructureItem tree)
- Visibility detection (pub/public/private + naming convention fallback)
- Nested children flatten (recursive)
- Diagnostics → warnings (syntax errors)
- Graceful handling untuk semua failure mode

---

### 4.2 Update `graps/cli.py` — Parser Dispatch

```python
# graps/cli.py — perubahan

from graps.scanner.ast_parser import safe_parse
from graps.scanner.tree_sitter_parser import TreeSitterParser

def _discover(path: Path, exclude: set[str]) -> list[Path]:
    """
    Cari semua file rekursif yang didukung tree-sitter-language-pack.
    Pakai detect_language_from_path() untuk filter — 306 bahasa otomatis.
    Fallback ke *.py kalau library tidak terinstall.
    """
    try:
        from tree_sitter_language_pack import detect_language_from_path
        use_tslp = True
    except ImportError:
        use_tslp = False

    files = []
    for p in path.rglob("*"):
        if not p.is_file():
            continue
        if set(p.parts) & exclude:
            continue
        if use_tslp:
            if detect_language_from_path(str(p)) is not None:
                files.append(p)
        else:
            # Fallback: Python only
            if p.suffix == ".py":
                files.append(p)
    return files


def _parse_file(path: Path, root: Path) -> ParsedFile | None:
    """
    Dispatch parser per file.
    Python: TreeSitterParser dulu, fallback ke ASTParser kalau gagal.
    Lainnya: TreeSitterParser saja, tidak ada fallback.
    """
    ts_parser = TreeSitterParser()
    result = ts_parser.parse_file(path, root)

    if result is not None:
        return result

    # Python fallback ke ASTParser
    if path.suffix == ".py":
        logger.debug(f"tree-sitter failed for {path}, falling back to ASTParser")
        return safe_parse(path)

    # Non-Python, no fallback → unsupported
    return None
```

**Update `main()` dan `_build()`:**

```python
# Ganti:
#   py_files = _discover(root, excl)
#   results = [safe_parse(p) for p in py_files]
# Menjadi:
files = _discover(root, excl)
results = [_parse_file(p, root) for p in files]
results = [r for r in results if r is not None]  # filter None (unsupported/failed)

if not results:
    typer.echo(f"  ✗ No supported files found in {path}")
    raise typer.Exit(1)
```

---

### 4.3 Update `graps/scanner/risk_analyzer.py` — Language-aware

Risk analyzer saat ini Python-specific. Perlu di-generalize tapi **jangan over-engineer.**

**Approach:** language-agnostic untuk flags yang universal, Python-specific flags tetap ada tapi di-skip untuk non-Python files.

```python
# risk_analyzer.py — tambahan

LANGUAGE_AGNOSTIC_RISKS = {
    "dead_code",           # function defined, zero callers — universal
    "unused_parameter",    # parameter tidak dipakai — universal
}

PYTHON_ONLY_RISKS = {
    "none_return_unchecked",   # Python-specific: None | Type return
    "uncaught_exception",      # Python-specific: try/except pattern
    "missing_type_annotation", # Python-specific: type hints
    "star_import",             # Python-specific: from X import *
    "circular_import_toplevel", # Python-specific
}

def analyze_file(parsed_file: ParsedFile) -> list[RiskFlag]:
    """
    Return risk flags untuk file. Language-aware:
    - Language-agnostic risks: semua bahasa
    - Python-only risks: hanya kalau parsed_file.language == "python"
    """
    flags = []

    # Universal risks
    flags.extend(_check_dead_code(parsed_file))
    flags.extend(_check_unused_parameters(parsed_file))

    # Python-only
    if parsed_file.language == "python":
        flags.extend(_check_none_return(parsed_file))
        flags.extend(_check_uncaught_exceptions(parsed_file))
        flags.extend(_check_type_annotations(parsed_file))
        flags.extend(_check_star_imports(parsed_file))
        flags.extend(_check_circular_imports(parsed_file))

    # TypeScript/JavaScript specific
    if parsed_file.language in ("typescript", "javascript"):
        flags.extend(_check_ts_any_type(parsed_file))  # stub — Phase 4 ext

    return flags
```

---

## 5. Frontend Update — Unsupported File Node

Ketika grammar tidak available dan file di-skip, graph harus tetap render tapi file tersebut muncul sebagai node dengan visual yang jelas berbeda.

**Data contract tambahan** — graph JSON perlu field baru:

```json
{
  "nodes": [
    {
      "id": "src/main.cpp",
      "type": "file",
      "language": "cpp",
      "supported": false,
      "unsupported_reason": "grammar_unavailable",
      ...
    }
  ]
}
```

**Frontend (graph.js) — visual untuk unsupported node:**

```javascript
// Unsupported node: dashed border, opacity 50%, warna abu gelap
// Hover tooltip: "C++ tidak didukung — grammar tidak tersedia"
// Tidak bisa diklik (tidak ada side panel untuk unsupported files)
```

Ini satu-satunya frontend change di Phase 4 — hanya tambah visual state baru, tidak mengubah logic yang ada.

---

## 6. pyproject.toml Update

```toml
[project.optional-dependencies]
# Existing
ai = ["anthropic>=0.28.0", "openai>=1.30.0", "detect-secrets>=1.5.0"]

# Baru — tree-sitter-language-pack (306 bahasa, code intelligence API)
multilang = [
    "tree-sitter-language-pack>=1.12.0,<2.0.0",
]

# Install semua sekaligus
full = [
    "anthropic>=0.28.0",
    "openai>=1.30.0",
    "detect-secrets>=1.5.0",
    "tree-sitter-language-pack>=1.12.0,<2.0.0",
]

# Dev — tambah tree-sitter untuk test
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "tree-sitter-language-pack>=1.12.0,<2.0.0",
]
```

User install experience:

```bash
pip install graps              # Python only (ASTParser), tanpa tree-sitter
pip install graps[multilang]   # 306 bahasa via tree-sitter-language-pack
pip install graps[full]        # semua feature: multilang + AI
pip install graps[ai]          # hanya AI layer, tidak ada multilang
```

---

## 7. ProcessResult → ParsedFile Mapping Reference

Diverifikasi dari `docs/reference/api-python.md` (v1.12.1, 2026-07-01).

### ProcessResult fields → ParsedFile fields

| ProcessResult field | Type | ParsedFile field | Mapping |
|---------------------|------|------------------|---------|
| `language` | `str` | `language` | direct |
| `structure` | `list[StructureItem]` | `functions` | flatten + filter FUNCTION/METHOD |
| `structure` | `list[StructureItem]` | `classes` | filter CLASS, extract methods from children |
| `imports` | `list[ImportInfo]` | `imports` | map ImportInfo → ParsedImport |
| `exports` | `list[ExportInfo]` | `exported_names` | extract .name |
| `diagnostics` | `list[Diagnostic]` | `warnings` | format "line N: message" |
| — | — | `constants` | `[]` — not in ProcessResult (Phase 4 ext) |
| — | — | `file_modified_at` | from `path.stat().st_mtime` |

### StructureItem → ParsedFunction

| StructureItem field | ParsedFunction field | Mapping |
|---------------------|----------------------|---------|
| `name` | `name` | direct |
| `visibility` | `is_private` | invert: pub/public → False, private/internal → True |
| `span.start_line` | `line_start` | +1 (tree-sitter 0-indexed) |
| `span.end_line` | `line_end` | +1 |
| `decorators` | `decorators` | direct |
| `signature` | `params` / `returns` | parse later (Phase 4 ext) |
| `children` | — | recurse: flatten nested FUNCTION/METHOD |
| `body_span` | — | not mapped (not needed) |

### ImportInfo → ParsedImport

| ImportInfo field | ParsedImport field | Mapping |
|------------------|--------------------|---------|
| `source` | `target` | direct |
| `is_wildcard` | `is_star` | direct |
| `span.start_line` | `lineno` | +1 |
| `items` | — | not mapped (not in ParsedImport) |
| `alias` | — | not mapped (not in ParsedImport) |

### ExportInfo → exported_names

| ExportInfo field | ParsedFile field | Mapping |
|-----------------|------------------|---------|
| `name` | `exported_names[i]` | append |

### callers / callees

**Tidak ada di ProcessResult.** `process()` hanya analyze satu file. Cross-file relationship tetap diisi oleh `graph_builder.py` via import resolution. Jangan ada yang assume `process()` solve ini.

---

## 8. Offline Behavior (Verified)

```
First run:
  process(source, config) for new language
    → library detects grammar not in local cache
    → downloads from GitHub releases (~per-grammar, small)
    → caches in local directory (platform-specific)
    → parses + returns ProcessResult

Subsequent runs (offline):
  process(source, config) for same language
    → grammar found in local cache
    → parses + returns ProcessResult
    → NO network needed
```

**`prefetch()` available** untuk pre-warm cache sebelum scan:
```python
from tree_sitter_language_pack import prefetch
prefetch(["python", "typescript", "javascript", "go", "rust"])
```

**Download failure** → `process()` raises `Error.Download` → adapter catches → returns `None` → file muncul sebagai unsupported node.

---

## 9. Test Fixtures yang Dibutuhkan

```
tests/fixtures/
  ├── typescript/
  │   ├── simple.ts           # basic function + import
  │   ├── arrow_functions.ts  # const foo = () => {}
  │   ├── class_methods.ts    # class dengan methods
  │   └── export_patterns.ts  # named export, default export
  ├── javascript/
  │   ├── simple.js
  │   └── commonjs.js         # require() + module.exports
  ├── go/
  │   ├── simple.go           # package main, func main()
  │   └── unexported.go       # lowercase function (unexported)
  └── rust/
      ├── simple.rs           # fn main()
      └── pub_private.rs      # pub fn vs fn (visibility)
```

---

## 10. Checklist Ringkas

```
[ ] tree_sitter_parser.py — TreeSitterParser (adapter only)
    [ ] parse_file() — detect_language_from_path → process() → map to ParsedFile
    [ ] _extract_functions() — flatten StructureItem tree
    [ ] _extract_imports() — map ImportInfo → ParsedImport
    [ ] _extract_classes() — filter CLASS from StructureItem
    [ ] _extract_exports() — map ExportInfo → exported_names
    [ ] _detect_is_private() — visibility + naming convention
[ ] cli.py update          — _discover() multi-ext + _parse_file() dispatch
[ ] risk_analyzer.py       — language-aware, Python-only flags di-guard
[ ] graph.js               — unsupported node visual state
[ ] pyproject.toml         — [multilang], [full], [dev] optional deps
[ ] Test fixtures           — TS, JS, Go, Rust
[ ] tests/test_tree_sitter_parser.py — unit tests per bahasa
[ ] Full test suite pass, zero regresi dari existing tests
```

---

## 11. Yang TIDAK Termasuk Phase 4

```
✗ Constants extraction — ProcessResult tidak provide; Phase 4 extension
✗ params/returns parsing dari signature string — Phase 4 extension
✗ is_conditional/is_dynamic untuk non-Python imports — Phase 4 extension
✗ risk_analyzer TS-specific checks (_check_ts_any_type) — stub dulu
✗ SaaS / container deployment — masa depan
✗ Frontend search update untuk filter by language — backlog
✗ Rewrite ke Go/Rust — tidak disentuh sampai ada user complaint + performance data
```

---

## 12. Verifikasi Library (2026-07-01)

| Item | Status |
|------|--------|
| `process(source, config) → ProcessResult` | ✅ Confirmed in API docs |
| `ProcessResult.structure: list[StructureItem]` | ✅ Confirmed |
| `StructureItem.children` (nested tree) | ✅ Confirmed — adapter must flatten |
| `ImportInfo.source/items/alias/is_wildcard` | ✅ Confirmed |
| `ExportInfo.name/kind` | ✅ Confirmed |
| `ProcessConfig(language=, structure=, imports=, exports=)` | ✅ Confirmed |
| `detect_language_from_path(path) → str|None` | ✅ Confirmed |
| `prefetch(languages)` untuk pre-warm | ✅ Confirmed |
| Offline after first download | ✅ Confirmed — cached locally |
| Wheel size Linux x86_64 | ✅ 2.3 MB |
| callers/callees in ProcessResult | ❌ Not present — graph_builder job |
| MIT license | ✅ Confirmed |

---

*PHASE4.md — reference BLUEPRINT.md §4 untuk BaseParser interface spec.*
*Dibuat: 2026-06-28. Revised: 2026-07-01 — switch to tree-sitter-language-pack.*
