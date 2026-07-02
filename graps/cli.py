"""CLI entry point graps (lihat BLUEPRINT.md §6).

Flow utama: scan .py rekursif → build_graph → create_app → uvicorn + auto-open
browser. Sengaja flat — satu fungsi `main`, satu helper `_build` agar
self-check bisa memanggil tanpa menjalankan server.

ponytail: tidak pakai Rich/Click/colorama. typer.echo + print biasa cukup.
"""

from __future__ import annotations

import errno
import logging
import os
import socket
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Any

import typer
import uvicorn

# ponytail: dipanggil sebagai `python graps/cli.py` (self-check) butuh repo
# root di sys.path. No-op untuk `python -m graps.cli`.
if __name__ == "__main__":
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graps import __version__  # noqa: E402
from graps.scanner import ParsedFile  # noqa: E402
from graps.scanner.ast_parser import safe_parse
from graps.scanner.graph_builder import build_graph
from graps.scanner.tree_sitter_parser import TreeSitterParser  # Phase 4
from graps.server.app import create_app  # noqa: E402

app = typer.Typer(add_completion=False)

logger = logging.getLogger(__name__)

_DEFAULT_EXCLUDES = ("__pycache__", ".git", ".venv", "venv", "node_modules")


def _discover(path: Path, exclude: set[str]) -> list[Path]:
    """Cari file rekursif yang didukung tree-sitter-language-pack (306 bahasa).

    Fallback ke ``*.py`` kalau library tidak terinstall.
    """
    try:
        from tree_sitter_language_pack import detect_language_from_path
        use_tslp = True
    except ImportError:
        use_tslp = False

    files: list[Path] = []
    for p in path.rglob("*"):
        if not p.is_file():
            continue
        if set(p.parts) & exclude:
            continue
        if use_tslp:
            if detect_language_from_path(str(p)) is not None:
                files.append(p)
        elif p.suffix == ".py":
            files.append(p)
    return files


def _parse_file(path: Path, root: Path) -> ParsedFile | None:
    """Dispatch parser per file.

    TreeSitterParser dulu. Kalau gagal dan file .py → fallback ke ASTParser.
    Non-Python tanpa fallback → None (unsupported).
    """
    ts_parser = TreeSitterParser()
    result = ts_parser.parse_file(path, root)

    if result is not None:
        return result

    if path.suffix == ".py":
        logger.debug("tree-sitter failed for %s, falling back to ASTParser", path)
        return safe_parse(path)

    return None


def _build(path: Path, exclude: set[str]) -> dict[str, Any]:
    """Discover + parse + build_graph. Dipisah supaya self-check bisa panggil tanpa server."""
    files = _discover(path, exclude)
    results = [r for r in (_parse_file(p, path) for p in files) if r is not None]
    return build_graph(results, root=path)


def _count_risks(graph: dict[str, Any]) -> dict[str, int]:
    """Hitung risk per criticality dari graph (file-level risks)."""
    counts = {"high": 0, "medium": 0, "low": 0}
    for node in graph.get("nodes", []):
        for r in node.get("risks", []) or []:
            sev = (r.get("severity") or r.get("level") or "").lower()
            if sev in counts:
                counts[sev] += 1
    return counts


