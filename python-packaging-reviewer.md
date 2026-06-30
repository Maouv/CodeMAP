# Python Packaging Review — graps

> Project: `graps` — Interactive visual dependency graph for Python codebases  
> Source: Planning session + architect review (2026-06-27)  
> Scope: PyPI distribution, CLI entry point, frontend asset bundling

---

## Project Context

**graps** adalah CLI tool open source yang membantu semi-technical vibe coders memahami codebase melalui interactive visual dependency graph di localhost browser.

**Stack:**
- Python AST parsing (built-in `ast` module)
- FastAPI + Uvicorn (backend + static serving)
- D3.js force-directed graph (frontend)
- Typer (CLI)
- BYOK AI layer (Anthropic / OpenAI, optional)

**Distribution target:** `pip install graps` via PyPI.

---

## Sesi 1 — Initial Packaging Plan

### `pyproject.toml` — Konfigurasi Lengkap

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "graps"
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
graps = "graps.cli:app"

[project.urls]
Homepage = "https://github.com/yourname/graps"
Issues = "https://github.com/yourname/graps/issues"

[tool.hatch.build.targets.wheel]
packages = ["graps"]

# Salin frontend/ dari root repo → graps/frontend/ di dalam wheel
[tool.hatch.build.targets.wheel.force-include]
"frontend" = "graps/frontend"

[tool.hatch.build.targets.sdist]
include = [
  "graps/",
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
| Core | `pip install graps` | Typer + FastAPI + Uvicorn — no AI |
| Anthropic | `pip install graps[anthropic]` | Tambah `anthropic` SDK |
| OpenAI | `pip install graps[openai]` | Tambah `openai` SDK |
| Both | `pip install graps[ai]` | Kedua SDK |
| Dev | `pip install graps[dev]` | Test + lint tools |

Sesuai desain BYOK — AI libraries tidak dipaksakan ke user.

### Struktur Project (flat layout)

```
graps/
├── graps/
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
# graps/__init__.py
__version__ = "0.1.0"
```

### `.gitignore` untuk packaging artifacts

```
dist/
*.egg-info/
.graps/
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
pip install --index-url https://test.pypi.org/simple/ graps

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
packages = ["graps"]

# Salin frontend/ dari root repo → graps/frontend/ di dalam wheel
[tool.hatch.build.targets.wheel.force-include]
"frontend" = "graps/frontend"

[tool.hatch.build.targets.sdist]
include = [
  "graps/",
  "frontend/",
  "tests/",
  "pyproject.toml",
  "README.md",
  "LICENSE",
]
```

**Kenapa `force-include`?**

Hatchling secara default hanya bundle direktori yang ada di dalam `packages` — yaitu `graps/`. Direktori `frontend/` ada di root repo, di luar `graps/`, jadi tidak ikut otomatis. `force-include` memetakan:

```
"frontend"  →  "graps/frontend"
 (source)       (tujuan di dalam wheel)
```

**Verifikasi setelah build — wajib dilakukan:**

```bash
python -m build
unzip -l dist/graps-0.1.0-py3-none-any.whl | grep frontend
```

Output yang harus muncul:
```
graps/frontend/index.html
graps/frontend/graph.js
graps/frontend/panel.js
graps/frontend/style.css
```

Kalau baris-baris itu tidak muncul → static files tidak ikut → server 404 semua halaman, tapi `pip install` tetap sukses. **Silent failure yang susah di-debug.**

---

### Q2: Entry Point CLI via `[project.scripts]`

```toml
[project.scripts]
graps = "graps.cli:app"
```

Format: `"nama-command" = "dotted.module.path:callable"`

- `graps` = nama command yang bisa dipanggil di terminal
- `graps.cli` = module path (`graps/cli.py`)
- `app` = objek Typer yang di-expose di module itu

**Implementasi `graps/cli.py`:**

```python
import typer
from graps import __version__

app = typer.Typer(help="Interactive visual dependency graph for Python codebases.")

def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"graps v{__version__}")
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

Setelah `pip install graps`, pip membuat shim executable di:
- Linux/macOS: `~/.venv/bin/graps`
- Windows: `Scripts\graps.exe`

User cukup ketik `graps .` — tidak perlu `python -m graps`.

**Hal yang sering salah:** pastikan `app` adalah Typer instance yang di-export di level module, bukan nested di dalam fungsi atau `if __name__ == "__main__"` block.

---

### Q3: Cara Bundle Frontend Assets supaya Ikut saat `pip install`

Ini yang paling non-trivial. Ada tiga bagian yang semuanya harus benar.

#### Bagian A — Struktur direktori di dalam wheel

Setelah `pip install`, file harus ada di dalam direktori `graps/` yang terinstall:

```
# Di dalam wheel / setelah install:
site-packages/
└── graps/
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
# graps/server/app.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# __file__ = path ke app.py yang terinstall
# .parent   = graps/server/
# .parent.parent = graps/
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="static"
)
```

`Path(__file__).parent.parent / "frontend"` bekerja di semua kondisi:
- Dev mode: `pip install -e .`
- Installed via PyPI: `pip install graps`
- Zipapp / PEX bundle

#### Bagian C — Alternatif: `importlib.resources` (Python 3.9+)

Untuk kasus yang lebih complex atau jika wheel dikompres (zip-safe):

```python
# graps/server/app.py
import importlib.resources
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# Cara future-proof untuk Python 3.9+
frontend_ref = importlib.resources.files("graps") / "frontend"
FRONTEND_DIR = Path(str(frontend_ref))

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
```

Untuk `graps` (tool CLI lokal), `Path(__file__)` approach sudah cukup dan lebih readable. `importlib.resources` lebih relevan kalau package punya kemungkinan dijalankan dari zip archive.

#### Ringkasan alur lengkap

```
Repo (development)          Wheel (distribusi)           Installed (user)
──────────────────          ──────────────────           ────────────────
frontend/                   graps/frontend/            graps/frontend/
  index.html      ──►         index.html        ──►       index.html
  graph.js        force-      graph.js          pip       graph.js
  panel.js        include     panel.js          install   panel.js
  style.css                   style.css                   style.css

