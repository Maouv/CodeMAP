# Python Packaging Review — CodeMAP

> Project: `codemap` — Interactive visual dependency graph for Python codebases  
> Source: Planning session + architect review (2026-06-27)  
> Scope: PyPI distribution, CLI entry point, frontend asset bundling

---

## Project Context

**codemap** adalah CLI tool open source yang membantu semi-technical vibe coders memahami codebase melalui interactive visual dependency graph di localhost browser.

**Stack:**
- Python AST parsing (built-in `ast` module)
- FastAPI + Uvicorn (backend + static serving)
- D3.js force-directed graph (frontend)
- Typer (CLI)
- BYOK AI layer (Anthropic / OpenAI, optional)

**Distribution target:** `pip install codemap` via PyPI.

---

## Sesi 1 — Initial Packaging Plan

### `pyproject.toml` — Konfigurasi Lengkap

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
authors = [
  { name = "Your Name", email = "you@example.com" }
]
keywords = ["codebase", "visualization", "ast", "dependency-graph", "cli"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Console",
  "Environment :: Web Environment",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Software Development :: Libraries :: Python Modules",
  "Topic :: Utilities",
]

dependencies = [
  "typer>=0.12.0",
  "fastapi>=0.111.0",
  "uvicorn[standard]>=0.30.0",
]

[project.optional-dependencies]
anthropic = ["anthropic>=0.28.0"]
openai = ["openai>=1.30.0"]
ai = ["anthropic>=0.28.0", "openai>=1.30.0"]
dev = [
  "pytest>=8.0.0",
  "pytest-asyncio>=0.23.0",
  "httpx>=0.27.0",
  "ruff>=0.4.0",
  "mypy>=1.10.0",
]

[project.scripts]
codemap = "codemap.cli:app"

[project.urls]
Homepage = "https://github.com/yourname/codemap"
Issues = "https://github.com/yourname/codemap/issues"

[tool.hatch.build.targets.wheel]
packages = ["codemap"]

# Salin frontend/ dari root repo → codemap/frontend/ di dalam wheel
[tool.hatch.build.targets.wheel.force-include]
"frontend" = "codemap/frontend"

[tool.hatch.build.targets.sdist]
include = [
  "codemap/",
  "frontend/",
  "tests/",
  "pyproject.toml",
  "README.md",
  "LICENSE",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.mypy]
python_version = "3.10"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### Keputusan Packaging Utama

**Build backend: Hatchling** (bukan setuptools).
- pyproject.toml-native, zero legacy config
- `force-include` untuk bundle `frontend/` ke dalam wheel
- Cleanest path untuk ship static files bersama Python package

**Tiga tier dependency:**

| Tier | Install command | Isi |
|------|----------------|-----|
| Core | `pip install codemap` | Typer + FastAPI + Uvicorn — no AI |
| Anthropic | `pip install codemap[anthropic]` | Tambah `anthropic` SDK |
| OpenAI | `pip install codemap[openai]` | Tambah `openai` SDK |
| Both | `pip install codemap[ai]` | Kedua SDK |
| Dev | `pip install codemap[dev]` | Test + lint tools |

Sesuai desain BYOK — AI libraries tidak dipaksakan ke user.

### Struktur Project (flat layout)

```
codemap/
├── codemap/
│   ├── __init__.py          # version = "0.1.0"
│   ├── cli.py
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── ast_parser.py
│   │   ├── resolver.py
│   │   ├── risk_analyzer.py
│   │   └── graph_builder.py
│   ├── server/
│   │   ├── __init__.py
│   │   └── app.py
│   └── ai/
│       ├── __init__.py
│       ├── provider.py
│       └── cache.py
├── frontend/                # source of truth saat development
│   ├── index.html
│   ├── graph.js
│   ├── panel.js
│   └── style.css
├── tests/
│   ├── fixtures/
│   └── test_ast_parser.py
├── pyproject.toml
├── README.md
└── LICENSE
```

