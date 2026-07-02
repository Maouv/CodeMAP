# Bug Hunter Report — `graps/graps/scanner/`

**Scope:** `graps/scanner/__init__.py`, `ast_parser.py`, `graph_builder.py`, `resolver.py`, `risk_analyzer.py`, `sanitize.py`, `tree_sitter_parser.py`  
**Branch:** `phase1-scanner-core`  
**Test file:** `test_scanner_bugs.py` (27 checks, 27 PASS — semua bug di bawah terkonfirmasi)

---

## Finding 1

### Title
Module-level `_resolve_cache` tidak pernah dikosongkan → unbounded memory growth

### Severity
High

### Likelihood
High

### Confidence
High

### Category
Memory Leak / Resource Leak

### Scenario
Aplikasi memangil `build_graph()` berulang kali (CLI batch scan, watch mode, server) — cache bertumbuh tak terbatas sampai proses di-restart atau OOM.

### Description
`_resolve_cache` adalah `dict` di level modul (`graph_builder.py` baris 22). Setiap pasangan `(target, is_dynamic, is_star, current_file, root)` ditambahkan tanpa pernah dihapus. Tidak ada batas ukuran, tidak ada TTL, tidak ada cleanup di akhir `build_graph()`.

### Evidence
```python
# graph_builder.py baris 22–28
_resolve_cache: dict[tuple[str, bool, bool, Path, Path], Path | None] = {}

def _resolved(imp: ParsedImport, current_file: Path, root: Path) -> Path | None:
    key = (imp.target, imp.is_dynamic, imp.is_star, current_file, root)
    if key not in _resolve_cache:
        _resolve_cache[key] = resolve_import(imp, current_file, root)
    return _resolve_cache[key]
```

**Output test (`test_scanner_bugs.py` BUG 1):**
```
Cache awal: 0 entries
Cache sesudah 200 scan berbeda: 200 entries
```

### Steps to Reproduce
```python
from graps.scanner.graph_builder import build_graph, _resolve_cache
# jalankan 200 build_graph() dengan file berbeda
# len(_resolve_cache) == 200, terus tumbuh
```

### Expected Behavior
Cache dikosongkan (atau dibatasi) setelah setiap `build_graph()` selesai, atau menggunakan `functools.lru_cache` dengan batas ukuran.

### Actual Behavior
Cache bertumbuh linear dengan jumlah total import yang pernah di-resolve sepanjang umur proses.

### Root Cause
Cache didesain untuk memoize resolusi dalam satu scan, tapi implementasinya sebagai module-level dict berarti umurnya ikut umur proses — bukan per-call.

### Blast Radius
Service / proses long-running (server mode, watch mode, CI pipeline).

### Impact
OOM pada project besar dengan ribuan file Python. Tidak ada data corruption, tapi proses akhirnya mati.

### Recommendation
- **Fix cepat:** kosongkan cache di awal setiap `build_graph()` → `_resolve_cache.clear()`
- **Fix proper:** pindahkan cache ke scope lokal `build_graph()` dan pass sebagai argumen ke `_resolved()`, atau gunakan `functools.lru_cache(maxsize=4096)` pada `resolve_import` langsung
- **Long term:** tambahkan metrics ukuran cache untuk monitoring

### Test Cases
```python
# Setelah fix: cache harus kosong setelah setiap build_graph()
build_graph([pf1], root1)
build_graph([pf2], root2)
assert len(_resolve_cache) == 0  # atau tidak ada akses sama sekali
```

### Regression Risk
Medium — perubahan scope cache bisa mempengaruhi performa jika banyak file share import yang sama dalam satu scan. Harus benchmark.

### Related Code Path
`graph_builder.py:22–28` → `_resolved()` → `resolve_import()`

---

## Finding 2

### Title
Stem collision di `_check_circular_imports` → false negative (circular tidak terdeteksi)

### Severity
High

### Likelihood
Medium

### Confidence
High

### Category
Logic Bug / False Negative

### Scenario
Project punya dua file dengan nama yang sama di direktori berbeda: `pkg/utils.py` dan `lib/utils.py`. Salah satunya terlibat dalam circular import — tapi tidak terdeteksi.

### Description
`_check_circular_imports` membangun `by_module` dict dengan key `pf.path.stem`. Kalau ada dua file dengan stem yang sama, yang terakhir dalam list `all_results` akan overwrite yang pertama — sehingga satu file hilang dari lookup.

### Evidence
```python
# risk_analyzer.py baris 52–54
by_module: dict[str, ParseResult] = {}
for pf in all_results:
    by_module[pf.path.stem] = pf  # ← last-write-wins, stem collision!
```

**Output test (`test_scanner_bugs.py` BUG 2):**
```
by_module['utils'] menunjuk ke lib/utils.py (a2), pkg/utils.py (a1) hilang
False negative: circular b→pkg/utils tidak terdeteksi
```

