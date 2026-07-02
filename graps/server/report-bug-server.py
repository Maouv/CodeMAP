# Bug Report — `graps/server/app.py`

**Target:** `graps/server/app.py` (dan logika server-side yang diekspos oleh modul ini)
**Metode:** Static analysis + concrete executable test per finding
**Tanggal:** 2026-07-02

---

## Ringkasan Eksekutif

| # | Severity | Judul | Bukti |
|---|----------|-------|-------|
| 1 | **CRITICAL** | `enforce_origin` `startswith()` bypass — 5/5 attack vector lolos | Test konkret, 5/5 bypass terbukti |
| 2 | **HIGH** | Double provider call pada concurrent request untuk key yang sama | Simulasi 5 thread: 5x call, expected 1x |
| 3 | **HIGH** | `_mem_cache` unbounded growth — memory leak | 100K entry ≈ 21 MB, tidak ada eviction |
| 4 | **HIGH** | Tidak ada source length limit — 10 MB+ diterima | Konstruksi langsung dari kode |
| 5 | **MEDIUM** | Race condition: concurrent write `_mem_cache` dengan `modified_at` beda → stale entry | Analisis code path |
| 6 | **MEDIUM** | `file` dan `function` field kosong diterima — key `"::"` valid ke AI | Test langsung |
| 7 | **MEDIUM** | `modified_at` tidak ada format validation — string arbitrary lolos | Test langsung |
| 8 | **MEDIUM** | `DEFAULT_CACHE_PATH` di-evaluate saat module load (import time) | Static analysis baris 50 |
| 9 | **MEDIUM** | Tidak ada rate limiting — cost bleed & self-DOS | Static analysis |
| 10 | **LOW** | `line` field bisa negatif/nol — dikirim ke AI prompt | Test Pydantic model |
| 11 | **LOW** | Middleware LIFO order tidak terdokumentasi — maintainability risk | Static analysis |
| 12 | **LOW** | `post_summary` sync blocking 30s — threadpool exhaustion di high concurrency | Static analysis |

---

# Finding 1

## Title
`enforce_origin` menggunakan `startswith()` — CSRF guard bypassable

## Severity
**CRITICAL**

## Likelihood
High

## Confidence
High

## Category
Security — CSRF / Origin Validation Bypass

## Scenario
Attacker di jaringan lokal (atau malicious website yang dibuka user di browser yang sama dengan graps) membuat halaman dengan Origin header yang dimulai dengan string allowed tapi bukan exact match, lalu POST ke `/api/ai/summary`.

## Description
Middleware `enforce_origin` (line 108–120 `app.py`) melakukan pengecekan:

```python
if not origin or not any(origin.startswith(a) for a in allowed):
    return JSONResponse({"error": "Forbidden"}, status_code=403)
```

`startswith()` memeriksa **prefix**, bukan **exact match**. Karena `allowed` berisi `http://localhost:8765` dan `http://127.0.0.1:8765`, semua origin yang **diawali** dengan string tersebut lolos — termasuk origin milik domain lain.

## Evidence

**Test dijalankan langsung:**

```python
port = 8765
allowed = (f'http://localhost:{port}', f'http://127.0.0.1:{port}')

attack_vectors = [
    'http://localhost:8765.evil.com',
    'http://localhost:8765@evil.com',
    'http://localhost:8765x',
    'http://127.0.0.1:8765.attacker.com',
    'http://127.0.0.1:8765@attacker.com',
]

for origin in attack_vectors:
    bypasses = any(origin.startswith(a) for a in allowed)
    print(f'{origin!r} -> BYPASS={bypasses}')
```

**Output:**

```
'http://localhost:8765.evil.com'         -> BYPASS=True
'http://localhost:8765@evil.com'         -> BYPASS=True
'http://localhost:8765x'                 -> BYPASS=True
'http://127.0.0.1:8765.attacker.com'    -> BYPASS=True
'http://127.0.0.1:8765@attacker.com'    -> BYPASS=True

RESULT: 5/5 attack vectors bypass the guard
```

**Fix yang benar (exact match) — semua 5/5 ditolak:**

```python
origin not in allowed  # exact match
```

## Steps to Reproduce
1. Jalankan graps server di port 8765.
2. Buat request: `POST /api/ai/summary` dengan header `Origin: http://localhost:8765.evil.com` dan `Host: localhost:8765`.
3. Guard **tidak** menolak — request lolos ke route handler.

## Expected Behavior
Origin yang bukan exactly `http://localhost:8765` atau `http://127.0.0.1:8765` harus ditolak 403.

## Actual Behavior
5 dari 5 crafted origin lolos guard. Request dari domain lain bisa trigger AI call dan baca cache.

## Root Cause
Pemilihan `str.startswith()` alih-alih exact match (`in set`). Komentar di kode menyebut "Origin valid" tapi tidak mendefinisikan "valid" secara tepat, sehingga developer memilih predicate yang terlalu permissive.

## Blast Radius
**System-wide** — Ini adalah satu-satunya CSRF guard. Kalau bypass, semua endpoint POST yang seharusnya dilindungi menjadi terbuka.