graps/                    graps/                     graps/
  server/app.py  ──►          server/app.py    ──►        server/app.py
                              (Path(__file__)              (path resolved
                               resolves correctly)          at runtime ✓)
```

#### Checklist verifikasi end-to-end

```bash
# 1. Build wheel
python -m build

# 2. Cek isi wheel — frontend harus ada
unzip -l dist/graps-0.1.0-py3-none-any.whl | grep frontend

# 3. Install ke fresh venv
python -m venv /tmp/test-graps
/tmp/test-graps/bin/pip install dist/graps-0.1.0-py3-none-any.whl

# 4. Jalankan dan cek tidak ada 404
/tmp/test-graps/bin/graps . --no-browser &
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/
# Harus: 200
```

---

## Catatan dari Architect Review

Tiga concern teknis dari review arsitektur yang relevan dengan packaging:

**AST Parser** — file corrupt atau syntax error tidak boleh crash seluruh pipeline. Setiap `ast.parse()` harus dibungkus `try/except`, dengan encoding detection via `tokenize.detect_encoding()` dan max file size guard (>1MB skip). Ini harus ditestable secara unit — pastikan `tests/fixtures/` berisi sample files untuk edge cases.

**Static Serving** — `StaticFiles` dari Starlette tidak ada caching bawaan. Untuk production, nginx di depan FastAPI untuk static files. Untuk dev (yang adalah use case utama `graps`), cukup dengan `Path(__file__)` approach di atas.

**D3 Performance** — SVG renderer aman sampai ~500 node. Kalau codebase target user bisa >500 file, pertimbangkan Canvas renderer sejak Phase 1. Tidak ada implikasi packaging — ini murni frontend concern.

---

*Document generated: 2026-06-27*  
*Based on: graps-main/handoff.md + graps-main/architect-review.md + packaging review session*