### Steps to Reproduce
```python
a1 = ParsedFile(path=Path("pkg/utils.py"), imports=[ParsedImport(target="b", ...)])
a2 = ParsedFile(path=Path("lib/utils.py"), imports=[ParsedImport(target="x", ...)])
b  = ParsedFile(path=Path("b.py"),         imports=[ParsedImport(target="utils", ...)])
# b → pkg/utils → tidak ada back-edge
# b → lib/utils → ada? tidak — by_module['utils'] = a2, a2 import 'x' bukan 'b'
risks = _check_circular_imports(b, [a1, a2, b])
# risks == [] padahal circular b ↔ a1 ada
```

### Expected Behavior
Kedua file dilacak secara terpisah menggunakan path lengkap, bukan hanya stem.

### Actual Behavior
Satu file hilang dari lookup — circular yang melibatkan file tersebut tidak terdeteksi.

### Root Cause
Penggunaan `path.stem` sebagai key dict tidak unik di project dengan subdirektori.

### Blast Radius
Module — hanya circular detection, tapi ini salah satu fitur utama risk analyzer.

### Impact
Silent false negative. Developer tidak diperingatkan tentang circular import yang nyata, yang bisa menyebabkan `ImportError` di runtime.

### Recommendation
- Gunakan path relatif ke root sebagai key: `str(pf.path.relative_to(root))` atau `pf.id`
- Matching target ke file juga harus diperbaiki — saat ini `target.split(".")[0]` lalu lookup by stem, harus diganti dengan resolver yang sudah ada

### Test Cases
```python
# Setelah fix: circular antar file beda direktori tapi sama stem harus terdeteksi
risks = _check_circular_imports(b, [a1, a2, b])
assert any(r["type"] == "circular_import_toplevel" for r in risks)
```

### Regression Risk
High — perubahan matching logic bisa mengubah true positive rate. Butuh test suite lengkap untuk semua pola circular.

### Related Code Path
`risk_analyzer.py:42–82` → `_check_circular_imports()`

---

## Finding 3

### Title
Circular import pair dilaporkan dua kali di output gabungan

### Severity
Medium

### Likelihood
Very High

### Confidence
High

### Category
Logic Bug / Duplicate Output

### Scenario
Setiap kali ada circular import A ↔ B, consumer graph (UI, CLI) akan menampilkan warning dua kali — sekali dari perspektif A, sekali dari B.

### Description
`analyze_risks()` dipanggil untuk setiap file secara independen. Ketika A mengimport B dan B mengimport A, `_check_circular_imports(A, all)` menghasilkan satu risk, dan `_check_circular_imports(B, all)` juga menghasilkan satu risk — total dua entry untuk pair yang sama.

### Evidence
```python
# risk_analyzer.py baris 74–80
flags.append({
    "type": "circular_import_toplevel",
    "detail": f"circular import: {my_stem} → {target} → {my_stem}",
    "affected_files": [str(result.path), str(target_pf.path)],  # ← kedua file sudah ada di sini
})
```

**Output test (`test_scanner_bugs.py` BUG 3):**
```
risks_a: [{"detail": "circular import: circ_a → circ_b → circ_a", ...}]
risks_b: [{"detail": "circular import: circ_b → circ_a → circ_b", ...}]
# Pair yang sama, dua kali
```

### Steps to Reproduce
```python
risks_a = analyze_risks(a, [a, b])
risks_b = analyze_risks(b, [a, b])
# len(risks_a) + len(risks_b) == 2 untuk satu circular pair
```

### Expected Behavior
Satu circular pair → satu entry risk, dengan `affected_files` berisi kedua file.

### Actual Behavior
Satu circular pair → dua entry risk dengan detail yang berbeda tapi menggambarkan hal yang sama.

### Root Cause
Tidak ada deduplikasi di level `build_graph()` sebelum digabungkan ke output. Setiap file dinilai secara independen tanpa tracking pair yang sudah dilaporkan.

### Blast Radius
Local — hanya output `warnings` dan `risks` di graph JSON, tidak corrupt data.

### Impact
UI/CLI menampilkan warning duplikat, membingungkan developer, dan mengembungkan ukuran output JSON pada project besar.

### Recommendation
- Di `build_graph()`, setelah collect semua risks, deduplikasi circular pairs berdasarkan frozenset `affected_files`
- Atau: tambahkan flag `_reported_pairs: set[frozenset]` di `_check_circular_imports` yang di-pass dari `analyze_risks`

### Test Cases
```python
# Setelah fix: circular pair hanya muncul satu kali
all_risks = []
for pf in [a, b]:
    all_risks.extend(analyze_risks(pf, [a, b]))
circular = [r for r in all_risks if r["type"] == "circular_import_toplevel"]
assert len(circular) == 1
```

### Regression Risk
Low — perubahan dedup tidak mengubah deteksi, hanya output.

### Related Code Path
`risk_analyzer.py:42–82`, `graph_builder.py:138–142`

---

## Finding 4

### Title
`graph_builder` recompute `is_private` dari nama, mengabaikan `ParsedFunction.is_private`

### Severity
Medium

### Likelihood
High

### Confidence
High

### Category
Logic Bug / Data Loss

### Scenario
Phase 4: `TreeSitterParser` mendeteksi visibilitas dari modifier bahasa (Go: `func MyFunc` = exported, `func myFunc` = unexported; Java: `private void foo()`). Tapi `graph_builder` membuang informasi ini dan recompute dari nama prefix saja.