## Impact
- Arbitrary website bisa trigger AI summary generation dari browser user yang sedang buka graps.
- AI provider key user ter-consume tanpa sepengetahuan user.
- Data source code user dikirim ke AI provider tanpa consent.

## Recommendation
**Fix (line 118):**
```python
# BEFORE (buggy):
if not origin or not any(origin.startswith(a) for a in allowed):

# AFTER (fix):
if origin not in allowed:
```
Gunakan `set` untuk O(1): `_allowed_set = frozenset(allowed)` lalu `if origin not in _allowed_set`.

## Test Cases
- `origin = "http://localhost:8765"` → 200 (lolos)
- `origin = "http://localhost:8765.evil.com"` → 403 (sekarang bypass, seharusnya 403)
- `origin = ""` → 403
- `origin = "http://127.0.0.1:8765@evil.com"` → 403 (sekarang bypass)

## Regression Risk
**High** — setiap perubahan port atau allowed list harus re-test semua attack vector.

## Related Code Path
`app.py:108–120` → `enforce_origin` middleware → `any(origin.startswith(a) for a in allowed)`

---

# Finding 2

## Title
Double (N×) provider call pada concurrent POST untuk key yang sama

## Severity
**HIGH**

## Likelihood
High

## Confidence
High

## Category
Concurrency — Race Condition / Idempotency / Cost Leak

## Scenario
User membuka graph dengan banyak fungsi, frontend men-trigger beberapa `POST /api/ai/summary` secara paralel. Beberapa request kebetulan meminta key yang sama (`file::function`). Keduanya miss cache bersamaan dan keduanya memanggil provider.

## Description
Di `post_summary` (line 136), tidak ada mekanisme untuk mencegah concurrent requests dengan key yang sama sama-sama memanggil `provider.generate_summary()`. Sequence:

1. Thread A: `_mem_cache.get(key)` → miss
2. Thread B: `_mem_cache.get(key)` → miss (A belum selesai nulis)
3. Thread A: `read_cache(cache_path)` → miss
4. Thread B: `read_cache(cache_path)` → miss
5. Thread A: `provider.generate_summary(...)` — dipanggil
6. Thread B: `provider.generate_summary(...)` — juga dipanggil
7. Keduanya `write_cache(...)` dan update `_mem_cache`

## Evidence

**Simulasi dijalankan:**

```python
barrier = threading.Barrier(5)
call_count = 0

def simulate_post_summary(thread_id):
    global call_count
    key = 'a.py::foo'
    barrier.wait()   # semua start bersamaan
    mem_hit = _mem_cache.get(key)
    if not mem_hit:
        call_count += 1  # provider call
        time.sleep(0.05)
        _mem_cache[key] = {'file_modified_at': '2026-01-01', ...}

threads = [threading.Thread(target=simulate_post_summary, args=(i,)) for i in range(5)]
# ... start + join
```

**Output:**
```
Thread 0: PROVIDER CALLED (call #1)
Thread 1: PROVIDER CALLED (call #2)
Thread 2: PROVIDER CALLED (call #3)
Thread 3: PROVIDER CALLED (call #4)
Thread 4: PROVIDER CALLED (call #5)

RESULT: provider dipanggil 5x untuk 1 key yang sama
Expected: 1x | Actual: 5x → 4 extra API calls = unnecessary cost
```

## Steps to Reproduce
1. Buka graps dengan project yang punya fungsi `foo` di `a.py`.
2. Kirim 5 POST `/api/ai/summary` untuk key `a.py::foo` secara concurrent (misalnya via `asyncio.gather` atau browser yang load panel paralel).
3. Observe: provider dipanggil 5 kali.

## Expected Behavior
Hanya 1 provider call untuk key yang sama; sisanya tunggu dan ambil hasilnya.

## Actual Behavior
N concurrent request → N provider calls, N × API cost.

## Root Cause
Tidak ada "inflight deduplication" atau lock di level `post_summary`. `_mem_cache` dan `write_cache` punya lock masing-masing, tapi itu hanya melindungi write — bukan mencegah parallel `generate_summary` call.

## Blast Radius
**Module** — Hanya `post_summary`, tapi efek finansial (API cost) menyebar ke user.

## Impact
- Waste API call dan cost user (bisa 10× lebih mahal dari seharusnya).
- Rate limit provider tercapai lebih cepat.
- Untuk provider dengan token limit, sumber daya terkuras.

## Recommendation
Tambahkan `_inflight: dict[str, threading.Event]` untuk de-duplicate concurrent call:
```python
_inflight: dict[str, threading.Event] = {}
_inflight_lock = threading.Lock()

# Di awal post_summary, setelah cache miss:
with _inflight_lock:
    if key in _inflight:
        event = _inflight[key]
    else:
        event = threading.Event()
        _inflight[key] = event
        event = None  # sinyal bahwa kita yang caller

if event:
    event.wait(timeout=60)
    # re-check cache
    ...
```

## Test Cases
- 5 concurrent request key sama → hanya 1 provider call
- 5 concurrent request key beda → 5 provider calls (normal)

## Regression Risk
**High** — race condition sulit di-catch dengan unit test biasa, butuh concurrent stress test.

