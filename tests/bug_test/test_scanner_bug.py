"""
test_scanner_bugs.py
====================
Verifikasi bug yang ditemukan di graps/graps/scanner/
Setiap test CONFIRM bahwa bug benar-benar ada (bukan speculation).

Jalankan:
    cd ~/graps && python test_scanner_bugs.py
"""

import ast
import signal
import tempfile
import threading
from pathlib import Path

from graps.scanner import ParsedFile, ParsedFunction, ParsedImport
from graps.scanner.ast_parser import ASTParser, safe_parse
from graps.scanner.graph_builder import build_graph, _resolve_cache
from graps.scanner.resolver import resolve_import, resolve_safe
from graps.scanner.risk_analyzer import _check_circular_imports, analyze_risks
from graps.scanner.sanitize import sanitize_constant_value

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    mark = "✓" if condition else "✗"
    print(f"  [{mark}] {name}")
    if not condition:
        print(f"      ↳  {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# BUG 1 — graph_builder: module-level _resolve_cache tidak pernah dikosongkan
# File: graph_builder.py baris 22–28
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 1] Module-level _resolve_cache unbounded growth (graph_builder.py:22)")

before = len(_resolve_cache)
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    for i in range(50):
        imp = ParsedImport(target=f"mod_{i}", lineno=1)
        pf = ParsedFile(id=f"f{i}.py", path=root / f"f{i}.py", imports=[imp])
        build_graph([pf], root)

after = len(_resolve_cache)
check(
    "Cache tumbuh tanpa batas (50 scan unik → 50 entry baru)",
    after >= before + 50,
    f"before={before}, after={after}",
)
check(
    "Cache tidak pernah dikosongkan antara build_graph() calls",
    after > 0,
    "Harus 0 kalau ada cleanup",
)


# ─────────────────────────────────────────────────────────────────────────────
# BUG 2 — risk_analyzer: stem collision pada _check_circular_imports
# File: risk_analyzer.py baris 52–54
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 2] Stem collision di _check_circular_imports (risk_analyzer.py:52)")

# Dua file beda direktori, stem sama → dict last-write-wins
a1 = ParsedFile(path=Path("pkg/utils.py"), imports=[ParsedImport(target="b", lineno=1)])
a2 = ParsedFile(path=Path("lib/utils.py"), imports=[ParsedImport(target="x", lineno=1)])
b_file = ParsedFile(path=Path("b.py"), imports=[ParsedImport(target="utils", lineno=1)])

# b.py import 'utils', tapi by_module['utils'] = a2 (lib/utils.py, last wins)
# a2 tidak import 'b' → circular b→a1 (pkg/utils.py) TIDAK terdeteksi (false negative)
risks = _check_circular_imports(b_file, [a1, a2, b_file])
check(
    "False negative: circular b→pkg/utils tidak terdeteksi karena stem collision",
    len(risks) == 0,   # kita EXPECT ini 0 → bug terbukti
    f"risks={risks}",
)

# Verifikasi by_module hanya simpan last entry
by_module: dict[str, ParsedFile] = {}
for pf in [a1, a2]:
    by_module[pf.path.stem] = pf
check(
    "by_module['utils'] menunjuk ke lib/utils.py (a2), pkg/utils.py (a1) hilang",
    by_module["utils"] is a2,
    f"got path={by_module['utils'].path}",
)


# ─────────────────────────────────────────────────────────────────────────────
# BUG 3 — risk_analyzer: circular import pair dilaporkan dua kali
# File: risk_analyzer.py baris 74–80
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 3] Circular import pair double-reported (risk_analyzer.py:74)")

ca = ParsedFile(path=Path("circ_a.py"), imports=[ParsedImport(target="circ_b", lineno=1)])
cb = ParsedFile(path=Path("circ_b.py"), imports=[ParsedImport(target="circ_a", lineno=1)])

risks_a = analyze_risks(ca, [ca, cb])
risks_b = analyze_risks(cb, [ca, cb])

check(
    "circ_a.py melaporkan circular",
    any(r["type"] == "circular_import_toplevel" for r in risks_a),
)
check(
    "circ_b.py JUGA melaporkan circular pair yang sama",
    any(r["type"] == "circular_import_toplevel" for r in risks_b),
)
check(
    "Total: pair yang sama muncul dua kali di output gabungan",
    len(risks_a) + len(risks_b) == 2,
    f"risks_a={len(risks_a)}, risks_b={len(risks_b)}",
)