### Description
`_build_node()` di `graph_builder.py` mengisi `is_private` dengan `f.name.startswith("_")` — Python convention. `ParsedFunction` sudah punya field `is_private` yang di-set oleh parser (termasuk `TreeSitterParser._detect_is_private()` yang sudah handle berbagai bahasa), tapi field ini tidak pernah dibaca.

### Evidence
```python
# graph_builder.py baris 69–85
functions = [{
    "name": f.name,
    "type": "function",
    "decorators": f.decorators,
    "is_private": f.name.startswith("_"),  # ← ignore f.is_private!
    "line_start": f.lineno,
    ...
} for f in result.functions]
```

**Output test (`test_scanner_bugs.py` BUG 4):**
```
myFunc  → ParsedFunction.is_private=True  → graph is_private=False  (SALAH)
_helper → ParsedFunction.is_private=False → graph is_private=True   (SALAH)
```

### Steps to Reproduce
```python
pf = ParsedFile(functions=[
    ParsedFunction(name="myFunc", is_private=True),   # Go unexported
    ParsedFunction(name="_helper", is_private=False),  # explicit public
], language="go")
graph = build_graph([pf], root)
# graph nodes[0].functions[0].is_private == False  (harusnya True)
```

### Expected Behavior
`"is_private": f.is_private` — gunakan nilai yang sudah dihitung parser.

### Actual Behavior
`is_private` di graph selalu berdasarkan Python naming convention, salah untuk semua bahasa lain.

### Root Cause
Refactoring yang tidak lengkap: field `is_private` ditambahkan ke `ParsedFunction` tapi `_build_node` tidak diupdate untuk membacanya.

### Blast Radius
Module — semua function entry di graph JSON untuk non-Python files akan punya `is_private` yang salah.

### Impact
Risk analyzer downstream yang menggunakan `is_private` untuk mendeteksi exposed private methods akan memberikan hasil salah untuk Go, Java, Rust, dll.

### Recommendation
```python
# Fix: graph_builder.py baris 73
"is_private": f.is_private,  # gunakan field yang sudah ada
```
Jika backward compat dibutuhkan untuk Python: `f.is_private or f.name.startswith("_")`.

### Test Cases
```python
fn = ParsedFunction(name="myFunc", is_private=True)
pf = ParsedFile(functions=[fn], language="go")
graph = build_graph([pf], root)
assert graph["nodes"][0]["functions"][0]["is_private"] is True
```

### Regression Risk
Low untuk Python (hasil sama karena ASTParser set `is_private=False` default dan `name.startswith("_")` menangani kasus umum). Medium untuk Phase 4 non-Python.

### Related Code Path
`graph_builder.py:73`, `scanner/__init__.py:28`, `tree_sitter_parser.py:198–219`

---

## Finding 5

### Title
`sanitize_constant_value()` crash `TypeError` untuk non-string value

### Severity
Critical

### Likelihood
High

### Confidence
High

### Category
Crash / Missing Validation / Type Safety

### Scenario
Phase 2 parser mengekstrak constant `MAX_RETRY = 3` (int) atau `ENABLED = True` (bool). `build_graph()` memanggil `sanitize_constant_value("MAX_RETRY", 3)` → crash `TypeError` → seluruh scan gagal.

### Description
`ParsedFile.constants` bertipe `list[dict[str, object]]` — `value` bisa berupa `object` apapun. `sanitize_constant_value()` langsung melempar nilai tersebut ke `pattern.search(value)` yang mengharapkan `str | bytes`. Jika `value` bukan string, `re.search` raise `TypeError`.

### Evidence
```python
# sanitize.py baris 70–72
for pattern in SENSITIVE_VALUE_PATTERNS:
    if pattern.search(value):  # ← crash jika value bukan str
        return "[REDACTED]"
```

**Output test (`test_scanner_bugs.py` BUG 5):**
```
sanitize_constant_value('MAX_RETRY', 3)    → TypeError: expected string or bytes-like object
sanitize_constant_value('ENABLED', True)   → TypeError
sanitize_constant_value('RATIO', 3.14)    → TypeError
sanitize_constant_value('DATA', None)      → TypeError
build_graph() dengan constant int         → CRASH
```

### Steps to Reproduce
```python
from graps.scanner.sanitize import sanitize_constant_value
sanitize_constant_value("MAX_RETRY", 3)  # → TypeError
```

### Expected Behavior
Non-string values di-convert ke `str` sebelum regex, atau di-skip pattern matching dan dikembalikan as-is (non-string tidak mungkin berisi credential literal).

### Actual Behavior
`TypeError` yang tidak tertangkap → propagate ke `build_graph()` → scan gagal total.

### Root Cause
Type signature fungsi mengatakan `value: str` tapi tidak ada runtime enforcement. `ParsedFile.constants` menggunakan `dict[str, object]` yang lebih luas.

### Blast Radius
System-wide — satu file dengan constant non-string membuat seluruh `build_graph()` gagal.