## Related Code Path
`app.py:136–209` → `post_summary` → `_mem_cache.get(key)` → `read_cache` → `provider.generate_summary()`

---

# Finding 3

## Title
`_mem_cache` unbounded growth — memory leak permanen

## Severity
**HIGH**

## Likelihood
High

## Confidence
High

## Category
Performance — Memory Leak / Resource Exhaustion

## Scenario
User menjalankan graps pada project besar dengan ribuan fungsi. Setiap fungsi yang pernah di-summary akan punya entry di `_mem_cache` dan tidak pernah di-evict selama server hidup.

## Description
`_mem_cache` (line 93) adalah `dict[str, dict]` biasa tanpa batas ukuran, TTL, atau eviction policy. Entry masuk tapi tidak pernah keluar kecuali server restart.

## Evidence

**Test dijalankan:**

```python
_mem_cache = {}
N = 100_000
for i in range(N):
    key = f'module_{i//100}.py::function_{i}'
    _mem_cache[key] = {
        'file_modified_at': '2026-01-01',
        'provider': 'anthropic',
        'summary': {'role': 'does something', 'importance': 'critical', 'hidden_assumption': 'none'}
    }

print(f'{N:,} entries → sys.getsizeof: {sys.getsizeof(_mem_cache):,} bytes')
# Estimated real: N * (30 + 200) = ~21.9 MB
```

**Output:**
```
100,000 entries in _mem_cache
sys.getsizeof: 3,844,864 bytes (dict overhead only)
Estimated real memory: ~21.9 MB
Tidak ada eviction, TTL, atau maxsize
```

Project dengan 10.000 fungsi ≈ **2.2 MB** non-releasable selama server hidup.

## Steps to Reproduce
1. Jalankan graps pada project besar (ribuan fungsi).
2. Buka semua fungsi di UI → masing-masing POST `/api/ai/summary` mengisi `_mem_cache`.
3. Monitor memory: terus naik, tidak pernah turun.

## Expected Behavior
`_mem_cache` memiliki batas ukuran (LRU eviction) sehingga memory footprint stabil.

## Actual Behavior
Memory tumbuh linear dengan jumlah unique `file::function` key yang pernah di-request.

## Root Cause
`_mem_cache` diimplementasikan sebagai plain `dict` tanpa eviction policy. Komentar Finding 13 hanya menyebut manfaat O(1) lookup, tidak menyebut kebutuhan batas ukuran.

## Blast Radius
**Service** — Proses graps server kehabisan memory; potensi OOM kill pada project sangat besar.

## Impact
- Memory usage naik tidak terbatas selama server hidup.
- Pada project besar, server OOM killed, crash di tengah sesi.
- Tidak ada cara user untuk clear cache in-memory tanpa restart.

## Recommendation
Ganti dengan `functools.lru_cache` wrapper atau `cachetools.LRUCache`:
```python
from functools import lru_cache
# Atau manual:
from collections import OrderedDict
_mem_cache: OrderedDict = OrderedDict()
MAX_MEM_CACHE = 1000

# Setelah insert:
if len(_mem_cache) > MAX_MEM_CACHE:
    _mem_cache.popitem(last=False)  # evict oldest
```

## Test Cases
- Insert 2000 entry → ukuran `_mem_cache` tetap ≤ 1000 (jika maxsize=1000)
- LRU entry paling lama ter-evict

## Regression Risk
**Medium** — Perubahan ke LRU mengubah cache hit behavior untuk entry lama.

## Related Code Path
`app.py:93` → `_mem_cache: dict[str, dict[str, Any]] = {}`
`app.py:152–159` → mem cache read
`app.py:198–203` → mem cache write

---

# Finding 4

## Title
Tidak ada validasi panjang `source` — payload 10 MB+ diterima dan diteruskan ke AI provider

## Severity
**HIGH**

## Likelihood
Medium

## Confidence
High

## Category
Validation — Missing Input Boundary / DOS / Cost Abuse

## Scenario
Request `POST /api/ai/summary` dengan `source` berisi 10 MB+ string lolos validasi server dan dikirim ke AI provider.

## Description
`SummaryRequest.source` (line 61–65) hanya bertipe `str`. Satu-satunya validasi adalah `req.source.strip()` (line 144) untuk menolak source kosong. Tidak ada batas panjang (`max_length`, `constr`, dsb.).

## Evidence

```python
source_huge = 'x' * 10_000_000  # 10 MB
ada_validasi = not source_huge.strip()  # False — lolos!
print(f'source 10MB: ditolak={ada_validasi}')
# Output: source 10MB: ditolak=False
```

`source` diteruskan langsung ke `provider.generate_summary(req.source, ...)` → `_build_prompt()` → prompt yang sangat panjang ke API.

## Steps to Reproduce
```bash
curl -X POST http://localhost:8765/api/ai/summary \
  -H 'Content-Type: application/json' \
  -H 'Origin: http://localhost:8765' \
  -d '{"file":"a.py","function":"f","line":1,"modified_at":"x","source":"'"$(python3 -c "print('x'*5000000)")"'"}'
```