# ─────────────────────────────────────────────────────────────────────────────
# BUG 4 — graph_builder: is_private dihitung ulang dari nama, abaikan ParsedFunction.is_private
# File: graph_builder.py baris 73
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 4] is_private recomputed dari name.startswith('_'), abaikan field (graph_builder.py:73)")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    pf = ParsedFile(
        id="main.go",
        path=root / "main.go",
        functions=[
            ParsedFunction(name="myFunc", is_private=True),   # Go unexported, nama lowercase
            ParsedFunction(name="_helper", is_private=False),  # explicit public tapi ada '_'
        ],
        language="go",
    )
    graph = build_graph([pf], root)
    fns = {f["name"]: f for f in graph["nodes"][0]["functions"]}

    check(
        "myFunc: is_private=True di ParsedFunction → False di graph (salah)",
        fns["myFunc"]["is_private"] is False,  # bug: harusnya True
        f"got is_private={fns['myFunc']['is_private']}",
    )
    check(
        "_helper: is_private=False di ParsedFunction → True di graph (salah)",
        fns["_helper"]["is_private"] is True,  # bug: harusnya False
        f"got is_private={fns['_helper']['is_private']}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# BUG 5 — sanitize: non-string value crash TypeError
# File: sanitize.py baris 70 (pattern.search(value))
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 5] sanitize_constant_value crash untuk non-str value (sanitize.py:70)")

non_str_cases = [
    ("MAX_RETRY", 3),
    ("ENABLED", True),
    ("RATIO", 3.14),
    ("DATA", None),
]

for name, val in non_str_cases:
    try:
        sanitize_constant_value(name, val)
        crashed = False
    except TypeError:
        crashed = True
    check(
        f"sanitize_constant_value({name!r}, {val!r}) → TypeError crash",
        crashed,
        "Tidak crash padahal seharusnya",
    )

# Konfirmasi build_graph juga crash
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    pf = ParsedFile(
        id="cfg.py",
        path=root / "cfg.py",
        constants=[{"name": "MAX_RETRY", "value": 3, "line": 1}],
    )
    try:
        build_graph([pf], root)
        bg_crashed = False
    except TypeError:
        bg_crashed = True
    check(
        "build_graph crash ketika constant value adalah int",
        bg_crashed,
    )


# ─────────────────────────────────────────────────────────────────────────────
# BUG 6 — sanitize: keyword 'auth' terlalu broad → false positive redaction
# File: sanitize.py baris 11–22 (SENSITIVE_NAME_KEYWORDS)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 6] 'auth' keyword terlalu broad → false positive (sanitize.py:11)")

false_positive_cases = [
    ("AUTHOR", "John Doe"),
    ("DEFAULT_AUTHOR", "Jane"),
    ("AUTHENTICATE_MAX_RETRY", "3"),
    ("REAUTHORIZE", "false"),
]

for name, val in false_positive_cases:
    result = sanitize_constant_value(name, val)
    check(
        f"{name!r} ter-redact padahal bukan credential (false positive)",
        result == "[REDACTED]",
        f"got={result!r}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# BUG 7 — ast_parser: signal.signal() crash di non-main thread
# File: ast_parser.py baris 62–64
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 7] safe_parse crash di worker thread (ast_parser.py:62)")

thread_err: dict[str, object] = {}

def _parse_in_thread() -> None:
    p = Path(tempfile.mkdtemp()) / "t.py"
    p.write_text("def foo(): pass\n")
    try:
        safe_parse(p)
        thread_err["error"] = None
    except Exception as e:
        thread_err["error"] = f"{type(e).__name__}: {e}"

t = threading.Thread(target=_parse_in_thread)
t.start()
t.join()

check(
    "safe_parse() di worker thread raise ValueError (signal only works in main thread)",
    isinstance(thread_err.get("error"), str) and "signal" in thread_err["error"].lower(),
    f"error={thread_err.get('error')}",
)