def _port_free(port: int) -> bool:
    """True kalau bisa bind 127.0.0.1:port (pre-flight check)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"graps v{__version__}")
        raise typer.Exit(0)


def _warn_if_cache_not_ignored(root: Path) -> None:
    """Warning non-blocking kalau ``.graps/`` tidak di-ignore di ``root/.gitignore``.

    Hanya typer.echo, tidak pernah sys.exit — cache berisi ringkasan AI dari
    source code, kalau tidak di-ignore bisa ter-commit ke Git (BLUEPRINT H-03).
    """
    gitignore = root / ".gitignore"
    if gitignore.exists():
        try:
            content = gitignore.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return  # unreadable → skip warning silently
        if ".graps" not in content and ".graps/" not in content:
            typer.echo(
                "  ⚠ .graps/ belum ada di .gitignore — "
                "cache bisa berisi ringkasan AI dari source code kamu. "
                "Tambahkan '.graps/' ke .gitignore?"
            )


@app.command()
def main(
    path: str = typer.Argument(".", help="Direktori yang akan di-scan"),
    port: int = typer.Option(8765, "--port", help="Port HTTP server"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Jangan auto-open browser"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Pakai cache sementara (dihapus OS)"),
    exclude: list[str] = typer.Option(  # noqa: B008
        None, "--exclude", help="Pattern direktori yang di-skip (boleh berulang)",
    ),
    ai_provider: str = typer.Option(
        None, "--ai-provider", help="anthropic|openai — paksa satu provider",
    ),
    version: bool = typer.Option(  # noqa: ARG001
        False, "--version", callback=_version_callback, is_eager=True,
        help="Tampilkan versi dan keluar",
    ),
) -> None:
    """Scan PATH untuk file Python, jalankan server lokal + buka browser."""
    root = Path(path).resolve()

    typer.echo(f"graps v{__version__}")
    typer.echo("")
    typer.echo(f"  Scanning {root}...")

    # Validasi PATH.
    if not root.exists() or not root.is_dir():
        typer.echo(f"  ✗ Cannot read directory {path} — not found or not a directory")
        raise typer.Exit(1)
    if not os.access(root, os.R_OK):
        typer.echo(f"  ✗ Cannot read directory {path} — permission denied")
        raise typer.Exit(1)

    # Startup warning: cache .graps/ harus di-gitignore (BLUEPRINT H-03).
    _warn_if_cache_not_ignored(root)

    excl: set[str] = set(_DEFAULT_EXCLUDES)
    if exclude:
        # Buang trailing slash supaya "tests/" cocok dengan parts "tests".
        excl.update(e.rstrip("/").rstrip("\\") for e in exclude)

    files = _discover(root, excl)
    if not files:
        typer.echo(f"  ✗ No supported files found in {path}")
        raise typer.Exit(1)

    # Scan + build.
    results = [r for r in (_parse_file(p, root) for p in files) if r is not None]
    graph = build_graph(results, root=root)

    meta = graph.get("meta", {})
    files_n = meta.get("total_files", len(results))
    funcs_n = meta.get("total_functions", sum(len(r.functions) for r in results))
    edges_n = meta.get("total_edges", len(graph.get("edges", [])))
    risks = _count_risks(graph)

    typer.echo(f"  ├── Found {files_n} files")
    typer.echo(f"  ├── Found {funcs_n} functions")
    typer.echo(f"  ├── Found {edges_n} import relationships")
    typer.echo(
        f"  └── Risk analysis complete: {risks['high']} high, "
        f"{risks['medium']} medium, {risks['low']} low"
    )
    typer.echo("")

    # AI provider env masking. get_provider order Anthropic-first → ini cara
    # paling lazy untuk memaksa openai.
    if ai_provider == "openai":
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if not os.environ.get("OPENAI_API_KEY"):
            typer.echo("  ! OPENAI_API_KEY tidak di-set — AI summary akan disabled")
    elif ai_provider == "anthropic":
        os.environ.pop("OPENAI_API_KEY", None)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            typer.echo("  ! ANTHROPIC_API_KEY tidak di-set — AI summary akan disabled")

    # Cache path. --no-cache → tempfile OS-unik per-run (mkstemp).
    # ponytail: mkstemp lebih simple dari TemporaryDirectory context manager
    # karena server.run() block — kita gak punya tempat clean up ergonomis.
    # OS akan bersihkan /tmp eventually.
    cache_path: Path | None
    if no_cache:
        fd, name = tempfile.mkstemp(suffix=".json", prefix="graps-nocache-")
        os.close(fd)
        cache_path = Path(name)
    else:
        cache_path = None  # create_app pakai DEFAULT_CACHE_PATH

    # Pre-flight port check.
    if not _port_free(port):
        typer.echo(f"  ✗ Port {port} already in use. Try: graps . --port {port + 1}")
        raise typer.Exit(1)

    fastapi_app = create_app(graph, port=port, cache_path=cache_path, scan_root=path)

    typer.echo(f"  Server running at http://localhost:{port}")
    if not no_browser:
        typer.echo("  Opening browser...")
        timer = threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}"))
        timer.daemon = True  # ponytail: jangan block exit kalau server.run() gagal (Finding 6)
        timer.start()
    typer.echo("  Press Ctrl+C to stop")
    typer.echo("")

    config = uvicorn.Config(
        fastapi_app, host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        typer.echo("")
        typer.echo("  Stopped.")
        raise typer.Exit(0)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            typer.echo(f"  ✗ Port {port} already in use. Try: graps . --port {port + 1}")
            raise typer.Exit(1)
        raise


if __name__ == "__main__":
    # Self-check minimal — tidak menjalankan server beneran.
    from typer.testing import CliRunner

    # 1. Import + Typer instance.
    assert isinstance(app, typer.Typer)

    # 2. --version exit 0 + output mengandung "graps v".
    runner = CliRunner()
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0, (r.exit_code, r.output)
    assert "graps v" in r.output, r.output

    # 3. Fixture dir kecil → _build hasilkan graph valid.
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "x.py").write_text("def foo(): pass\n")
        (tdp / "__pycache__").mkdir()
        (tdp / "__pycache__" / "ignored.py").write_text("syntax ( error\n")

        files = _discover(tdp, set(_DEFAULT_EXCLUDES))
        assert len(files) == 1, files  # __pycache__ ter-skip

        graph = _build(tdp, set(_DEFAULT_EXCLUDES))
        assert "nodes" in graph and isinstance(graph["nodes"], list), graph
        assert graph["meta"]["total_files"] == 1, graph["meta"]
        assert graph["meta"]["total_functions"] == 1, graph["meta"]

    # 4. Empty dir → exit code != 0.
    with tempfile.TemporaryDirectory() as td:
        r = runner.invoke(app, [td, "--no-browser"])
        assert r.exit_code != 0, (r.exit_code, r.output)
        assert "No supported files" in r.output, r.output

    # 5. PATH tidak ada → exit code != 0.
    r = runner.invoke(app, ["/path/yang/pasti/tidak/ada/xyz123", "--no-browser"])
    assert r.exit_code != 0, (r.exit_code, r.output)

    # 6. _count_risks tahan input kosong / None.
    assert _count_risks({"nodes": []}) == {"high": 0, "medium": 0, "low": 0}
    assert _count_risks({"nodes": [{"risks": None}]}) == {"high": 0, "medium": 0, "low": 0}
    assert _count_risks(
        {"nodes": [{"risks": [{"severity": "high"}, {"level": "MEDIUM"}]}]}
    ) == {"high": 1, "medium": 1, "low": 0}

    # 7. _port_free konsisten dengan socket-bind manual.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    busy_port = s.getsockname()[1]
    assert _port_free(busy_port) is False
    s.close()

    print("cli.py self-check OK")
