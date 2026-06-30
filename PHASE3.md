{se 3 — AI Layer Hardening & BaseParser Foundation

> Reference: BLUEPRINT.md — jangan diubah, baca section yang direference per task.
> Status awal: sebagian besar AI layer SUDAH diimplementasi di siklus Phase 1-2.
> File ini bukan "build dari nol" — ini gap-closing + upgrade.

---

## 0. Status Real Sebelum Mulai (Verified 2026-06-28)

Sudah ada dan **tests pass** — jangan tulis ulang:

```
✅ graps/ai/provider.py     — AnthropicProvider, OpenAIProvider, pakai SDK resmi
✅ graps/ai/cache.py        — read/write cache, sudah pakai pola yang benar
✅ POST /api/ai/summary     — endpoint di graps/server/app.py
✅ Tombol [Generate AI Insight] — sudah ada di graps/frontend/panel.js
✅ 9 test AI-related        — tests/test_api.py, semua pass
```

Belum ada — **ini scope Phase 3**:

```
❌ Consent notice sebelum AI pertama kali dipanggil
❌ scrub_secrets() masih regex manual 3 pattern — upgrade ke detect-secrets
❌ Verifikasi chmod 600 untuk .graps/cache.json benar-benar diterapkan
❌ Verifikasi .gitignore check untuk .graps/ saat startup
❌ SECURITY.md (file user-facing, beda dari security/codemap-security-review.md)
❌ BaseParser Protocol interface (BLUEPRINT §4) — prasyarat Phase 4
```

---

## 1. Prinsip Wajib (berlaku semua task di file ini)

Lihat rules yang sudah ditetapkan manual saat building:

1. Kode simple tapi works — jangan over-engineer.
2. Minimalisir bug — defensive terhadap input aneh/kosong/corrupt.
3. Gampang di-refactor — pertahankan separation of concern yang sudah ada (provider.py tidak tahu FastAPI, cache.py tidak tahu AI).
4. Riset dulu sebelum tulis manual — kalau ada library yang sudah solve, pakai dan jelaskan trade-off ke user sebelum eksekusi.
5. Jangan build dari nol kalau ada yang sudah dibangun — selama license-nya aman dipakai komersial.

**Lisensi check untuk task di bawah:** `detect-secrets` (Yelp) — Apache 2.0. Aman dipakai untuk produk komersial, termasuk closed-source kalau nanti ada tier berbayar.

---

## 2. Task — Urutan Dependency

### Task 1 — Upgrade `scrub_secrets()` pakai detect-secrets plugins

**File:** `graps/ai/provider.py`
**Baca:** BLUEPRINT.md §10 (Secret scrubbing section)
**Input:** `graps/ai/provider.py` yang sudah ada (jangan dihapus total, upgrade saja)

**Keputusan trade-off (sudah final, jangan re-discuss):**

```
Regex manual lama → coverage sempit (3 pattern keyword), false negative tinggi
detect-secrets    → 27 detector built-in, tapi didesain untuk CI/baseline scanning,
                     bukan runtime redaction — perlu integrasi manual

                     Solusi: pakai PLUGIN class dari detect-secrets sebagai detector,
                     tapi logic redaction tetap kita yang tulis (bukan pakai
                     detect-secrets CLI/baseline workflow).

                     Regex manual yang ada SEKARANG tetap dipertahankan sebagai
                     layer kedua (defense in depth), bukan dihapus.
                     ```

                     **Implementasi:**

                     ```python
# graps/ai/provider.py — tambahan, bukan replace total

                     from detect_secrets.plugins.aws import AWSKeyDetector
                     from detect_secrets.plugins.github_token import GitHubTokenDetector
                     from detect_secrets.plugins.keyword import KeywordDetector
                     from detect_secrets.plugins.high_entropy_strings import (
                         Base64HighEntropyString,
                             HexHighEntropyString,
                             )
                     from detect_secrets.plugins.stripe import StripeDetector
                     from detect_secrets.plugins.jwt import JwtTokenDetector

                     _DETECTORS = [
                         AWSKeyDetector(),
                             GitHubTokenDetector(),
                                 StripeDetector(),
                                     JwtTokenDetector(),
                                         KeywordDetector(),
                                             Base64HighEntropyString(limit=4.5),
                                                 HexHighEntropyString(limit=3.0),
                                                 ]

                                                 def scrub_secrets(source: str) -> str:
                                                     """Dua layer: detect-secrets plugins dulu, lalu regex manual lama
                                                         sebagai fallback untuk pattern yang plugin mungkin lewatkan.
                                                             """
                                                                 lines = source.split("\n")
                                                                     redacted_lines = []

                                                                         for line in lines:
                                                                                     redacted = line
                                                                                             for detector in _DETECTORS:
                                                                                                             try:
                                                                                                                             secrets = detector.analyze_line(
                                                                                                                                                 filename="<ai_summary_input>",
                                                                                                                                                                     line=line,
                                                                                                                                                                                         line_number=0,
                                                                                                                                                                                                         )
                                                                                                                                         except Exception:
                                                                                                                                                         # ponytail: detector gagal parse satu line aneh —
                                                                                                                                                                         # jangan crash seluruh scrub, skip detector ini untuk line ini
                                                                                                                                                                                         continue
                                                                                                                                                                                                     for secret in secrets or []:
                                                                                                                                                                                                                         if secret.secret_value:
                                                                                                                                                                                                                                                 redacted = redacted.replace(secret.secret_value, "[REDACTED]")
                                                                                                                                                                                                                                                         redacted_lines.append(redacted)

                                                                                                                                                                                                                                                             scrubbed = "\n".join(redacted_lines)

                                                                                                                                                                                                                                                                 # Layer 2 — regex manual lama, tetap jalan sebagai fallback
                                                                                                                                                                                                                                                                     for pattern in _SENSITIVE_PATTERNS:
                                                                                                                                                                                                                                                                                 scrubbed = pattern.sub(
                                                                                                                                                                                                                                                                                             lambda m: m.group().split("=")[0] + '= "[REDACTED]"', scrubbed
                                                                                                                                                                                                                                                                                                     )
                                                                                                                                                                                                                                                                                     return scrubbed
                                                                                                                                                                                                                                                                                     ```

                                                                                                                                                                                                                                                                                     **pyproject.toml — tambah dependency:**

                                                                                                                                                                                                                                                                                     ```toml
                                                                                                                                                                                                                                                                                     [project.optional-dependencies]
                                                                                                                                                                                                                                                                                     ai = ["anthropic>=0.28.0", "openai>=1.30.0", "detect-secrets>=1.5.0"]
                                                                                                                                                                                                                                                                                     ```

                                                                                                                                                                                                                                                                                     **Test yang wajib ditambah** (`tests/test_provider.py` atau extend yang ada):

                                                                                                                                                                                                                                                                                     ```python
                                                                                                                                                                                                                                                                                     def test_scrub_secrets__detects_aws_key():
                                                                                                                                                                                                                                                                                         source = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
                                                                                                                                                                                                                                                                                             result = scrub_secrets(source)
                                                                                                                                                                                                                                                                                                 assert "AKIAIOSFODNN7EXAMPLE" not in result
                                                                                                                                                                                                                                                                                                     assert "[REDACTED]" in result

                                                                                                                                                                                                                                                                                                     def test_scrub_secrets__detects_github_token():
                                                                                                                                                                                                                                                                                                         source = 'token = "ghp_1234567890abcdef1234567890abcdef1234"'
                                                                                                                                                                                                                                                                                                             result = scrub_secrets(source)
                                                                                                                                                                                                                                                                                                                 assert "ghp_" not in result

                                                                                                                                                                                                                                                                                                                 def test_scrub_secrets__keeps_normal_code_intact():
                                                                                                                                                                                                                                                                                                                     source = "def get_user(user_id: int) -> User:\n    return db.query(user_id)"
                                                                                                                                                                                                                                                                                                                         result = scrub_secrets(source)
                                                                                                                                                                                                                                                                                                                             assert result == source  # tidak ada false positive di kode normal

                                                                                                                                                                                                                                                                                                                             def test_scrub_secrets__regex_fallback_still_works():
                                                                                                                                                                                                                                                                                                                                 # Pattern lama (password = "...") harus tetap kena meski
                                                                                                                                                                                                                                                                                                                                     # bukan format yang dikenali detect-secrets plugin manapun
                                                                                                                                                                                                                                                                                                                                         source = 'password = "hardcoded123"'
                                                                                                                                                                                                                                                                                                                                             result = scrub_secrets(source)
                                                                                                                                                                                                                                                                                                                                                 assert "hardcoded123" not in result
                                                                                                                                                                                                                                                                                                                                                 ```

                                                                                                                                                                                                                                                                                                                                                 **Selesai ketika:** semua test di atas pass, 60 test lama tidak ada yang regresi.

                                                                                                                                                                                                                                                                                                                                                 ---

### Task 2 — Consent Notice

**File:** `graps/frontend/panel.js` + kemungkinan state baru di `graps/frontend/filter.js` (state global) atau localStorage-equivalent (browser, bukan node — vanilla JS, tidak boleh localStorage per BLUEPRINT artifact rules, tapi ini bukan artifact, ini real app — cek dulu apakah project ini boleh localStorage karena bukan di environment artifact Claude)

**Baca:** BLUEPRINT.md §10 — "User harus lihat consent notice pertama kali AI dipanggil"

**Perilaku yang diharapkan:**

```
User klik [Generate AI Insight] pertama kali dalam sesi ini
  →
  Modal/toast muncul:
    "File content akan dikirim ke Anthropic/OpenAI.
       Pastikan tidak ada credentials hardcoded.
          [Lanjutkan]  [Batal]"
            →
            User klik Lanjutkan → request jalan, consent di-remember
              untuk sisa sesi (in-memory, tidak perlu persist ke disk)
              User klik Batal → request dibatalkan, tombol balik ke idle state
              ```

              **Implementasi sederhana — in-memory flag, bukan localStorage:**

              ```javascript
              // graps/frontend/panel.js — tambahan
              let _aiConsentGiven = false;

              function requestAIInsight(functionId) {
                    if (!_aiConsentGiven) {
                            showConsentModal(() => {
                                      _aiConsentGiven = true;
                                            callAIInsightEndpoint(functionId);
                                                });
                                return;
                                  }
                                    callAIInsightEndpoint(functionId);
              }
              ```

              Consent di-reset setiap kali server di-restart (`codemap .` dijalankan ulang) — sesuai sifat tool yang per-sesi, bukan aplikasi yang persist data antar run.

              **Selesai ketika:** modal muncul sekali per sesi server, tidak muncul lagi untuk function lain dalam sesi yang sama.

              ---

### Task 3 — Verifikasi Cache File Permission & Gitignore Check

**File:** `graps/ai/cache.py`, `graps/cli.py`
**Baca:** BLUEPRINT.md §10, §11 (Cache file permissions)

**Yang harus diverifikasi (bukan ditulis dari nol, cache.py sudah ada):**

```python
# graps/ai/cache.py — pastikan ada baris ini saat create cache pertama kali
def _ensure_cache_file(cache_path: Path) -> None:
    if not cache_path.exists():
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                        cache_path.touch(mode=0o600)
                            else:
                                        # kalau sudah ada tapi permission salah (misal dari OS lain), perbaiki
                                                os.chmod(cache_path, 0o600)
                                                ```

                                                **Gitignore check di startup** — tambahan baru di `cli.py`:

                                                ```python
                                                def _warn_if_cache_not_ignored(root: Path) -> None:
                                                    gitignore = root / ".gitignore"
                                                        if gitignore.exists():
                                                                    content = gitignore.read_text()
                                                                            if ".graps" not in content and ".graps/" not in content:
                                                                                            typer.echo(
                                                                                                            "  ⚠ .graps/ belum ada di .gitignore — "
                                                                                                                            "cache bisa berisi ringkasan AI dari source code kamu. "
                                                                                                                                            "Tambahkan '.graps/' ke .gitignore?"
                                                                                                                                                        )
                                                                                            ```

                                                                                            Bukan blocking — hanya warning di terminal, jangan stop eksekusi.

                                                                                            **Test:**

                                                                                            ```python
                                                                                            def test_cache_file_created_with_600_permission(tmp_path):
                                                                                                cache_path = tmp_path / ".graps" / "cache.json"
                                                                                                    write_cache(cache_path, "key", {"foo": "bar"})
                                                                                                        mode = oct(cache_path.stat().st_mode)[-3:]
                                                                                                            assert mode == "600"
                                                                                                            ```

                                                                                                            **Selesai ketika:** test permission pass, warning muncul di terminal kalau `.gitignore` ada tapi tidak exclude `.graps/`.

                                                                                                            ---

### Task 4 — SECURITY.md (file user-facing, root repo)

**Baca:** `security/codemap-security-review.md` (review internal, sudah ada) — distill jadi versi pendek untuk user.
**Bukan technical deep-dive** — ini yang dibaca orang sebelum install/pakai tool.

**Struktur:**

```markdown
# Security Policy

## Threat Model

graps adalah tool yang berjalan 100% di komputer kamu (localhost).
Tidak ada data yang dikirim kemana pun KECUALI:

- Kamu generate AI Insight secara eksplisit (opt-in per klik)
- Saat itu, source code function yang kamu pilih dikirim ke
  provider AI (Anthropic atau OpenAI) sesuai API key yang kamu set

## Apa yang TIDAK pernah dikirim

- Seluruh codebase kamu — hanya function yang kamu klik
- File di luar direktori yang kamu scan
- API key kamu sendiri (dipakai untuk auth ke provider, tidak
  pernah dikirim ke pihak lain)

## Secret Scrubbing

Sebelum source code dikirim ke AI provider, graps melakukan scrub
otomatis terhadap pola yang terlihat seperti credential (API key,
password, token). Ini best-effort, BUKAN jaminan — review kode
kamu sendiri sebelum generate AI insight pada file yang berisi
secret.

## Cara Report Vulnerability

[isi sesuai preferensi Maou — email, atau GitHub Security Advisory]

## Known Limitations

- Server localhost tidak ada authentication layer — siapapun
  yang punya akses ke mesin yang sama bisa akses localhost:8765
    selama server berjalan
    - Cache AI summary (.graps/cache.json) disimpan plaintext di disk
    ```

    **Selesai ketika:** file di-commit ke root repo, bahasa jelas untuk non-security-expert.

    ---

### Task 5 — BaseParser Protocol Interface

**File baru:** `graps/scanner/__init__.py`
**Baca:** BLUEPRINT.md §4 (BaseParser Interface section — sudah lengkap di sana, tinggal implementasi)

Ini **prasyarat wajib sebelum Phase 4 dimulai**. Tidak terkait AI layer, tapi dikerjakan di Phase 3 supaya Phase 4 tinggal jalan tanpa refactor.

**Implementasi — copy persis dari BLUEPRINT.md §4**, lalu:

1. Refactor `graps/scanner/ast_parser.py` supaya class `ASTParser` implement `BaseParser` Protocol (tidak perlu inherit eksplisit karena `Protocol`, cukup match method signature)
2. Refactor `graps/scanner/graph_builder.py` — pastikan hanya import `ParsedFile` dari `graps.scanner`, BUKAN import `ASTParser` secara langsung
3. Jalankan ulang full test suite — tidak boleh ada regresi dari refactor ini

**Selesai ketika:** `python -m pytest tests/ -v` tetap 60+ passed (atau lebih, karena ada test baru dari Task 1-3), dan `graph_builder.py` tidak punya import `from graps.scanner.ast_parser import ASTParser` secara langsung.

---

## 3. Checklist Ringkas

```
[ ] Task 1 — scrub_secrets() upgrade pakai detect-secrets plugins
[ ] Task 2 — Consent notice di frontend
[ ] Task 3 — Cache permission 600 + gitignore warning
[ ] Task 4 — SECURITY.md
[ ] Task 5 — BaseParser Protocol interface + refactor ast_parser & graph_builder
[ ] Full test suite pass, zero regresi dari 60 test yang sudah ada
```

---

## 4. Yang TIDAK Termasuk Phase 3 (eksplisit)

```
✗ Tree-sitter implementation — itu Phase 4, jangan disentuh sekarang
✗ Multi-language risk_analyzer — Phase 4
✗ Rename/rebrand lanjutan — sudah selesai di siklus sebelumnya
✗ Subagent tambahan (prompt engineering reviewer, dll) — tidak dipakai,
  coding + reviewer existing sudah cukup untuk scope Phase 3 ini
  ```

  ---

  *PHASE3.md — reference BLUEPRINT.md, tidak menduplikasi isinya.*
  *Dibuat: 2026-06-28*

  "$schema": "https://opencode.ai/config.json",

  "provider": {
    "myprovider": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "unimodel",

      "options": {
        "baseURL": "https://unimodel.ai/v1"
      },

      "models": {
        "glm-5.2": {
          "name": "glm-5.2"
        }
      }
    }
  },

  "model": "unimodel/glm-5.2"
}