### Impact
- **Production:** scan crash total untuk project yang punya konstanta numerik/boolean
- **Phase 2:** masalah ini akan muncul begitu parser mulai mengekstrak constants

### Recommendation
```python
# sanitize.py — fix sederhana
def sanitize_constant_value(name: str, value: object) -> object:
    if not isinstance(value, str):
        return value  # non-string tidak bisa berupa credential literal
    name_lower = name.lower()
    if any(keyword in name_lower for keyword in SENSITIVE_NAME_KEYWORDS):
        return "[REDACTED]"
    for pattern in SENSITIVE_VALUE_PATTERNS:
        if pattern.search(value):
            return "[REDACTED]"
    return value
```

### Test Cases
```python
assert sanitize_constant_value("MAX_RETRY", 3) == 3
assert sanitize_constant_value("ENABLED", True) is True
assert sanitize_constant_value("RATIO", 3.14) == 3.14
assert sanitize_constant_value("DATA", None) is None
assert sanitize_constant_value("DB_PASSWORD", "secret") == "[REDACTED]"
```

### Regression Risk
Low — perubahan hanya menambah early-return untuk non-string.

### Related Code Path
`sanitize.py:39–74`, `graph_builder.py:39–50` (`_sanitized_constants`)

---

## Finding 6

### Title
Keyword `"auth"` di `SENSITIVE_NAME_KEYWORDS` terlalu broad → false positive redaction

### Severity
Medium

### Likelihood
Very High

### Confidence
High

### Category
Logic Bug / False Positive

### Scenario
Developer punya konstanta `AUTHOR = "John Doe"` atau `AUTHENTICATE_MAX_RETRY = 3` di kodenya. Graph output akan menampilkan `[REDACTED]` untuk nilai yang tidak sensitif — menyesatkan dan menghilangkan data berguna.

### Description
`sanitize.py` menggunakan `any(keyword in name_lower ...)` — substring match. Keyword `"auth"` cocok dengan `AUTHOR`, `DEFAULT_AUTHOR`, `AUTHENTICATE_MAX_RETRY`, `REAUTHORIZE`, `OAUTH_PROVIDER`.

### Evidence
```python
# sanitize.py baris 11–22
SENSITIVE_NAME_KEYWORDS = {
    ...
    "auth",           # ← terlalu broad
    "credential",
    ...
}
```

**Output test (`test_scanner_bugs.py` BUG 6):**
```
AUTHOR='John Doe'                → '[REDACTED]'  (false positive)
DEFAULT_AUTHOR='Jane'            → '[REDACTED]'  (false positive)
AUTHENTICATE_MAX_RETRY='3'       → '[REDACTED]'  (false positive)
REAUTHORIZE='false'              → '[REDACTED]'  (false positive)
```

### Steps to Reproduce
```python
sanitize_constant_value("AUTHOR", "John Doe")        # → "[REDACTED]"
sanitize_constant_value("AUTHENTICATE_MAX_RETRY", "3") # → "[REDACTED]"
```

### Expected Behavior
Hanya nama yang benar-benar credential-related yang di-redact. `AUTHOR`, `AUTHENTICATE_MAX_RETRY` tidak seharusnya di-redact.

### Actual Behavior
Setiap variabel yang mengandung substring `"auth"` di-redact.

### Root Cause
Substring matching tanpa word boundary check. Harusnya match pada kata utuh seperti `_auth_`, `_auth`, `auth_`.

### Blast Radius
Local — hanya nilai di graph JSON, tidak corrupt data asli.

### Impact
Graph output kehilangan data valid. Developer yang membaca graph untuk dokumentasi atau analisis mendapat informasi yang salah.

### Recommendation
Gunakan word-boundary matching:
```python
import re
_SENSITIVE_RE = re.compile(
    r"\b(password|passwd|pwd|secret|token|api_key|apikey|api_secret"
    r"|auth_token|auth_key|auth_secret|credential|credentials"
    r"|private_key|privkey|access_key|access_secret"
    r"|client_secret|client_id|signing_key|encryption_key"
    r"|webhook_secret|jwt_secret|db_pass|database_pass)\b"
)
# Ganti "auth" dengan keyword yang lebih spesifik
```

Atau ubah "auth" menjadi daftar lebih spesifik: `"auth_token"`, `"auth_key"`, `"auth_secret"`.

### Test Cases
```python
assert sanitize_constant_value("AUTHOR", "John Doe") == "John Doe"
assert sanitize_constant_value("AUTH_TOKEN", "abc123") == "[REDACTED]"
assert sanitize_constant_value("AUTHENTICATE_MAX_RETRY", "3") == "3"
```

### Regression Risk
Medium — perubahan keyword list bisa membuat beberapa true positive sebelumnya tidak ter-redact. Butuh audit daftar keyword.

### Related Code Path
`sanitize.py:11–22, 63–67`

---

## Finding 7

### Title
`safe_parse()` crash `ValueError` saat dipanggil dari worker thread

### Severity
High

### Likelihood
High

### Confidence
High

### Category
Concurrency / Threading Bug / Crash

### Scenario
CLI menambahkan flag `--parallel` atau menggunakan `ThreadPoolExecutor` untuk scan lebih cepat. Setiap thread memanggil `safe_parse()` → crash karena `signal.signal()` hanya bisa dipanggil dari main thread.