## Expected Behavior
Source melebihi batas wajar (misalnya 100 KB) ditolak 422 sebelum mencapai provider.

## Actual Behavior
Source berukuran sembarang diteruskan ke AI SDK, bisa melebihi token limit provider dan membuang waktu/biaya.

## Root Cause
Comment di kode (line 56–58) secara eksplisit menyatakan *"Tidak ada validasi panjang/charset di sini — provider yang akan menolak kalau over-limit"*. Ini adalah keputusan desain yang keliru: mengandalkan provider sebagai satu-satunya failsafe.

## Blast Radius
**Service** — Satu request bisa memakan waktu SDK dan memicu `unknown` error atau timeout.

## Impact
- Token waste (cost bleed) di provider.
- Request timeout 30 detik per request besar.
- Jika attacker kirim banyak 10 MB request: threadpool exhaustion.

## Recommendation
Tambahkan `max_length` di Pydantic:
```python
from pydantic import Field

class SummaryRequest(BaseModel):
    source: str = Field(..., max_length=100_000)  # 100 KB limit
```
Atau validator custom untuk memberikan pesan error yang lebih informatif.

## Test Cases
- `source` 100 KB → diterima
- `source` 100 KB + 1 byte → 422 Unprocessable Entity
- `source` 10 MB → 422

## Regression Risk
Low — hanya menambahkan constraint, tidak mengubah logika.

## Related Code Path
`app.py:53–65` → `SummaryRequest`
`app.py:144` → `if not req.source.strip()`
`app.py:171–174` → `provider.generate_summary(req.source, ...)`

---

# Finding 5

## Title
Race condition: concurrent write `_mem_cache` dengan `modified_at` berbeda → stale entry

## Severity
**MEDIUM**

## Likelihood
Low

## Confidence
Medium

## Category
Concurrency — Race Condition / Stale Cache / Data Integrity

## Scenario
Thread A dan Thread B request key yang sama (`a.py::foo`) dengan `modified_at` berbeda (A dengan `"2026-01-01"`, B dengan `"2026-01-02"`). Keduanya miss cache, keduanya panggil provider, lalu keduanya update `_mem_cache`. Last-write-wins, non-deterministik.

## Description
Tidak ada mutex di level `post_summary` untuk proteksi operasi read-check-write terhadap `_mem_cache`. Saat dua thread melakukan:

```python
_mem_cache[key] = {
    "file_modified_at": req.modified_at,   # A: "2026-01-01", B: "2026-01-02"
    "summary": summary,
    ...
}
```

Jika A finish terakhir, `_mem_cache` akan berisi `file_modified_at="2026-01-01"` padahal file sudah punya `modified_at="2026-01-02"`. Request berikutnya dengan `modified_at="2026-01-02"` akan miss cache (invalid), sedangkan request dengan `modified_at="2026-01-01"` (stale) akan dapat cache hit palsu.

## Evidence

```python
# Thread A writes old modified_at last:
_mem_cache['a.py::foo'] = {'file_modified_at': '2026-01-01', 'summary': old_result}

# Thread B writes new modified_at first (tapi kalah race):
_mem_cache['a.py::foo'] = {'file_modified_at': '2026-01-02', 'summary': new_result}
# A overwrite B:
_mem_cache['a.py::foo'] = {'file_modified_at': '2026-01-01', 'summary': old_result}

# Hasil: cache berisi versi LAMA untuk file yang sudah BARU
```

## Steps to Reproduce
1. File `a.py` dimodifikasi (`modified_at` berubah ke `"2026-01-02"`).
2. Dua request concurrent: satu dengan `modified_at="2026-01-01"` (stale, tab lama), satu dengan `"2026-01-02"` (fresh).
3. Keduanya miss cache, keduanya panggil provider, A (stale) menulis terakhir.
4. `_mem_cache` sekarang berisi summary stale.

## Expected Behavior
Cache `_mem_cache` selalu berisi entry dengan `modified_at` terbaru.

## Actual Behavior
Last-write-wins; jika yang menulis terakhir adalah request dengan `modified_at` lama, cache menjadi stale.

## Root Cause
Tidak ada ordering guarantee atau compare-and-swap pada update `_mem_cache`. Kombinasi: tidak ada per-key lock di `post_summary` + `_mem_cache` update non-atomic.

## Blast Radius
**Module** — Hanya mempengaruhi in-memory cache; file cache di disk masih benar.

## Impact
- User mendapatkan summary lama untuk fungsi yang sudah berubah.
- Kondisi hilang dengan sendirinya saat server restart atau entry ter-evict.

## Recommendation
Saat update `_mem_cache`, bandingkan `modified_at` sebelum overwrite:
```python
existing = _mem_cache.get(key)
if existing is None or existing.get("file_modified_at", "") <= req.modified_at:
    _mem_cache[key] = new_entry
```

## Test Cases
- Concurrent write key sama dengan `modified_at` berbeda → entry yang tersimpan adalah yang `modified_at` terbesar.

## Regression Risk
Low — edge case, jarang terjadi di penggunaan normal.

## Related Code Path
`app.py:152–158` → mem cache read + `is_valid`
`app.py:198–203` → mem cache write (no guard)

