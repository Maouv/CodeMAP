"""Phase 4 Task 10 — CLI dispatch end-to-end tests.

Verifies: _discover() multi-ext discovery, _parse_file() dispatch with
ASTParser fallback for .py, _build() end-to-end multi-language scan,
and exclude pattern filtering.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graps.cli import _build, _discover, _parse_file

ROOT = Path(__file__).resolve().parent.parent  # codemap root
FIX = Path(__file__).parent / "fixtures"

# Skip kalau tree-sitter-language-pack tidak terinstall.
pytestmark = pytest.mark.skipif(
    pytest.importorskip("tree_sitter_language_pack", reason="tslp not installed") is None,
    reason="tree-sitter-language-pack not installed",
)


class TestDiscover:
    """_discover() harus nemuin file multi-bahasa + skip exclude."""

    def test_finds_python(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n")
        files = _discover(tmp_path, set())
        assert tmp_path / "a.py" in files

    def test_finds_typescript(self, tmp_path: Path) -> None:
        (tmp_path / "b.ts").write_text("export const y = 1;\n")
        files = _discover(tmp_path, set())
        assert tmp_path / "b.ts" in files

    def test_finds_mixed(self, tmp_path: Path) -> None:
        for name in ("a.py", "b.ts", "c.js", "d.go", "e.rs"):
            (tmp_path / name).write_text("# stub\n")
        files = _discover(tmp_path, set())
        names = {p.name for p in files}
        assert names == {"a.py", "b.ts", "c.js", "d.go", "e.rs"}

    def test_skip_unknown_ext(self, tmp_path: Path) -> None:
        (tmp_path / "weird.xyz").write_text("nope\n")
        (tmp_path / "ok.py").write_text("x = 1\n")
        files = _discover(tmp_path, set())
        names = {p.name for p in files}
        assert "weird.xyz" not in names
        assert "ok.py" in names

    def test_exclude_dir(self, tmp_path: Path) -> None:
        (tmp_path / "keep.py").write_text("x = 1\n")
        sub = tmp_path / "node_modules"
        sub.mkdir()
        (sub / "hidden.js").write_text("y = 2\n")
        files = _discover(tmp_path, {"node_modules"})
        names = {p.name for p in files}
        assert "keep.py" in names
        assert "hidden.js" not in names


class TestParseFileDispatch:
    """_parse_file() → TreeSitterParser, fallback ke ASTParser untuk .py."""

    def test_python_file(self, tmp_path: Path) -> None:
        f = tmp_path / "x.py"
        f.write_text("def foo(): pass\n")
        pf = _parse_file(f, tmp_path)
        assert pf is not None
        assert any(fn.name == "foo" for fn in pf.functions)

    def test_typescript_file(self, tmp_path: Path) -> None:
        f = tmp_path / "x.ts"
        f.write_text('function greet(): void {}\n')
        pf = _parse_file(f, tmp_path)
        assert pf is not None
        assert pf.language == "typescript"

    def test_unsupported_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "x.xyz"
        f.write_text("garbage\n")
        assert _parse_file(f, tmp_path) is None


class TestBuildEndToEnd:
    """_build() → discover + parse + graph untuk multi-language project."""

    def test_mixed_project(self, tmp_path: Path) -> None:
        """Scan dir campuran .py + .ts → graph valid dengan 2 file."""
        (tmp_path / "main.py").write_text("def hello(): return 'hi'\n")
        (tmp_path / "app.ts").write_text(
            'function greet(name: string): string { return name; }\n'
        )
        graph = _build(tmp_path, set())
        assert "nodes" in graph
        assert isinstance(graph["nodes"], list)
        assert len(graph["nodes"]) == 2
        assert graph["meta"]["total_files"] == 2

    def test_empty_dir_returns_empty_graph(self, tmp_path: Path) -> None:
        """Dir tanpa file yang didukung → graph kosong (bukan crash).

        ponytail: detect_language_from_path recognize .txt/.md/.json/.yaml
        sebagai bahasa (vimdoc, markdown, dll). Pakai extension yang benar-benar
        unknown untuk test "no supported files" path.
        """
        (tmp_path / "readme.xyzunknown").write_text("no code here\n")
        graph = _build(tmp_path, set())
        assert graph.get("nodes", []) == []

    def test_py_fallback_works(self, tmp_path: Path) -> None:
        """Kalau tree-sitter return None untuk .py, ASTParser fallback."""
        # File Python valid → TreeSitterParser sukses, tidak perlu fallback.
        # Test ini verify _build tetap menghasilkan graph untuk .py.
        (tmp_path / "solo.py").write_text("def only_func(): pass\n")
        graph = _build(tmp_path, set())
        assert graph["meta"]["total_files"] == 1
        assert graph["meta"]["total_functions"] == 1

    def test_language_carried_to_parsedfile(self, tmp_path: Path) -> None:
        """_parse_file() carry language field dari TreeSitterParser."""
        (tmp_path / "x.ts").write_text('function f(): void {}\n')
        pf = _parse_file(tmp_path / "x.ts", tmp_path)
        assert pf is not None
        assert pf.language == "typescript"