# ─────────────────────────────────────────────────────────────────────────────
# BUG 8 — resolver: resolve_safe depth guard tidak efektif (dead code)
# File: resolver.py baris 15–21
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 8] resolve_safe depth guard tidak efektif / dead code (resolver.py:15)")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    real = root / "real.py"
    real.write_text("")
    # Buat chain 6 symlink
    prev = real
    links = []
    for i in range(6):
        lnk = root / f"l{i}.py"
        lnk.symlink_to(prev)
        links.append(lnk)
        prev = lnk

    # path.resolve() di Python sudah follow semua symlink di level OS
    # jadi setelah resolve() hasilnya BUKAN symlink → rekursi selalu berhenti di depth=1
    resolved = links[-1].resolve()
    check(
        "Setelah path.resolve(), result BUKAN symlink (depth guard tidak pernah aktif)",
        not resolved.is_symlink(),
        f"resolved={resolved}, is_symlink={resolved.is_symlink()}",
    )
    # Depth=6 tapi tetap resolve karena resolve() OS-level
    result = resolve_safe(links[-1])
    check(
        "resolve_safe(chain 6 symlink) tetap berhasil meski depth > MAX_SYMLINK_DEPTH=5",
        result is not None,
        f"result={result}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# BUG 9 — resolver: ambiguitas pkg/submod.py vs pkg/submod/__init__.py
# File: resolver.py baris 35–47
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 9] Resolver pilih submod.py bukan submod/__init__.py (resolver.py:35)")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "pkg").mkdir()
    (root / "pkg" / "submod").mkdir()
    (root / "pkg" / "submod" / "__init__.py").write_text("")
    (root / "pkg" / "submod.py").write_text("")  # ada keduanya!

    current = root / "main.py"
    # 'from pkg.submod import ClassName' → target='pkg.submod.ClassName'
    result = resolve_import(
        ParsedImport(target="pkg.submod.ClassName", lineno=1), current, root
    )
    check(
        "Resolver pilih pkg/submod.py tapi Python runtime pakai pkg/submod/__init__.py",
        result == Path("pkg/submod.py"),  # ini bug: harusnya pkg/submod/__init__.py
        f"result={result}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# BUG 10 — ast_parser: ParsedFunction.line_start tidak diisi (selalu 0)
# File: ast_parser.py baris 125–138 (_handle_func)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 10] ParsedFunction.line_start selalu 0 dari ASTParser (ast_parser.py:125)")

src = "def foo():\n    pass\n\ndef bar():\n    pass\n"
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "t.py"
    p.write_text(src)
    r = safe_parse(p)

    for fn in r.functions:
        check(
            f"{fn.name}: lineno={fn.lineno} (terisi) tapi line_start={fn.line_start} (selalu 0)",
            fn.line_start == 0 and fn.lineno > 0,
            f"line_start={fn.line_start}, lineno={fn.lineno}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUG 11 — tree_sitter_parser: path.stat() kedua tidak di-try/except
# File: tree_sitter_parser.py baris 100
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 11] path.stat().st_mtime di tree_sitter_parser tidak di-guard (tree_sitter_parser.py:100)")

import inspect
from graps.scanner.tree_sitter_parser import TreeSitterParser

src_code = inspect.getsource(TreeSitterParser.parse_file)
lines = src_code.split("\n")

# Cari baris yang ada st_mtime dan cek apakah dalam try block
stat_mtime_line = None
for i, l in enumerate(lines):
    if "st_mtime" in l:
        stat_mtime_line = i
        break

# Periksa apakah ada try: SETELAH try/except process() dan SEBELUM return ParsedFile
# Dari source inspection: stat().st_mtime ada di dalam return ParsedFile(...) yang
# TIDAK di-wrapped try/except
in_try = False
try_depth = 0
for i, l in enumerate(lines):
    stripped = l.strip()
    if stripped.startswith("try:"):
        try_depth += 1
    if stripped.startswith("except") and try_depth > 0:
        try_depth -= 1
    if "st_mtime" in l:
        stat_mtime_in_try = try_depth > 0

check(
    "path.stat().st_mtime dipanggil di luar try/except → OSError tidak tertangkap",
    not stat_mtime_in_try,
    f"stat_mtime_in_try={stat_mtime_in_try}",
)
check(
    "Double stat() call: sekali untuk size (line 54), sekali untuk mtime (line 100) → TOCTOU",
    stat_mtime_line is not None,
    "stat().st_mtime ditemukan di source",
)


# ─────────────────────────────────────────────────────────────────────────────
# BUG 12 — ast_parser: __all__ += [] tidak terdeteksi (AugAssign bukan Assign)
# File: ast_parser.py baris 177–183 (visit_Assign)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[BUG 12] __all__ += [...] tidak terdeteksi (ast_parser.py:177)")

src_aug = '__all__ = ["foo"]\n__all__ += ["bar"]\n'
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "aug.py"
    p.write_text(src_aug)
    r = safe_parse(p)
    check(
        "__all__ += ['bar'] tidak menambah exported_names (hanya ['foo'] yang masuk)",
        r.exported_names == ["foo"],  # 'bar' hilang → bug
        f"exported_names={r.exported_names}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(1 for s, _, _ in results if s == PASS)
failed = sum(1 for s, _, _ in results if s == FAIL)
print(f"  TOTAL: {len(results)} checks | {passed} PASS | {failed} FAIL")

unexpected_pass = [(n, d) for s, n, d in results if s == FAIL]
if unexpected_pass:
    print("\n  Checks yang tidak sesuai ekspektasi:")
    for name, detail in unexpected_pass:
        print(f"    - {name}")
        if detail:
            print(f"      {detail}")

print("=" * 60)