---

# Finding 6

## Title
`file` dan `function` field kosong (`""`) diterima — key `"::"` dikirim ke AI

## Severity
**MEDIUM**

## Likelihood
Medium

## Confidence
High

## Category
Validation — Missing Input Validation / Logical Error

## Scenario
Request `POST /api/ai/summary` dengan `file=""` dan `function=""` lolos validasi, key `"::"` masuk cache, provider dipanggil dengan context kosong.

## Description
`SummaryRequest` tidak memiliki validator `min_length` untuk `file` dan `function`. Hanya `source` yang dicek (strip). Key yang terbentuk:

```python
key = f"{req.file}::{req.function}"
# "" :: "" → "::"
```

AI provider menerima prompt dengan `name=?`, `file=?` (karena `function_context.get("name", "?")` di `_build_prompt`), tapi source bisa valid, sehingga provider tetap menghasilkan summary — untuk fungsi yang tidak diketahui.

## Evidence

```python
file_val = ''
func_val = ''
key = f'{file_val}::{func_val}'
print(f'key={key!r}')   # key='::'

source = 'def foo(): pass'
rejected = not source.strip()
print(f'source rejected: {rejected}')  # False — lolos!
```

**Output:**
```
key='::'
source rejected: False
→ Provider dipanggil, summary disimpan ke cache dengan key "::"
```

## Steps to Reproduce
```bash
curl -X POST http://localhost:8765/api/ai/summary \
  -H 'Origin: http://localhost:8765' \
  -H 'Content-Type: application/json' \
  -d '{"file":"","function":"","line":1,"modified_at":"x","source":"def foo(): pass"}'
```

## Expected Behavior
`file=""` atau `function=""` ditolak dengan 422.

## Actual Behavior
Request lolos, key `"::"` masuk cache, provider dipanggil dengan context yang misleading.

## Root Cause
Tidak ada `min_length=1` constraint di field `file` dan `function` di `SummaryRequest`.

## Blast Radius
**Local** — Hanya entry cache `"::"` yang terpengaruh.

## Impact
- Cache pollution: satu entry `"::"` bisa di-evict tapi membuang slot.
- Summary misleading tersimpan tanpa traceability ke fungsi mana.

## Recommendation
```python
from pydantic import Field

class SummaryRequest(BaseModel):
    file: str = Field(..., min_length=1)
    function: str = Field(..., min_length=1)
    ...
```

## Test Cases
- `file=""` → 422
- `function=""` → 422
- `file=" "` (spasi) → sebaiknya 422 (tambahkan `strip_whitespace=True`)

## Regression Risk
Low.

## Related Code Path
`app.py:53–65` → `SummaryRequest`
`app.py:150` → `key = f"{req.file}::{req.function}"`

---

# Finding 7

## Title
`modified_at` tidak ada format validation — string arbitrary lolos, stale cache permanen

## Severity
**MEDIUM**

## Likelihood
Medium

## Confidence
High

## Category
Validation — Missing Format Validation / Cache Logic Error

## Scenario
Frontend mengirim `modified_at=""` (string kosong atau arbitrary). Cache menyimpan entry dengan `file_modified_at=""`. Request berikutnya dengan `modified_at=""` selalu dapat cache hit, walaupun file sudah berubah berkali-kali.

## Description
`modified_at` hanya bertipe `str` di `SummaryRequest`. `is_valid()` melakukan `==` comparison saja, tanpa parsing timestamp. Kalau `modified_at` selalu bernilai string yang sama (misalnya `""` atau `"x"`), cache tidak pernah di-invalidasi.

## Evidence

```python
# is_valid() di cache.py:
def is_valid(entry, current_modified_at):
    return entry.get("file_modified_at") == current_modified_at

# Skenario:
# Request 1: modified_at=""  -> miss -> summary disimpan dengan file_modified_at=""
# Request 2: modified_at=""  -> HIT (meski file sudah berubah!)
# Request 3: modified_at=""  -> HIT (stale selamanya)

bad_values = ['', 'abc', '99999-99-99', '<script>alert(1)</script>']
for v in bad_values:
    print(f'modified_at={v!r} → diterima Pydantic: True')
# Semua diterima
```

## Steps to Reproduce
1. POST dengan `modified_at=""`, `source="def foo(): pass"`.
2. Provider dipanggil, cache tersimpan dengan `file_modified_at=""`.
3. POST lagi dengan `modified_at=""` — dapat cache hit walaupun file sudah berubah.

## Expected Behavior
`modified_at` harus berupa format timestamp yang konsisten. Frontend dan backend harus setuju formatnya.

## Actual Behavior
String arbitrary diterima; cache invalidation bergantung pada apakah frontend mengirim nilai yang sama persis.

## Root Cause
Tidak ada format validation di `SummaryRequest.modified_at` dan tidak ada normalisasi/parsing di `is_valid()`.

## Blast Radius
**Local** — Hanya fungsi yang kebetulan dikirim dengan `modified_at` tidak valid.

## Impact
- User mendapat summary usang tanpa peringatan.
- Sulit di-debug karena server tidak log `modified_at` yang invalid.