### `__init__.py` — Expose version

```python
# codemap/__init__.py
__version__ = "0.1.0"
```

### `.gitignore` untuk packaging artifacts

```
dist/
*.egg-info/
.codemap/
__pycache__/
.venv/
```

### Publishing ke PyPI

```bash
# Build
pip install build twine
python -m build

# Check
twine check dist/*

# TestPyPI dulu
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ codemap

# PyPI production
twine upload dist/*
```

**Trusted Publishing via GitHub Actions (recommended — tanpa API token di CI):**

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  push:
    tags: ["v*"]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build && python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

---

## Sesi 2 — Tiga Pertanyaan Lanjutan

---

### Q1: `pyproject.toml` Setup yang Benar untuk Include Frontend Files

Ada dua bagian yang harus benar sekaligus: **build target** (apa yang masuk wheel) dan bahwa file non-`.py` ikut terbundle.

```toml
[tool.hatch.build.targets.wheel]
packages = ["codemap"]

# Salin frontend/ dari root repo → codemap/frontend/ di dalam wheel
[tool.hatch.build.targets.wheel.force-include]
"frontend" = "codemap/frontend"

[tool.hatch.build.targets.sdist]
include = [
  "codemap/",
  "frontend/",
  "tests/",
  "pyproject.toml",
  "README.md",
  "LICENSE",
]
```

**Kenapa `force-include`?**

Hatchling secara default hanya bundle direktori yang ada di dalam `packages` — yaitu `codemap/`. Direktori `frontend/` ada di root repo, di luar `codemap/`, jadi tidak ikut otomatis. `force-include` memetakan:

```
"frontend"  →  "codemap/frontend"
 (source)       (tujuan di dalam wheel)
```

**Verifikasi setelah build — wajib dilakukan:**

```bash
python -m build
unzip -l dist/codemap-0.1.0-py3-none-any.whl | grep frontend
```

Output yang harus muncul:
```
codemap/frontend/index.html
codemap/frontend/graph.js
codemap/frontend/panel.js
codemap/frontend/style.css
```

Kalau baris-baris itu tidak muncul → static files tidak ikut → server 404 semua halaman, tapi `pip install` tetap sukses. **Silent failure yang susah di-debug.**

---

### Q2: Entry Point CLI via `[project.scripts]`

```toml
[project.scripts]
codemap = "codemap.cli:app"
```

Format: `"nama-command" = "dotted.module.path:callable"`

- `codemap` = nama command yang bisa dipanggil di terminal
- `codemap.cli` = module path (`codemap/cli.py`)
- `app` = objek Typer yang di-expose di module itu

**Implementasi `codemap/cli.py`:**

```python
import typer
from codemap import __version__

app = typer.Typer(help="Interactive visual dependency graph for Python codebases.")

def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"codemap v{__version__}")
        raise typer.Exit()

@app.command()
def main(
    path: str = typer.Argument(".", help="Directory to scan"),
    port: int = typer.Option(8765, help="Port to serve on"),
    exclude: list[str] = typer.Option([], help="Directories to exclude"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't auto-open browser"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Force re-scan"),
    ai_provider: str | None = typer.Option(None, help="AI provider: anthropic or openai"),
    version: bool = typer.Option(None, "--version", callback=version_callback, is_eager=True),
) -> None:
    """Scan a Python codebase and serve an interactive dependency graph."""
    ...
```

Setelah `pip install codemap`, pip membuat shim executable di:
- Linux/macOS: `~/.venv/bin/codemap`
- Windows: `Scripts\codemap.exe`

User cukup ketik `codemap .` — tidak perlu `python -m codemap`.

**Hal yang sering salah:** pastikan `app` adalah Typer instance yang di-export di level module, bukan nested di dalam fungsi atau `if __name__ == "__main__"` block.

---

### Q3: Cara Bundle Frontend Assets supaya Ikut saat `pip install`

Ini yang paling non-trivial. Ada tiga bagian yang semuanya harus benar.