### Description
`safe_parse()` memanggil `signal.signal(signal.SIGALRM, _timeout)` untuk timeout guard. Python docs eksplisit: `signal.signal()` hanya bisa dipanggil dari main thread. Di worker thread, ini raise `ValueError: signal only works in main thread`.

### Evidence
```python
# ast_parser.py baris 57–64
has_alarm = hasattr(signal, "SIGALRM")  # ← hanya cek OS, tidak cek thread
def _timeout(signum, frame): raise TimeoutError
if has_alarm:
    old = signal.signal(signal.SIGALRM, _timeout)  # ← CRASH di non-main thread
    signal.alarm(_TIMEOUT_S)
```

**Output test (`test_scanner_bugs.py` BUG 7):**
```
thread error: ValueError: signal only works in main thread of the main interpreter
```

### Steps to Reproduce
```python
import threading
from graps.scanner.ast_parser import safe_parse
err = {}
def run():
    try: safe_parse(Path("test.py"))
    except Exception as e: err["e"] = e
t = threading.Thread(target=run); t.start(); t.join()
# err["e"] == ValueError: signal only works in main thread
```

### Expected Behavior
`safe_parse()` berjalan tanpa error di thread manapun (timeout guard dinonaktifkan secara graceful di non-main thread, bukan crash).

### Actual Behavior
`ValueError` tidak tertangkap → thread crash → `Future` dari ThreadPoolExecutor raise exception.

### Root Cause
Guard hanya mengecek ketersediaan `SIGALRM` di OS (Unix), tapi tidak mengecek apakah eksekusi ada di main thread.

### Blast Radius
System-wide jika parallelism diperkenalkan. Semua parallel scan akan gagal.

### Impact
- Concurrent/parallel scanning tidak bisa digunakan sama sekali
- Jika dipanggil via async worker, seluruh worker pool bisa crash

### Recommendation
```python
# ast_parser.py — fix
import threading

has_alarm = hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()
```

Ini membuat timeout guard hanya aktif di main thread, dan non-main thread berjalan tanpa guard (dengan risiko hang yang minimal dan bisa dihandle di level caller dengan `concurrent.futures.wait(timeout=...)`).

### Test Cases
```python
import threading
from graps.scanner.ast_parser import safe_parse
err = {}
def run():
    try:
        r = safe_parse(Path("valid.py"))
        err["result"] = r
    except Exception as e:
        err["error"] = e
t = threading.Thread(target=run); t.start(); t.join()
assert "error" not in err
assert "result" in err
```

### Regression Risk
Low — main thread behavior tidak berubah. Thread support adalah penambahan.

### Related Code Path
`ast_parser.py:57–73`

---

## Finding 8

### Title
`resolve_safe()` depth guard tidak efektif — dead code

### Severity
Low

### Likelihood
High

### Confidence
High

### Category
Logic Bug / Dead Code / False Security

### Scenario
Developer mengandalkan `MAX_SYMLINK_DEPTH = 5` sebagai proteksi terhadap symlink loop. Tapi perlindungan ini tidak pernah aktif karena implementasinya salah.

### Description
`resolve_safe()` memanggil `path.resolve()` sebelum rekursi. `Path.resolve()` di Python (dan OS Linux) sudah mengikuti seluruh rantai symlink di level OS dan mengembalikan path absolut nyata yang **bukan symlink**. Karena hasilnya bukan symlink, `path.is_symlink()` di rekursi berikutnya selalu `False` → rekursi berhenti di depth=1. `MAX_SYMLINK_DEPTH` tidak pernah dicapai.

### Evidence
```python
# resolver.py baris 15–21
def resolve_safe(path: Path, depth: int = 0) -> Path | None:
    if depth > MAX_SYMLINK_DEPTH:
        return None
    if path.is_symlink():
        return resolve_safe(path.resolve(), depth + 1)  # ← resolve() sudah ikuti semua symlink
    return path
```

**Output test (`test_scanner_bugs.py` BUG 8):**
```
link.resolve() is_symlink: False  ← setelah resolve(), hasilnya bukan symlink
resolve_safe(chain 6 symlink) → /tmp/real.py  ← berhasil meski depth > 5
MAX_SYMLINK_DEPTH=5 adalah dead code
```

### Steps to Reproduce
```python
# Buat chain symlink depth 6
resolve_safe(l6)  # Harusnya None (depth > 5), tapi return real path
```

### Expected Behavior
Depth guard aktif melindungi dari symlink loop yang dalam.

### Actual Behavior
Depth guard tidak pernah aktif. Perlindungan sebenarnya datang dari OS (Linux kernel membatasi symlink follow ke 40 level dan raise `ELOOP`), bukan dari kode ini.

### Root Cause
Penggunaan `path.resolve()` yang sudah OS-level resolve sebelum rekursi membuat depth counter tidak pernah naik secara efektif. Untuk membuat depth guard bekerja, perlu iterasi manual lewat `os.readlink()` tanpa memanggil `resolve()`.

### Blast Radius
Local — hanya `resolve_safe()`.