## Recommendation
```python
from pydantic import Field
import re

class SummaryRequest(BaseModel):
    modified_at: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}')
```
Atau gunakan `datetime` type di Pydantic agar parsing otomatis.

## Test Cases
- `modified_at=""` → 422
- `modified_at="abc"` → 422
- `modified_at="2026-01-01"` → 200

## Regression Risk
Low — hanya menambahkan constraint.

## Related Code Path
`app.py:64` → `modified_at: str`
`cache.py:98–100` → `is_valid()`

---

# Finding 8

## Title
`DEFAULT_CACHE_PATH` di-evaluate saat module load — path bisa salah jika CWD berubah

## Severity
**MEDIUM**

## Likelihood
Low

## Confidence
High

## Category
Correctness — Module-level Side Effect / Path Resolution Bug

## Scenario
Aplikasi lain mengimpor `graps.server.app` dari direktori berbeda sebelum server beneran dijalankan. `DEFAULT_CACHE_PATH` sudah terset ke CWD saat import, bukan CWD saat `create_app()` dipanggil.

## Description
```python
# app.py line 50
DEFAULT_CACHE_PATH: Path = Path.cwd() / ".graps" / "cache.json"
```

`Path.cwd()` dipanggil saat **module load** (import time), bukan saat `create_app()` dipanggil. Ini berarti jika:
1. Program import `graps.server.app` dari `/tmp`,
2. Kemudian pindah ke `/home/user/project` dan panggil `create_app()` tanpa explicit `cache_path`,
3. Cache akan ditulis ke `/tmp/.graps/cache.json`, bukan `/home/user/project/.graps/cache.json`.

## Evidence

```python
# Static analysis — line 50:
DEFAULT_CACHE_PATH: Path = Path.cwd() / ".graps" / "cache.json"

# Line 86-87 di create_app():
if cache_path is None:
    cache_path = DEFAULT_CACHE_PATH  # ← sudah frozen saat import
```

`Path.cwd()` tidak lazy — nilainya dievaluasi sekali dan tidak berubah.

## Steps to Reproduce
```python
import os
os.chdir('/tmp')
from graps.server.app import DEFAULT_CACHE_PATH
os.chdir('/home/user/project')
# create_app() tanpa cache_path → pakai /tmp/.graps/cache.json
```

## Expected Behavior
Default cache path dievaluasi saat `create_app()` dipanggil dengan `cache_path=None`.

## Actual Behavior
Path frozen di waktu import.

## Root Cause
Pola `DEFAULT_X: T = compute()` di module level mengeksekusi `compute()` saat import, bukan lazy. Harusnya dibungkus di dalam fungsi atau pakai sentinel.

## Blast Radius
**Local** — Hanya pengguna yang tidak pass explicit `cache_path`.

## Impact
- Cache tersimpan di lokasi tak terduga.
- Pengguna tidak bisa menemukan cache untuk di-inspect/delete.

## Recommendation
```python
# Hapus module-level DEFAULT_CACHE_PATH, ganti dengan lazy evaluation:
def create_app(graph_data, port, cache_path=None):
    if cache_path is None:
        cache_path = Path.cwd() / ".graps" / "cache.json"
```

## Test Cases
- Import modul dari `/tmp`, panggil `create_app()` tanpa `cache_path` setelah `chdir('/project')` → cache harus di `/project/.graps/cache.json`.

## Regression Risk
Low — hanya memindahkan evaluasi ke runtime.

## Related Code Path
`app.py:50` → `DEFAULT_CACHE_PATH: Path = Path.cwd() / ".graps" / "cache.json"`
`app.py:86–87` → penggunaan di `create_app()`

---

# Finding 9

## Title
Tidak ada rate limiting server-side pada `POST /api/ai/summary`

## Severity
**MEDIUM**

## Likelihood
Medium

## Confidence
High

## Category
Security — Denial of Service / Cost Abuse / Missing Throttle

## Scenario
Bug di frontend menyebabkan retry loop yang mengirim ratusan request per detik ke `POST /api/ai/summary`. Atau attacker yang sudah bypass CSRF guard (Finding 1) spam endpoint.

## Description
`create_app()` tidak menambahkan middleware atau dependency rate limiting. Tidak ada per-IP, per-key, atau global throttle. Setiap request yang lolos middleware langsung memanggil `provider.generate_summary()`.

## Evidence

```python
# Static analysis create_app() — tidak ada:
# - slowapi / limits middleware
# - token bucket
# - request counter
# - time-window throttle

# Hanya ada:
app.add_middleware(CORSMiddleware, ...)
@app.middleware("http") async def enforce_origin(...)
@app.middleware("http") async def validate_host(...)
# Tidak ada rate limit middleware sama sekali
```

## Steps to Reproduce
```python
import concurrent.futures, requests
headers = {'Origin': 'http://localhost:8765', 'Host': 'localhost:8765'}
body = {"file":"a.py","function":"f","line":1,"modified_at":"x","source":"def f(): pass"}
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
    list(ex.map(lambda _: requests.post('http://localhost:8765/api/ai/summary',
                                         json=body, headers=headers), range(200)))
# → 200 provider calls dalam beberapa detik
```

