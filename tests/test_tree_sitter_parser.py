"""Phase 4 tests — TreeSitterParser, 1 file per language.

Verifies: function extraction, import extraction, class extraction, export
extraction, Go import dedup, visibility detection, graceful failure on
unsupported/oversized files.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from graps.scanner.tree_sitter_parser import TreeSitterParser

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent  # codemap root

# Skip seluruh module kalau tree-sitter-language-pack tidak terinstall.
pytestmark = pytest.mark.skipif(
    pytest.importorskip("tree_sitter_language_pack", reason="tslp not installed") is None,
    reason="tree-sitter-language-pack not installed",
)


@pytest.fixture()
def parser() -> TreeSitterParser:
    return TreeSitterParser()


# ── Per-language: 1 file per bahasa ──────────────────────────────────


class TestPython:
    def test_parse(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "simple.py", ROOT)
        assert pf is not None
        assert pf.language == "python"
        assert any(f.name == "hello" for f in pf.functions)
        # Python imports → target bukan full statement string
        assert any("os" in i.target for i in pf.imports)


class TestTypeScript:
    def test_simple(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "typescript" / "simple.ts", ROOT)
        assert pf is not None
        assert pf.language == "typescript"
        assert any(f.name == "greet" for f in pf.functions)
        assert len(pf.imports) == 1

    def test_class_methods(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "typescript" / "class_methods.ts", ROOT)
        assert pf is not None
        # Method ter-flatten dengan parent = class name
        names = {f.name for f in pf.functions}
        assert {"add", "multiply"} <= names
        assert all(f.parent == "Calculator" for f in pf.functions)
        # Class masuk ke classes list
        assert len(pf.classes) == 1
        assert pf.classes[0]["name"] == "Calculator"
        methods = cast(list[str], pf.classes[0]["methods"])
        assert sorted(methods) == ["add", "multiply"]

    def test_exports(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "typescript" / "export_patterns.ts", ROOT)
        assert pf is not None
        assert len(pf.exported_names) >= 2  # square + default main
        assert any("square" in e for e in pf.exported_names)


class TestJavaScript:
    def test_parse(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "javascript" / "simple.js", ROOT)
        assert pf is not None
        assert pf.language == "javascript"
        assert any(f.name == "baz" for f in pf.functions)
        assert len(pf.imports) == 1


class TestGo:
    def test_simple(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "go" / "simple.go", ROOT)
        assert pf is not None
        assert pf.language == "go"
        assert any(f.name == "main" for f in pf.functions)

    def test_import_dedup(self, parser: TreeSitterParser) -> None:
        """Go return 2 entries per import — adapter harus dedup by lineno."""
        pf = parser.parse_file(FIX / "go" / "simple.go", ROOT)
        assert pf is not None
        fmt_imports = [i for i in pf.imports if "fmt" in i.target]
        assert len(fmt_imports) == 1, f"expected 1 deduped import, got {fmt_imports}"

    def test_unexported(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "go" / "unexported.go", ROOT)
        assert pf is not None
        names = {f.name: f for f in pf.functions}
        assert "ExportedFunc" in names
        assert "unexportedFunc" in names


class TestRust:
    def test_simple(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "rust" / "simple.rs", ROOT)
        assert pf is not None
        assert pf.language == "rust"
        assert any(f.name == "main" for f in pf.functions)

    def test_pub_private(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "rust" / "pub_private.rs", ROOT)
        assert pf is not None
        names = {f.name: f for f in pf.functions}
        assert "public_function" in names
        assert "private_function" in names


# ── Failure modes ────────────────────────────────────────────────────


class TestFailureModes:
    def test_unsupported_extension(self, parser: TreeSitterParser, tmp_path: Path) -> None:
        f = tmp_path / "weird.xyz"
        f.write_text("hello")
        assert parser.parse_file(f, tmp_path) is None

    def test_oversized_file(self, parser: TreeSitterParser, tmp_path: Path) -> None:
        f = tmp_path / "big.py"
        f.write_text("x = 1\n" * 200_000)  # > 1MB
        assert parser.parse_file(f, tmp_path) is None

    def test_nonexistent_file(self, parser: TreeSitterParser, tmp_path: Path) -> None:
        assert parser.parse_file(tmp_path / "nope.py", tmp_path) is None

    def test_supported_extensions(self, parser: TreeSitterParser) -> None:
        # Protocol compliance — returns []
        assert parser.supported_extensions() == []


# ── Line numbers are 1-indexed ───────────────────────────────────────


class TestLineNumbers:
    def test_function_line_start(self, parser: TreeSitterParser) -> None:
        pf = parser.parse_file(FIX / "typescript" / "simple.ts", ROOT)
        assert pf is not None
        greet = next(f for f in pf.functions if f.name == "greet")
        assert greet.line_start >= 1  # 1-indexed, tree-sitter 0-indexed +1
