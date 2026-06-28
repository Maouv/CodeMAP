from pathlib import Path
import os

from codemap.scanner.ast_parser import ParsedImport, safe_parse
from codemap.scanner.resolver import resolve_import, resolve_safe

FIXTURES = Path(__file__).parent / "fixtures" / "relative_imports"


def _imp(target, **kw):
    return ParsedImport(target=target, lineno=1, **kw)


def test_relative__resolves_to_sibling():
    main = FIXTURES / "main.py"
    imp = next(i for i in safe_parse(main).imports if i.target.startswith("."))
    assert resolve_import(imp, main, FIXTURES) == Path("sub.py")


def test_absolute__module_to_py(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("")
    assert resolve_import(_imp("pkg.mod"), tmp_path / "x.py", tmp_path) == Path("pkg/mod.py")


def test_absolute__package_to_init(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    assert resolve_import(_imp("pkg"), tmp_path / "x.py", tmp_path) == Path("pkg/__init__.py")


def test_notfound__returns_none(tmp_path):
    assert resolve_import(_imp("nope.gone"), tmp_path / "x.py", tmp_path) is None


def test_dynamic__returns_none(tmp_path):
    assert resolve_import(_imp("<dynamic>", is_dynamic=True), tmp_path / "x.py", tmp_path) is None


def test_star__returns_none(tmp_path):
    assert resolve_import(_imp("pkg", is_star=True), tmp_path / "x.py", tmp_path) is None


def test_output__always_relative(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("")
    assert not resolve_import(_imp("pkg.mod"), tmp_path / "x.py", tmp_path).is_absolute()


def test_resolvesafe__depth_guard(tmp_path):
    assert resolve_safe(tmp_path / "any.py", depth=6) is None


def test_resolvesafe__follows_symlink(tmp_path):
    real = tmp_path / "real.py"
    real.write_text("")
    link = tmp_path / "link.py"
    os.symlink(real, link)
    assert resolve_safe(link) == real