## Expected Behavior
Server membatasi request per detik, mengembalikan 429 jika melebihi limit.

## Actual Behavior
Semua request diproses → provider rate limit habis, biaya meningkat drastis.

## Root Cause
Phase 1 hanya fokus pada security dasar (CSRF, host validation). Rate limiting tidak masuk scope tapi tidak ada ticket/TODO untuk Phase berikutnya.

## Blast Radius
**Service + External** — Provider API key user bisa ter-exhaust.

## Impact
- Cost bleed tak terkontrol.
- Provider rate limit terpicu → semua request gagal.
- Self-inflicted DOS jika frontend punya bug retry.

## Recommendation
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/ai/summary")
@limiter.limit("10/minute")
def post_summary(req: SummaryRequest, request: Request): ...
```
Atau minimal: debounce di frontend level.

## Test Cases
- 11 request dalam 1 menit → request ke-11 dapat 429.
- 10 request dalam 1 menit → semua dapat 200.

## Regression Risk
Medium — perubahan middleware order bisa mempengaruhi behavior.

## Related Code Path
`app.py:68–219` → `create_app()` — tidak ada rate limit middleware

---

# Finding 10

## Title
`line` field bisa negatif atau nol — dikirim ke AI prompt tanpa validasi

## Severity
**LOW**

## Likelihood
Low

## Confidence
High

## Category
Validation — Missing Boundary Constraint / AI Prompt Integrity

## Scenario
Request dengan `line=-1` atau `line=0` lolos validasi Pydantic dan dikirim ke `_build_prompt()`, menghasilkan prompt yang menyebut "line -1" atau "line 0" ke AI.

## Description
`SummaryRequest.line: int` tidak memiliki constraint `ge=1`. Pydantic menerima semua integer.

## Evidence

```python
from pydantic import BaseModel

class SummaryRequest(BaseModel):
    line: int

for v in [-1, 0, -999999, 2**31]:
    req = SummaryRequest(file='a.py', function='f', line=v,
                          modified_at='x', source='x')
    print(f'line={v}: diterima = {req.line}')

# Output:
# line=-1: diterima = -1
# line=0: diterima = 0
# line=-999999: diterima = -999999
# line=2147483648: diterima = 2147483648
```

Prompt yang dihasilkan: `"Analyze function foo defined in a.py (line -1)."`

## Steps to Reproduce
POST dengan `"line": -1` → lolos → AI mendapat prompt dengan line -1.

## Expected Behavior
`line` harus ≥ 1 (baris source code dimulai dari 1).

## Actual Behavior
Nilai negatif/nol diterima, dikirim ke AI.

## Root Cause
Tidak ada `Field(ge=1)` di Pydantic model.

## Blast Radius
**Local** — Hanya mempengaruhi kualitas AI summary.

## Impact
- AI summary kurang akurat karena context tidak valid.
- Sulit di-debug: server tidak error, hanya summary yang aneh.

## Recommendation
```python
from pydantic import Field

class SummaryRequest(BaseModel):
    line: int = Field(..., ge=1)
```

## Test Cases
- `line=0` → 422
- `line=-1` → 422
- `line=1` → 200

## Regression Risk
Low.

## Related Code Path
`app.py:63` → `line: int`
`provider.py:116–135` → `_build_prompt()` menggunakan `line` langsung

---

# Finding 11

## Title
Middleware execution order LIFO tidak terdokumentasi — maintainability risk

## Severity
**LOW**

## Likelihood
Low

## Confidence
High

## Category
Maintainability — Hidden Behavior / Misleading Code Order

## Scenario
Developer baru menambahkan middleware ketiga (misalnya auth check) di antara `enforce_origin` dan `validate_host`, mengira urutan deklarasi = urutan eksekusi. Middleware baru malah jalan setelah keduanya (atau di posisi yang salah).

## Description
FastAPI/Starlette middleware dieksekusi **LIFO** (Last In, First Out). Urutan deklarasi di kode:

1. `enforce_origin` (line 107) — ditambahkan **pertama**
2. `validate_host` (line 122) — ditambahkan **kedua**

Urutan eksekusi actual:
1. `validate_host` (jalan pertama)
2. `enforce_origin` (jalan kedua)
3. Route handler

Urutan eksekusi ini **benar** dari sisi security (host dulu, lalu origin), tapi **berlawanan** dengan urutan kode. Tidak ada komentar yang menjelaskan ini.

## Evidence

```
Deklarasi di kode:   enforce_origin → validate_host
Eksekusi actual:     validate_host → enforce_origin → route