#### Bagian A — Struktur direktori di dalam wheel

Setelah `pip install`, file harus ada di dalam direktori `codemap/` yang terinstall:

```
# Di dalam wheel / setelah install:
site-packages/
└── codemap/
    ├── __init__.py
    ├── cli.py
    ├── scanner/
    ├── server/
    │   └── app.py
    ├── ai/
    └── frontend/          ← harus ada di sini
        ├── index.html
        ├── graph.js
        ├── panel.js
        └── style.css
```

#### Bagian B — Referensi path di runtime yang benar

**Jangan pernah hardcode path atau pakai `os.getcwd()`.**

```python
# codemap/server/app.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# __file__ = path ke app.py yang terinstall
# .parent   = codemap/server/
# .parent.parent = codemap/
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="static"
)
```

`Path(__file__).parent.parent / "frontend"` bekerja di semua kondisi:
- Dev mode: `pip install -e .`
- Installed via PyPI: `pip install codemap`
- Zipapp / PEX bundle

#### Bagian C — Alternatif: `importlib.resources` (Python 3.9+)

Untuk kasus yang lebih complex atau jika wheel dikompres (zip-safe):

```python
# codemap/server/app.py
import importlib.resources
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# Cara future-proof untuk Python 3.9+
frontend_ref = importlib.resources.files("codemap") / "frontend"
FRONTEND_DIR = Path(str(frontend_ref))

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
```

Untuk `codemap` (tool CLI lokal), `Path(__file__)` approach sudah cukup dan lebih readable. `importlib.resources` lebih relevan kalau package punya kemungkinan dijalankan dari zip archive.

#### Ringkasan alur lengkap

```
Repo (development)          Wheel (distribusi)           Installed (user)
──────────────────          ──────────────────           ────────────────
frontend/                   codemap/frontend/            codemap/frontend/
  index.html      ──►         index.html        ──►       index.html
  graph.js        force-      graph.js          pip       graph.js
  panel.js        include     panel.js          install   panel.js
  style.css                   style.css                   style.css

codemap/                    codemap/                     codemap/
  server/app.py  ──►          server/app.py    ──►        server/app.py
                              (Path(__file__)              (path resolved
                               resolves correctly)          at runtime ✓)
```

#### Checklist verifikasi end-to-end

```bash
# 1. Build wheel
python -m build

# 2. Cek isi wheel — frontend harus ada
unzip -l dist/codemap-0.1.0-py3-none-any.whl | grep frontend

# 3. Install ke fresh venv
python -m venv /tmp/test-codemap
/tmp/test-codemap/bin/pip install dist/codemap-0.1.0-py3-none-any.whl

# 4. Jalankan dan cek tidak ada 404
/tmp/test-codemap/bin/codemap . --no-browser &
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/
# Harus: 200
```

---

## Catatan dari Architect Review

Tiga concern teknis dari review arsitektur yang relevan dengan packaging:

**AST Parser** — file corrupt atau syntax error tidak boleh crash seluruh pipeline. Setiap `ast.parse()` harus dibungkus `try/except`, dengan encoding detection via `tokenize.detect_encoding()` dan max file size guard (>1MB skip). Ini harus ditestable secara unit — pastikan `tests/fixtures/` berisi sample files untuk edge cases.

**Static Serving** — `StaticFiles` dari Starlette tidak ada caching bawaan. Untuk production, nginx di depan FastAPI untuk static files. Untuk dev (yang adalah use case utama `codemap`), cukup dengan `Path(__file__)` approach di atas.

**D3 Performance** — SVG renderer aman sampai ~500 node. Kalau codebase target user bisa >500 file, pertimbangkan Canvas renderer sejak Phase 1. Tidak ada implikasi packaging — ini murni frontend concern.

---

*Document generated: 2026-06-27*  
*Based on: CodeMAP-main/handoff.md + CodeMAP-main/architect-review.md + packaging review session*
