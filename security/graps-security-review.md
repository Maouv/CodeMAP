# Security Review — graps
> Reviewer: Security Analyst  
> Date: 2026-06-27  
> Scope: Planning documents (architect-review.md, handoff.md, python-packaging-reviewer.md)  
> Status: **PRE-IMPLEMENTATION REVIEW** — Vulnerabilities ditemukan di design phase

---

## Executive Summary

graps adalah CLI tool yang men-serve localhost web server (FastAPI) untuk memvisualisasikan dependency graph Python codebase. Tool ini dijalankan **per-user di localhost**, bukan multi-user server — fakta ini mengubah threat model secara fundamental.

**Threat model yang benar untuk graps:**
- Attacker bukan remote hacker di internet
- Attacker adalah: (1) malicious website yang buka di browser saat tool sedang running, (2) proses lain di machine yang sama, (3) user lain di shared machine (multi-user Linux)
- Tidak ada "server" yang di-hack — data tetap di machine user
- Risk utama: **data dari codebase yang di-scan bocor ke tempat yang salah** + **API key ter-expose** + **browser dijadikan attack vector via CORS/CSRF**

Ditemukan **9 security findings** (2 Critical, 3 High, 3 Medium, 1 Low) setelah reframing dengan threat model yang tepat.

---

## Bagian I — Pertanyaan Spesifik

---

### Q1: FastAPI Server di Localhost — Attack Surface, CORS, Local Network Exposure

**Jawaban singkat: Ya, ada attack surface yang nyata, bahkan di localhost.**

#### A. Localhost Bukan Berarti Aman

"Dijalankan di localhost" sering diasumsikan berarti aman — ini adalah asumsi yang salah. Browser yang berjalan di machine yang sama bisa melakukan request ke `http://localhost:8765` dari halaman manapun yang dibuka user, termasuk tab yang sedang buka `evil.com`. Ini adalah **DNS rebinding + CSRF attack surface** yang nyata.

**Attack scenario konkret:**

```
1. User jalankan: graps ./myproject (server up di localhost:8765)
2. User buka browser, lalu buka tab baru untuk lihat YouTube / baca artikel
3. Tab tersebut inject iframe atau fetch() ke http://localhost:8765/api/ai/summary
4. Request berhasil karena server tidak ada CORS guard + tidak ada auth
5. Attacker trigger AI call menggunakan API key user → habiskan billing quota
```

#### B. Default Uvicorn Bind: Potensi Masalah di Shared Machine

Dari dokumentasi desain tidak disebutkan `host` parameter. Default Uvicorn adalah `0.0.0.0` — semua interface, bukan hanya loopback.

```python
# Apa yang kemungkinan ditulis developer tanpa pikir panjang:
uvicorn.run(app, port=8765)  # bind ke 0.0.0.0 secara default

# Konsekuensi di shared machine (kampus, kantor, VPS dengan team):
# User lain di network yang sama bisa akses http://192.168.1.x:8765
# Dan lihat seluruh graph JSON codebase kamu
```

Untuk laptop personal yang tidak pernah di network publik, ini low risk. Untuk developer yang kerja di cafe, kantor dengan shared WiFi, atau di VPS/remote machine — **ini adalah data leak yang nyata.**

#### C. CORS — Apa yang Perlu Di-implement