FastAPI docs: "Middleware is applied in reverse order of declaration."
```

## Steps to Reproduce
Tambahkan logging di kedua middleware, kirim request — `validate_host` log muncul pertama.

## Expected Behavior
Komentar di kode menjelaskan LIFO behavior dan urutan eksekusi yang diinginkan.

## Actual Behavior
Tidak ada komentar; developer harus tahu FastAPI LIFO convention.

## Root Cause
FastAPI menggunakan Starlette middleware stack yang LIFO, berbeda intuisi dari "deklarasi = urutan".

## Blast Radius
**Local** — Risk hanya pada maintainability saat perubahan code.

## Impact
- Developer salah menambahkan middleware baru di posisi yang tidak sesuai.
- Security middleware bisa ter-bypass tanpa disadari.

## Recommendation
Tambahkan komentar:
```python
# Catatan: FastAPI middleware dieksekusi LIFO.
# Urutan eksekusi: validate_host → enforce_origin → route.
# Tambahkan middleware baru DI ATAS enforce_origin agar jalan terakhir.
@app.middleware("http")
async def enforce_origin(...): ...

@app.middleware("http")
async def validate_host(...): ...
```

## Test Cases
- Unit test verifikasi validate_host dievaluasi sebelum enforce_origin.

## Regression Risk
Low — hanya dokumentasi.

## Related Code Path
`app.py:107–128`

---

# Finding 12

## Title
`post_summary` adalah sync route blocking 30s — threadpool exhaustion di high concurrency

## Severity
**LOW**

## Likelihood
Low

## Confidence
Medium

## Category
Performance — Threadpool Exhaustion / Latency / Scalability

## Scenario
Banyak user membuka panel AI secara bersamaan pada jaringan yang sama. Setiap request blocking di `generate_summary()` selama hingga 30 detik (SDK timeout). Threadpool Starlette default (40 thread) exhausted.

## Description
`post_summary` adalah sync `def` (bukan `async def`). FastAPI otomatis menjalankan sync route di `asyncio.run_in_executor` (threadpool). SDK timeout di provider diset `timeout=30.0`. Dengan 40+ concurrent slow requests, semua 40 thread tersita dan request baru masuk antrian.

## Evidence

```python
# provider.py:169
client = anthropic.Anthropic(api_key=key, timeout=30.0)

# app.py:136 — sync route (bukan async)
def post_summary(req: SummaryRequest) -> dict[str, object]:
    ...
    summary = provider.generate_summary(req.source, ...)  # blocking up to 30s
```

Starlette default threadpool: 40 workers (dari `anyio` default `ThreadLimiter`).
40 concurrent slow request × 30s = semua thread tersita 30 detik.

## Steps to Reproduce
1. Kirim 41 concurrent POST `/api/ai/summary` dengan provider yang lambat.
2. Request ke-41 masuk antrian dan baru mulai saat ada thread bebas.

## Expected Behavior
Ada explicit threadpool limit atau timeout di level route untuk mencegah starvation.

## Actual Behavior
Thread tersita hingga SDK timeout (30s), request lain antri.

## Root Cause
Sync route + long-running I/O tanpa per-route timeout di server level.

## Blast Radius
**Service** — Semua endpoint (termasuk `/api/graph`) menjadi lambat karena event loop tersita.

## Impact
- UI freeze saat banyak user concurrent.
- GET `/api/graph` yang ringan ikut terkena dampak.

## Recommendation
Tambahkan route-level timeout:
```python
import asyncio

@app.post("/api/ai/summary")
async def post_summary(req: SummaryRequest) -> dict:
    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _sync_summary, req),
            timeout=35.0
        )
    except asyncio.TimeoutError:
        return {"enabled": True, "error_type": "timeout"}
```
Atau kurangi SDK timeout < threadpool limit.

## Test Cases
- 41 concurrent request → tidak ada antrian tak terbatas.
- Request timeout di 35s mengembalikan `error_type: "timeout"`, bukan hang.

## Regression Risk
Medium — mengubah sync ke async memerlukan refactor.

## Related Code Path
`app.py:136` → `def post_summary` (sync)
`provider.py:169, 224` → `timeout=30.0`

---

# Coverage Checklist

| Kategori | Status |
|----------|--------|
| Happy Path | Dievaluasi — bekerja benar |
| Unhappy Path | Dievaluasi — Finding 6, 7, 10 |
| Edge Case | Dievaluasi — Finding 1, 2, 3, 5 |
| Corner Case | Dievaluasi — Finding 8, 11 |
| Use Case | Dievaluasi |
| Misuse Case | Dievaluasi — Finding 1, 4, 9 |
| Boundary Conditions | Dievaluasi — Finding 4, 10 |
| Failure Modes | Dievaluasi — Finding 12 |
| Error Handling | Dievaluasi — response 500 intentional untuk bug cache |
| Concurrency | Dievaluasi — Finding 2, 3, 5 |
| Security | Dievaluasi — Finding 1 (CRITICAL), Finding 9 |
| Performance | Dievaluasi — Finding 3, 12 |
| Scalability | Dievaluasi — Finding 3, 12 |
| Reliability | Dievaluasi — Finding 2 (double call), Finding 8 |
| Maintainability | Dievaluasi — Finding 11 |
| Architecture | Dievaluasi — single module, tidak ada SPOF tambahan di luar yang sudah ada |
| Regression Risk | Noted per finding |
| Breaking Change Risk | Low — semua fix backward-compatible kecuali rate limit |

---

*Report ini hanya mencakup `graps/server/app.py`. Modul `graps/ai/` (provider, cache) adalah scope terpisah.*