### Impact
Tidak ada perlindungan nyata dari symlink loop (meski OS sendiri yang menanggani di Linux). Kode memberikan false sense of security. Jika diport ke platform lain dengan symlink behavior berbeda, bisa jadi masalah.

### Recommendation
Ganti dengan implementasi yang benar-benar iteratif:
```python
def resolve_safe(path: Path, depth: int = 0) -> Path | None:
    for _ in range(MAX_SYMLINK_DEPTH + 1):
        if not path.is_symlink():
            return path
        try:
            path = Path(os.readlink(path))  # satu level saja
        except OSError:
            return None
    return None  # terlalu dalam
```
Atau cukup pakai `try/except OSError` (ELOOP) di sekitar `path.resolve()`.

### Test Cases
```python
# Setelah fix: chain melebihi MAX_SYMLINK_DEPTH harus return None
result = resolve_safe(link_depth_6)
assert result is None
```

### Regression Risk
Low — fungsi ini hanya dipakai `_relative()` di resolver. Perubahan tidak mempengaruhi happy path.

### Related Code Path
`resolver.py:15–21`, `resolver.py:26–32`

---

## Finding 9

### Title
Resolver memilih `submod.py` daripada `submod/__init__.py` saat keduanya ada

### Severity
Medium

### Likelihood
Medium

### Confidence
High

### Category
Logic Bug / Wrong Resolution

### Scenario
Project punya `pkg/submod.py` dan `pkg/submod/__init__.py` (keduanya ada — bisa terjadi di transisi refactor). `from pkg.submod import ClassName` → Python runtime memilih `pkg/submod/__init__.py`, tapi resolver memilih `pkg/submod.py`.

### Description
`_try_module()` untuk `parts=['pkg','submod','ClassName']` mencoba `candidate` pertama (full path: `pkg/submod/ClassName.py`) lalu `candidate[:-1]` (drop last: `pkg/submod`). Untuk `pkg/submod`, ia mencoba `.py` dulu → menemukan `pkg/submod.py` → return. Tidak pernah sampai ke `pkg/submod/__init__.py`.

Python runtime mengutamakan package (`__init__.py`) atas module (`.py`) ketika nama sama.

### Evidence
```python
# resolver.py baris 35–47
def _try_module(base: Path, parts: list[str], root: Path) -> Path | None:
    for candidate in (parts, parts[:-1]):
        if not candidate:
            continue
        hit = (
            _relative(base.joinpath(*candidate).with_suffix(".py"), root)  # ← .py dicoba dulu
            or _relative(base.joinpath(*candidate, "__init__.py"), root)
        )
        if hit:
            return hit
```

**Output test (`test_scanner_bugs.py` BUG 9):**
```
pkg.submod.ClassName → pkg/submod.py
Python runtime → pkg/submod/__init__.py
MISMATCH
```

### Steps to Reproduce
```python
# Buat pkg/submod.py dan pkg/submod/__init__.py (keduanya ada)
result = resolve_import(ParsedImport(target="pkg.submod.ClassName"), current, root)
# result == Path("pkg/submod.py")  ← salah
# Python runtime pakai pkg/submod/__init__.py
```

### Expected Behavior
Resolver mengutamakan `__init__.py` (package) atas `.py` (module) saat keduanya ada, konsisten dengan Python import system.

### Actual Behavior
`.py` selalu dipilih duluan.

### Root Cause
Urutan `or` di `_try_module`: `.with_suffix(".py")` dievaluasi sebelum `/ "__init__.py"`.

### Blast Radius
Module — hanya resolver, tapi mempengaruhi semua edges di graph.

### Impact
Graph edges menunjuk ke file yang salah → analisis dependensi inaccurate → risk detector dan AI summary bekerja pada konteks yang keliru.

### Recommendation
Swap urutan:
```python
hit = (
    _relative(base.joinpath(*candidate, "__init__.py"), root)  # package dulu
    or _relative(base.joinpath(*candidate).with_suffix(".py"), root)
)
```

### Test Cases
```python
# Keduanya ada: package harus menang
result = resolve_import(ParsedImport(target="pkg.submod.ClassName"), current, root)
assert result == Path("pkg/submod/__init__.py")
```

### Regression Risk
Medium — perubahan urutan bisa membalik resolusi yang saat ini "benar secara kebetulan". Butuh test case komprehensif.

### Related Code Path
`resolver.py:35–47`

---

## Finding 10

### Title
`ParsedFunction.line_start` tidak diisi oleh `ASTParser` (selalu 0)

### Severity
Low

### Likelihood
Very High

### Confidence
High

### Category
Data Completeness / Schema Inconsistency

### Scenario
Consumer Phase 4 atau AI layer membaca `line_start` dari `ParsedFunction` untuk menentukan batas fungsi. Untuk semua output dari `ASTParser`, nilai ini selalu 0.

### Description
`_handle_func()` di `_ScannerVisitor` mengisi `lineno` (legacy field) tapi tidak mengisi `line_start` (BLUEPRINT §4 field). `graph_builder._build_node()` menggunakan `f.lineno` untuk `"line_start"` di graph output, sehingga graph JSON benar — tapi `ParsedFunction.line_start` sendiri selalu 0, yang bisa menyesatkan konsumen yang langsung baca dataclass.

