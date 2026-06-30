"""Import resolver — maps ParsedImport.target to a repo-relative path (BLUEPRINT Section 14).

Security M-03: outputs are always relative-to-root; absolute paths never leak.
"""

from __future__ import annotations

from pathlib import Path

from graps.scanner.ast_parser import ParsedImport

MAX_SYMLINK_DEPTH = 5


def resolve_safe(path: Path, depth: int = 0) -> Path | None:
    """Follow symlinks safely; abort past MAX_SYMLINK_DEPTH to break loops."""
    if depth > MAX_SYMLINK_DEPTH:
        return None
    if path.is_symlink():
        return resolve_safe(path.resolve(), depth + 1)
    return path


def _relative(path: Path, root: Path) -> Path | None:
    """Return path relative to root if it exists and lives under root, else None."""
    safe = resolve_safe(path)
    if safe is None or not safe.is_file():
        return None
    try:
        return safe.resolve().relative_to(root.resolve())
    except ValueError:  # escaped root (M-03)
        return None


def _try_module(base: Path, parts: list[str], root: Path) -> Path | None:
    """Resolve dotted parts to a file under base. Tries the full path, then drops
    the last segment (it may be an imported name, not a submodule)."""
    for candidate in (parts, parts[:-1]):
        if not candidate:
            continue
        hit = (
            _relative(base.joinpath(*candidate).with_suffix(".py"), root)
            or _relative(base.joinpath(*candidate, "__init__.py"), root)
        )
        if hit:
            return hit
    return None


def resolve_import(imp: ParsedImport, current_file: Path, root: Path) -> Path | None:
    target = imp.target
    # ponytail: dynamic/star carry no concrete target — no edge to resolve.
    if imp.is_dynamic or imp.is_star or not target:
        return None

    if target.startswith("."):
        dots = len(target) - len(target.lstrip("."))
        rest = target[dots:]
        base = current_file.parent
        for _ in range(dots - 1):  # first dot = current package
            base = base.parent
        parts = rest.split(".") if rest else []
        return _try_module(base, parts, root)

    # Absolute: pkg.mod → root/pkg/mod.py or root/pkg/mod/__init__.py.
    return _try_module(root, target.split("."), root)


if __name__ == "__main__":
    import tempfile

    root = Path(tempfile.mkdtemp())
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "sub.py").write_text("")
    main = pkg / "main.py"
    main.write_text("")

    def imp(t):
        return ParsedImport(target=t, lineno=1)

    assert resolve_import(imp(".sub"), main, root) == Path("pkg/sub.py")
    assert resolve_import(imp("pkg.sub"), main, root) == Path("pkg/sub.py")
    assert resolve_import(imp("pkg.sub"), root / "anywhere.py", root) == Path("pkg/sub.py")
    assert resolve_import(imp(".nope"), main, root) is None
    assert resolve_import(imp("std.lib.missing"), main, root) is None
    assert resolve_import(ParsedImport(target="<dynamic>", lineno=1, is_dynamic=True), main, root) is None

    # __init__.py resolution for a package import.
    sub = pkg / "child"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    assert resolve_import(imp("pkg.child"), main, root) == Path("pkg/child/__init__.py")

    # depth guard
    assert resolve_safe(main, depth=6) is None

    print("self-check ok")