CORS di localhost-only tool punya nuance khusus. Browser **tidak enforce CORS untuk `null` origin** (misalnya request dari file:// atau beberapa iframe), dan ada edge case di chromium yang bisa bypass localhost CORS.

Yang harus di-implement:

```python
from fastapi.middleware.cors import CORSMiddleware

# JANGAN: allow_origins=["*"]
# JANGAN: allow_origins=["http://localhost:8765"] saja — karena 127.0.0.1 ≠ localhost di beberapa browser

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{PORT}",
        f"http://127.0.0.1:{PORT}",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-graps-Request"],
)
```

Tapi CORS saja **tidak cukup** — CORS adalah browser enforcement, bukan server enforcement. `curl`, `requests`, atau process lain di machine tidak peduli CORS. Perlu Origin header check di server side:

```python
@app.middleware("http")
async def enforce_origin(request: Request, call_next):
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        allowed = f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"
        if origin and not any(origin.startswith(a) for a in allowed):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
    return await call_next(request)
```

#### D. DNS Rebinding Attack

Ini adalah attack yang lebih advanced tapi nyata untuk localhost tool:

```
1. Attacker set up evil.com dengan TTL DNS sangat pendek (60s)
2. User buka evil.com → resolve ke attacker's server IP
3. JavaScript di evil.com jalan di browser
4. 60 detik kemudian, evil.com DNS di-rebind ke 127.0.0.1
5. Browser sekarang anggap evil.com = localhost → same-origin dengan graps server
6. JavaScript bisa fetch() ke "evil.com:8765" yang sebenarnya adalah localhost:8765
```

Mitigasi: tambahkan `Host` header validation:

```python
@app.middleware("http")
async def validate_host(request: Request, call_next):
    host = request.headers.get("host", "")
    if host not in (f"localhost:{PORT}", f"127.0.0.1:{PORT}"):
        return JSONResponse({"error": "Invalid Host"}, status_code=400)
    return await call_next(request)
```

**Kesimpulan Q1:** Attack surface ada dan nyata. Dua mitigasi yang wajib: (1) hardcode `host="127.0.0.1"` di Uvicorn, (2) implement CORS + Origin check + Host validation. CSRF protection untuk POST endpoint juga diperlukan (lihat M-02).

---

### Q2: BYOK API Key — Apakah Bisa Ter-leak ke Cache atau Log?

**Jawaban singkat: Tidak secara langsung di cache, tapi ada beberapa indirect leak paths yang berbahaya.**

#### A. Cache — Desain Aman, Tapi Ada Gap

Dari schema `cache.json` yang didokumentasikan:

```json
{
  "entries": {
    "services/user_service.py::get_user": {
      "generated_at": "2026-06-27T10:00:00",
      "file_modified_at": "...",
      "provider": "anthropic",    ← nama provider, BUKAN key
      "summary": { ... }
    }
  }
}
```

API key **tidak disimpan langsung** di cache — ini desain yang benar. Tapi ada gap:

**Gap 1 — Error response dari AI provider bisa mengandung key fragment:**

```python
# Jika implementasi exception handler tidak hati-hati:
except anthropic.AuthenticationError as e:
    logger.error(f"Auth failed: {e}")  # e.message bisa berisi "Invalid API key: sk-ant-..."
    # → key ter-log di stdout/stderr
```

**Gap 2 — Request body bisa ter-log jika ada debug middleware:**

Beberapa FastAPI tutorial mengajarkan logging middleware yang log `request.body()`. Jika developer menambahkan ini untuk debugging, dan POST body ke `/api/ai/summary` berisi informasi yang bisa dikombinasikan dengan key yang ada di environment — ini membuat forensic trail yang tidak diinginkan.

**Gap 3 — Uvicorn access log tidak log body, tapi log URL:**

```
INFO:     127.0.0.1:54321 - "POST /api/ai/summary HTTP/1.1" 200 OK
```

Ini aman — URL tidak berisi key. Tapi jika ada developer yang "membantu" dengan menambahkan key ke query param (anti-pattern tapi sering terjadi di prototype):

```
GET /api/ai/summary?key=sk-ant-...   ← KEY AKAN TER-LOG DI UVICORN LOG
```

Pastikan key **tidak pernah** masuk ke URL atau query string.

#### B. Environment Variable — Inheritance Risk

Ketika graps spawn subprocess (saat ini belum ada, tapi mungkin di future untuk timeout implementation via `multiprocessing`), environment variable **diwarisi oleh child process secara default**:

```python
# BERBAHAYA jika subprocess ditambahkan di future:
subprocess.run(["some_tool"], env=os.environ)  # ANTHROPIC_API_KEY ikut ter-pass

# AMAN:
subprocess.run(["some_tool"], env={
    k: v for k, v in os.environ.items() 
    if not k.endswith("_API_KEY")  # strip semua keys
})
```

Ini perlu di-document sebagai coding standard dari awal, sebelum ada yang nulis subprocess call tanpa mikir.

#### C. Traceback Exposure

Python traceback bisa mengekspose nilai variable lokal dalam beberapa kondisi:

```python
# Jika key disimpan sebagai attribute dan ada exception saat request:
self.api_key = os.getenv("ANTHROPIC_API_KEY")
response = self.client.messages.create(...)  # ← crash here
# Traceback akan show: self.api_key = "sk-ant-..." di beberapa Python versions
```

Mitigasi: jangan simpan key sebagai instance attribute yang bisa muncul di traceback. Gunakan closure atau langsung pass ke client constructor tanpa intermediate storage:

```python
# LEBIH AMAN: key tidak pernah jadi attribute yang bisa muncul di traceback
def get_client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    # key di-pass langsung, tidak di-store sebagai self.api_key
```

**Kesimpulan Q2:** Cache tidak menyimpan key secara langsung — desain ini sudah benar. Risk ada di: (1) exception handler yang log error message dari provider (bisa mengandung key fragment), (2) subprocess inheritance jika ada subprocess di future, (3) traceback exposure jika key disimpan sebagai instance variable. Semua ini preventable dengan coding discipline yang harus di-document sekarang.

---

### Q3: User Codebase Di-scan — Data Apa yang Tidak Sengaja Di-expose ke Server?

**Jawaban singkat: Ada satu finding Critical yang tersembunyi di schema — `constants[].value` menyimpan nilai literal hardcoded credentials.**

#### A. Apa yang Masuk ke Graph JSON (dari schema di handoff.md)

| Field | Isi | Risk |
|-------|-----|------|
| `id` | relative path file | ✅ aman |
| `real_path` | **absolute path** (e.g. `/home/user/myproject/...`) | ⚠️ expose home dir structure |
| `functions[].name` | nama fungsi | ✅ aman |
| `functions[].params` | nama + type annotation | ✅ aman |
| `functions[].risks[].detail` | string seperti "2 callers tidak handle None return" | ✅ aman |
| `constants[].name` | nama konstanta | ✅ aman |
| `constants[].value` | **nilai literal sebagai string** | 🔴 CRITICAL LEAK |
| `imports[].from` | module name | ✅ aman |
| `file_modified_at` | timestamp | ✅ aman |

#### B. `constants[].value` — The Hidden Credential Leak

Dari schema yang didokumentasikan:

```json
"constants": [
  {
    "name": "MAX_RETRY",
    "value": "3",        ← aman
    "line": 8
  }
]
```

Ini terlihat innocent. Tapi konstanta Python di level module juga mencakup:

```python
# config.py — sangat umum di codebase vibe coder
DATABASE_URL = "postgres://admin:secretpassword@db.internal:5432/prod"
SECRET_KEY = "django-insecure-abc123xyz..."
ANTHROPIC_API_KEY = "sk-ant-..."
AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
WEBHOOK_SECRET = "whsec_..."
```

Semua nilai ini akan masuk ke `graph.json` verbatim sebagai `"value": "postgres://admin:..."`. Dan graph JSON ini:

1. Bisa di-akses via `GET /api/graph` oleh **siapapun yang bisa hit localhost:8765**
2. Di-render di browser frontend (visible di DevTools Network tab)
3. Bisa di-cache oleh browser

**Ini adalah credential leak yang by design, bukan bug.**

Solusinya bukan "jangan baca constants" — constants berguna untuk visualisasi. Solusinya adalah **sanitasi nilai sebelum masuk ke graph JSON**:

```python
import re

# Pola yang perlu di-redact sebelum masuk graph JSON
SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|auth[_-]?key)\s*=\s*['\"]([^'\"]{8,})['\"]"),
    re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}"),      # Anthropic key
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),               # OpenAI key
    re.compile(r"(?i)(postgres|mysql|mongodb)://[^@]+@"),  # DB connection string
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9\-_.]{20,}"),
]

def sanitize_constant_value(name: str, value: str) -> str:
    name_lower = name.lower()
    # Redact berdasarkan nama
    if any(kw in name_lower for kw in ["secret", "password", "token", "key", "auth", "credential"]):
        return "[REDACTED]"
    # Redact berdasarkan pola nilai
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            return "[REDACTED]"
    return value
```

#### C. `real_path` — Absolute Path Exposure

Graph JSON menyimpan:

```json
"real_path": "/home/alice/work/startup-project/backend/services/user_service.py"
```

Ini mengekspose: username sistem (`alice`), struktur folder project, dan nama project. Di context localhost-only tool yang di-run sendiri, ini kurang kritikal — user sudah tau path mereka sendiri. Tapi jika graph JSON pernah di-share (screenshot, copy-paste, bug report), ini bocor.

Mitigasi ringan: simpan `real_path` tapi jangan tampilkan di default frontend view. Atau relativize terhadap project root:

```python
# Ganti absolute path dengan relative ke scan root
relative_real_path = str(Path(real_path).relative_to(scan_root))
```

#### D. Apa yang TIDAK Masuk ke Graph JSON (dan Harusnya Tetap Begitu)

Berdasarkan schema, hal-hal berikut **tidak ada** di graph JSON dan harus tetap tidak ada:
- Source code konten file (kecuali via AI call)
- Nilai parameter fungsi saat runtime
- Isi string literals di dalam function body
- `.env` file content (karena `.env` bukan Python file, tidak di-scan)

Catatan penting: `.env` file aman karena bukan `.py` file. Tapi `settings.py`, `config.py`, atau `constants.py` yang berisi nilai hardcoded **akan di-scan**.

**Kesimpulan Q3:** Risk utama ada di `constants[].value` yang menyimpan literal string termasuk credentials hardcoded. Ini perlu secret-pattern detection sebelum nilai masuk ke graph JSON. `real_path` adalah minor leak yang acceptable di localhost context tapi perlu dokumentasi.

---

## Bagian II — Security Findings (Updated dengan Threat Model yang Benar)

---

### [CRITICAL] C-01: `constants[].value` Expose Hardcoded Credentials ke Graph JSON

**Location:** `handoff.md` → Section 7 (Data Contract / Graph JSON Schema)

**Masalah:** Nilai literal konstanta module-level disimpan verbatim di graph JSON dan dapat diakses via `GET /api/graph`. Credentials hardcoded di `config.py` atau `settings.py` akan bocor ke siapapun yang bisa hit endpoint tersebut.

**Severity: CRITICAL**

**Mitigasi:** Implementasi `sanitize_constant_value()` dengan pattern matching berbasis nama variabel dan pola nilai (lihat Q3 section B di atas). Redact ke `"[REDACTED]"` sebelum konstanta masuk ke graph builder output.

---

### [CRITICAL] C-02: Source Code Dikirim ke Third-Party AI API Tanpa Secret Scrubbing

**Location:** `handoff.md` → Section 10 (AI Layer Specification)

**Masalah:**

```
AI prompt: "Full file content: [entire file content]"
```

Full file dikirim ke Anthropic/OpenAI. Jika file tersebut mengandung credentials hardcoded, credentials tersebut ter-exfiltrate ke cloud provider. Ini adalah satu-satunya titik di graps di mana data keluar dari machine user.

**Severity: CRITICAL** (meskipun tool run di localhost, ini adalah data yang genuinely keluar ke internet)

**Mitigasi:**

1. Secret scrubbing sebelum payload dikirim ke AI provider
2. Explicit disclosure: pertama kali user klik "Generate AI Insight", tampilkan modal: *"File [nama] akan dikirim ke [Anthropic/OpenAI] untuk dianalisis. File berisi X baris. Lanjutkan?"*
3. Kirim hanya function context (lines start-end + imports), bukan full file
4. Implement `--enable-ai` flag explicit, bukan auto-detect dari env var

---

### [HIGH] H-01: Uvicorn Default Bind ke 0.0.0.0 — Local Network Exposure

**Location:** `handoff.md` → Section 4, tidak ada spesifikasi `host` parameter

**Masalah:** Default Uvicorn bind ke `0.0.0.0`. Di shared network (kantor, cafe, kampus), device lain bisa akses `http://192.168.x.x:8765` dan lihat seluruh graph JSON codebase user.

**Konteks:** Untuk laptop personal di home network, risk rendah. Untuk developer yang sering kerja di luar atau di shared machine — ini real exposure.

**Severity: HIGH**

**Mitigasi:** Hardcode satu baris ini — non-negotiable:

```python
uvicorn.run(app, host="127.0.0.1", port=port)
```

---

### [HIGH] H-02: Tidak Ada CORS + Origin Validation — Browser-based CSRF

**Location:** `handoff.md` → Section 4 (Architecture)

**Masalah:** Tidak ada CORS config yang didokumentasikan. Malicious website yang terbuka di browser user bisa trigger POST ke `/api/ai/summary` dan menghabiskan API quota/billing user.

**Severity: HIGH** (karena langsung hit API key user = financial impact)

**Mitigasi:** Implement CORS middleware + server-side Origin check + Host header validation (implementasi lengkap di Q1 section C dan D di atas).

---

### [HIGH] H-03: Cache File Plaintext + Rawan Ter-commit ke Git

**Location:** `handoff.md` → Section 10 (Cache Structure)

**Masalah:** `.graps/cache.json` disimpan di dalam project directory tanpa file permission restriction. AI summaries berisi inferensi tentang business logic, database structure, dan hidden assumptions — ini adalah sensitive IP. Jika developer lupa add `.graps/` ke `.gitignore`, cache ter-commit ke GitHub.

**Severity: HIGH** (AI summaries mengandung structural insight tentang codebase yang mungkin proprietary)

**Mitigasi:**

```python
import os, stat

def write_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # chmod 600

def startup_check(project_root: Path) -> None:
    gitignore = project_root / ".gitignore"
    if gitignore.exists() and ".graps" not in gitignore.read_text():
        print("⚠️  WARNING: .graps/ tidak ditemukan di .gitignore")
        print("   Cache berisi AI summaries bisa ter-commit ke Git.")
        print("   Tambahkan: echo '.graps/' >> .gitignore")
```

---

### [MEDIUM] M-01: API Key Leak via Exception Handler dan Traceback

**Location:** `handoff.md` → Section 10 (AI Layer), `graps/ai/provider.py`

**Masalah:** Beberapa indirect paths di mana API key bisa ter-expose ke log atau terminal output (detail di Q2 section A, B, C):
- Exception message dari Anthropic/OpenAI SDK bisa berisi key fragment
- Instance attribute `self.api_key` bisa muncul di Python traceback
- Subprocess spawn di future bisa inherit environment variable dengan key

**Severity: MEDIUM**

**Mitigasi:**

```python
# 1. Jangan simpan key sebagai instance attribute
class AnthropicProvider(AIProvider):
    def generate_summary(self, content: str, context: dict) -> dict:
        # Buat client inline, jangan di __init__
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        ...

# 2. Sanitize exception sebelum log
except anthropic.APIError as e:
    # Jangan log e langsung — bisa berisi key info
    logger.error(f"Anthropic API error: {type(e).__name__} (status {e.status_code})")

# 3. Custom key format validator — deteksi typo sebelum request gagal
def validate_key_format(key: str, provider: str) -> bool:
    if provider == "anthropic":
        return key.startswith("sk-ant-") and len(key) > 20
    if provider == "openai":
        return key.startswith("sk-") and len(key) > 20
    return False
```

---

### [MEDIUM] M-02: AST Parser Rentan DoS via Deeply Nested Code

**Location:** `architect-review.md` → Section 1

**Masalah:** `ast.parse()` tidak ada timeout bawaan. File `.py` yang berisi deeply nested expression (jutaan level) bisa hang parser selama menit bahkan jam, memblok seluruh scan. Relevan jika user scan directory yang mengandung generated code atau third-party library yang tidak dipercaya.

**Severity: MEDIUM**

**Mitigasi:**

```python
import ast, signal
from contextlib import contextmanager

@contextmanager
def parse_timeout(seconds: int = 5):
    def _handler(signum, frame):
        raise TimeoutError()
    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

def safe_parse(source: str, filename: str) -> ast.AST | None:
    if len(source.encode()) > 1_000_000:  # 1MB guard
        logger.warning(f"Skip {filename}: file too large")
        return None
    try:
        with parse_timeout(5):
            return ast.parse(source, filename=filename)
    except (TimeoutError, SyntaxError, MemoryError) as e:
        logger.warning(f"Skip {filename}: parse failed ({type(e).__name__})")
        return None
# Note: signal.SIGALRM Unix-only. Windows: gunakan multiprocessing dengan timeout.
```

---

### [MEDIUM] M-03: `real_path` di Graph JSON Expose Absolute Path User

**Location:** `handoff.md` → Section 7 (Graph JSON Schema)

**Masalah:** `real_path` menyimpan absolute path seperti `/home/alice/work/startup/backend/services/user.py`. Jika graph JSON di-share (screenshot DevTools, copy-paste untuk bug report, atau export feature di future), ini expose username dan directory structure.

Di context localhost-only personal tool: **low operational risk**, tapi perlu didocumentasikan sebagai known information leakage.

**Severity: MEDIUM** (bukan untuk exploit, tapi privacy concern yang perlu disadari)

**Mitigasi:** Relativize `real_path` terhadap scan root sebelum masuk ke graph JSON. Simpan absolute path hanya di memory jika diperlukan untuk file opening (klik "open in editor").

---

### [LOW] L-01: CI/CD Pipeline Tanpa Branch/Tag Protection

**Location:** `python-packaging-reviewer.md` → GitHub Actions Publish Workflow

**Masalah:** Workflow publish ke PyPI trigger dari semua tag `v*` tanpa protection rule. Siapapun dengan write access bisa push malicious tag dan publish ke PyPI. Karena ini open source tool yang di-install via `pip install graps`, supply chain compromise di sini bisa affect semua user.

**Severity: LOW** (karena masih dalam planning, belum ada contributors lain) → **Naik ke HIGH saat user base berkembang**

**Mitigasi:**

```yaml
jobs:
  publish:
    environment: pypi          # require manual approval di GitHub Environments
    permissions:
      id-token: write
      contents: read           # principle of least privilege
    steps:
      # Pin ke commit SHA, bukan floating tag
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
      - uses: pypa/gh-action-pypi-publish@76f52bc884a99b5b2b9ffdfe61fc1d457e7b580f
```

---

## Risk Matrix Summary

| ID | Severity | Finding | Komponen | Localhost Context |
|----|----------|---------|----------|-------------------|
| C-01 | **CRITICAL** | `constants[].value` expose hardcoded credentials ke graph JSON | Scanner / Data Contract | Tetap Critical — `GET /api/graph` accessible dari browser tab lain |
| C-02 | **CRITICAL** | Full source code dikirim ke AI API tanpa secret scrubbing | AI Layer | Tetap Critical — satu-satunya titik data keluar dari machine |
| H-01 | **HIGH** | Uvicorn bind ke 0.0.0.0 → local network exposure | FastAPI Server | High di shared network, Low di home network — tapi fix trivial |
| H-02 | **HIGH** | Tidak ada CORS + Origin validation → browser CSRF | FastAPI Server | Tetap High — malicious website bisa trigger API call |
| H-03 | **HIGH** | Cache plaintext + rawan ter-commit ke Git | Cache | Tetap High — AI summaries berisi sensitive IP |
| M-01 | **MEDIUM** | API key leak via exception/traceback | AI Layer | Medium — butuh bad luck / debug mode aktif |
| M-02 | **MEDIUM** | AST parser rentan DoS via deeply nested code | Scanner | Medium — hanya jika scan untrusted code |
| M-03 | **MEDIUM** | `real_path` expose absolute path user di graph JSON | Data Contract | Medium — privacy concern, bukan exploit |
| L-01 | **LOW** | CI/CD tanpa branch/tag protection | DevOps | Low sekarang, High jika ada contributor |

---

## Finding yang Dihapus / Di-downgrade dari Review Sebelumnya

Beberapa finding dari draft pertama tidak relevan untuk localhost per-user tool:

**"Arbitrary File Read via Unvalidated Scan Path" (C-01 lama) → Di-downgrade ke konteks**

Dalam threat model yang benar, user yang menjalankan `graps /etc/` adalah **user itu sendiri** yang memiliki akses ke `/etc/`. Tool tidak memberikan privilege escalation — user sudah punya akses ke file tersebut. Ini bukan vulnerability, ini expected behavior (user bisa scan directory manapun yang mereka punya akses). Yang perlu di-guard adalah output-nya (lihat C-01 baru tentang credentials di constants[]).

Satu-satunya edge case yang masih relevan: **symlink traversal di codebase yang di-clone dari internet** (malicious repo yang berisi symlink ke `/etc/hosts`). Ini tetap worth di-guard dengan symlink depth limit, tapi bukan Critical.

**"CI/CD Pipeline" — Turun dari konteks keseluruhan**

Untuk tool yang masih solo project, ini Low. Hanya perlu di-address sebelum ada contributor kedua.

---

## Prioritas Implementasi

**Sebelum baris kode pertama ditulis:**
- H-01: Hardcode `host="127.0.0.1"` di Uvicorn run — satu baris, zero cost

**Di Phase 1 (Core Visual) — saat scanner dan graph JSON builder dibuat:**
- C-01: Implement `sanitize_constant_value()` di graph builder — sebelum `constants[]` populated
- M-03: Relativize `real_path` terhadap scan root

**Di Phase 1 (Server) — saat FastAPI app dibuat:**
- H-02: Implement CORS middleware + Origin check + Host validation

**Di Phase 3 (AI Layer) — blocking sebelum AI feature shipped:**
- C-02: Secret scrubbing + explicit user consent modal
- M-01: Safe exception handling, tidak store key sebagai instance attribute

**Sebelum PyPI publish pertama:**
- H-03: Cache file permissions + .gitignore check pada startup
- L-01: GitHub Environment protection + pinned action SHAs

---

## Kesimpulan

Dengan threat model yang benar (localhost per-user tool), beberapa risk turun — tidak ada remote attacker yang bisa langsung hit server. Tapi dua risk tetap Critical dan tidak berubah karena localhost context:

**C-01** — Credentials hardcoded di constants user's codebase akan masuk ke graph JSON verbatim. Ini adalah credential leak by design yang tersembunyi di schema documentation.

**C-02** — AI layer adalah satu-satunya titik di mana data genuinely keluar dari machine user ke internet. Tanpa secret scrubbing, ini adalah exfiltration path untuk credentials hardcoded.

Dan satu risk baru yang muncul spesifik karena tool ini dijalankan di localhost dengan browser di machine yang sama: **H-02** (CORS/CSRF) adalah attack surface nyata yang sering diabaikan di "localhost tools" tapi telah dieksploitasi di tools populer lain (ngrok, webpack dev server, dsb).

**Rekomendasi akhir:** Tambahkan `SECURITY.md` di repo yang mendokumentasikan threat model ini secara eksplisit, termasuk apa yang dikirim ke AI provider dan apa yang tidak pernah keluar dari machine user. Ini penting untuk open source tool karena user perlu tahu apa yang mereka jalankan.

---

*Security Review v2 — Updated: 2026-06-27*  
*Changes: Reframed threat model untuk localhost per-user context, jawab 3 pertanyaan spesifik, hapus/downgrade findings yang tidak relevan, tambah C-01 (constants value leak) dan M-03 (real_path exposure)*