### Evidence
```python
# ast_parser.py baris 125–138
self.functions.append(ParsedFunction(
    name=node.name,
    qualified_name=self._qual(node.name),
    lineno=node.lineno,        # ← diisi
    # line_start tidak diisi → default 0
    ...
))
```

**Output test (`test_scanner_bugs.py` BUG 10):**
```
foo: lineno=1 (terisi) tapi line_start=0 (selalu 0)
bar: lineno=4 (terisi) tapi line_start=0 (selalu 0)
```

### Expected Behavior
`line_start = node.lineno` (sama dengan `lineno`) agar konsumen yang menggunakan field BLUEPRINT §4 mendapat data yang benar.

### Actual Behavior
`line_start` selalu 0 untuk semua fungsi dari `ASTParser`.

### Root Cause
Field `line_start` ditambahkan ke dataclass untuk BLUEPRINT §4 tapi `_handle_func()` tidak diupdate untuk mengisinya.

### Blast Radius
Local — hanya konsumen yang langsung baca `ParsedFunction.line_start`.

### Impact
Konsumen yang mengikuti BLUEPRINT §4 (bukan legacy `lineno`) mendapat 0 untuk semua fungsi.

### Recommendation
```python
# ast_parser.py — _handle_func
self.functions.append(ParsedFunction(
    name=node.name,
    qualified_name=self._qual(node.name),
    lineno=node.lineno,
    line_start=node.lineno,   # ← tambahkan ini
    line_end=node.end_lineno, # ← sekaligus isi line_end
    ...
))
```

### Test Cases
```python
r = safe_parse(Path("test.py"))
for fn in r.functions:
    assert fn.line_start == fn.lineno
    assert fn.line_end > fn.line_start
```

### Regression Risk
Low — penambahan data, tidak mengubah yang sudah ada.

### Related Code Path
`ast_parser.py:125–138`, `scanner/__init__.py:22–38`

---

## Finding 11

### Title
`TreeSitterParser.parse_file()` — `path.stat().st_mtime` di luar `try/except` dan double stat() TOCTOU

### Severity
Medium

### Likelihood
Medium

### Confidence
High

### Category
Error Handling / TOCTOU Race Condition

### Scenario
File di-delete atau di-replace antara operasi `stat()` (size check) dan `read_text()`, atau antara `read_text()` dan `stat()` kedua untuk `st_mtime`. OSError tidak tertangkap → exception propagate keluar `parse_file()`, melanggar kontrak `return None on failure`.

### Description
`parse_file()` memanggil `path.stat()` **dua kali**: sekali untuk size check (baris 54, dalam `try/except OSError`) dan sekali untuk `file_modified_at` (baris 100, di dalam `return ParsedFile(...)` yang tidak ada `try/except`). `OSError` dari stat kedua tidak tertangkap.

### Evidence
```python
# tree_sitter_parser.py baris 52–57: stat pertama (ter-guard)
try:
    size = path.stat().st_size
except OSError:
    return None

# tree_sitter_parser.py baris 92–103: stat kedua (TIDAK ter-guard)
return ParsedFile(
    ...
    file_modified_at=str(path.stat().st_mtime),  # ← OSError tidak tertangkap
    ...
)
```

**Output test (`test_scanner_bugs.py` BUG 11):**
```
path.stat().st_mtime di luar try/except → CONFIRMED
Double stat() call TOCTOU → CONFIRMED
```

### Steps to Reproduce
```
1. Parse file besar
2. Delete file setelah read_text() berhasil
3. stat() di baris 100 raise OSError
4. Exception propagate ke caller
```

### Expected Behavior
`parse_file()` selalu return `ParsedFile | None`, tidak pernah raise exception (sesuai kontrak BaseParser dan docstring `"Return None kalau unsupported/failed"`).

### Actual Behavior
Bisa raise `OSError` yang tidak tertangkap.

### Root Cause
Stat kedua ditambahkan untuk mengisi `file_modified_at` tanpa menambahkan error handling yang konsisten dengan stat pertama.

### Blast Radius
Module — hanya `TreeSitterParser.parse_file()`.

### Impact
- Melanggar kontrak `BaseParser` Protocol
- Caller yang tidak expect exception akan crash
- TOCTOU: file bisa di-replace dengan versi berbeda antara size check dan read, melewati size guard

### Recommendation
```python
# Ambil stat sekali, gunakan untuk keduanya
try:
    stat = path.stat()
    if stat.st_size > _MAX_BYTES:
        logger.warning(...)
        return None
    mtime = str(stat.st_mtime)
except OSError:
    return None

# ... lanjut read, parse ...

return ParsedFile(..., file_modified_at=mtime, ...)
```

### Test Cases
```python
# Mock path.stat() untuk raise OSError di panggilan kedua
# parse_file() harus return None, tidak raise
```

### Regression Risk
Low — hanya konsolidasi dua stat() menjadi satu, tidak ada perubahan logika.

### Related Code Path
`tree_sitter_parser.py:52–57, 92–103`

---

## Finding 12

### Title
`__all__ += [...]` (AugAssign) tidak terdeteksi oleh `visit_Assign`

### Severity
Low

### Likelihood
Medium

### Confidence
High

### Category
Logic Bug / Data Completeness

### Scenario
Module besar membangun `__all__` secara bertahap: `__all__ = ["a"]` di atas, lalu `__all__ += ["b", "c"]` setelah definisi class. Hanya "a" yang masuk ke `exported_names`, "b" dan "c" hilang.

### Description
`visit_Assign` hanya menangani `ast.Assign` (assignment biasa). `__all__ += [...]` di AST adalah `ast.AugAssign`, node yang berbeda dan tidak punya `visit_AugAssign` handler.

### Evidence
```python
# ast_parser.py baris 177–184
def visit_Assign(self, node: ast.Assign) -> None:
    if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
        if isinstance(node.value, (ast.List, ast.Tuple)):
            self.exported_names = [...]
    self.generic_visit(node)
# Tidak ada visit_AugAssign!
```

**Output test (`test_scanner_bugs.py` BUG 12):**
```python
__all__ = ["foo"]
__all__ += ["bar"]
# exported_names = ["foo"]  ← "bar" hilang
```

### Expected Behavior
`exported_names` berisi semua nama dari semua `__all__` assignment (baik `=` maupun `+=`).

### Actual Behavior
Hanya assignment pertama yang terbaca. Augmented assignments diabaikan.

### Root Cause
`ast.AugAssign` dan `ast.Assign` adalah node terpisah di Python AST. Tidak ada fallthrough atau inheritance.

### Blast Radius
Local — hanya `exported_names` di `ParsedFile`.

### Impact
`has_all_definition` dan `exported_names` di graph JSON tidak lengkap untuk module yang menggunakan pola `__all__ +=`.

### Recommendation
```python
def visit_AugAssign(self, node: ast.AugAssign) -> None:
    if isinstance(node.target, ast.Name) and node.target.id == "__all__":
        if isinstance(node.value, (ast.List, ast.Tuple)):
            additions = [
                e.value for e in node.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            self.exported_names.extend(additions)
    self.generic_visit(node)
```

### Test Cases
```python
src = '__all__ = ["foo"]\n__all__ += ["bar"]\n'
r = safe_parse(...)
assert r.exported_names == ["foo", "bar"]
```

### Regression Risk
Low — penambahan handler baru, tidak mengubah yang sudah ada.

### Related Code Path
`ast_parser.py:177–184`

---

## Coverage Checklist

| Dimensi | Status |
|---|---|
| Happy Path | ✓ Dievaluasi |
| Unhappy Path | ✓ 7 crash scenario ditemukan |
| Edge Case | ✓ Symlink loop, stem collision, non-str value |
| Corner Case | ✓ Double stat TOCTOU, AugAssign `__all__` |
| Misuse Case | ✓ Thread worker, non-Python language |
| Boundary Conditions | ✓ 1MB file, depth > MAX_SYMLINK_DEPTH |
| Failure Modes | ✓ OSError, TypeError, ValueError |
| Concurrency | ✓ Finding 7 (signal di thread), Finding 1 (cache race) |
| Security | ✓ Finding 6 (false positive redaction), Finding 8 (symlink guard) |
| Performance | ✓ Finding 1 (unbounded cache) |
| Scalability | ✓ Finding 1 (OOM pada project besar) |
| Reliability | ✓ Finding 11 (broken error contract) |
| Maintainability | ✓ Finding 8 (dead code), Finding 4 (field tidak dipakai) |
| Architecture | ✓ Finding 2 (stem-based lookup tidak scalable) |
| Regression Risk | ✓ Dicantumkan di setiap finding |
| Breaking Change Risk | ✓ Dicantumkan di setiap finding |

---

## Prioritas Fix

| # | Finding | Severity | Action |
|---|---|---|---|
| 5 | `sanitize` crash non-str value | **Critical** | Fix sekarang — Phase 2 parser akan trigger ini |
| 7 | `safe_parse` crash di thread | **High** | Fix sekarang — parallel scan tidak bisa jalan |
| 1 | Cache memory leak | **High** | Fix sekarang — production long-running |
| 2 | Stem collision false negative | **High** | Fix sebelum Phase 2 |
| 4 | `is_private` diabaikan | **Medium** | Fix sebelum Phase 4 non-Python |
| 3 | Circular double-reported | **Medium** | Fix sebelum UI integration |
| 11 | `stat()` TOCTOU / uncaught OSError | **Medium** | Fix bersamaan dengan TreeSitter activation |
| 9 | Package vs module resolution | **Medium** | Fix sebelum edge accuracy dibutuhkan |
| 6 | `auth` false positive | **Medium** | Fix sebelum graph dipublish |
| 12 | `__all__ +=` tidak terdeteksi | **Low** | Fix di Phase 2 |
| 10 | `line_start` selalu 0 | **Low** | Fix bersamaan dengan `line_end` di Phase 2 |
| 8 | Depth guard dead code | **Low** | Fix atau remove komentar misleading |
