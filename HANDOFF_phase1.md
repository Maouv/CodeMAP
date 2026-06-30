# HANDOFF — graps Phase 1

> Sesi: 2026-06-28. Scope yang dikerjakan: **File 1–9 (scanner core)** dari `Task_plan.md`.
> Status: **SELESAI & terverifikasi.** 30 test passed (`venv/bin/pytest tests/ -q`).

---

## 1. Rangkuman sesi

Scanner core graps selesai — pipeline statis dari file `.py` → graph dict JSON.

File yang dihasilkan (semua dengan skill `ponytail`):

| # | File | Isi |
|---|------|-----|
| 1 | `graps/scanner/sanitize.py` | `sanitize_constant_value(name, value)` — redaksi kredensial. Doctest pass. |
| 2 | `graps/scanner/ast_parser.py` | `safe_parse()` + `_ScannerVisitor` + `_decorator_name()`. Body skeleton diisi. |
| 3 | `tests/fixtures/*.py` | 16 fixture + folder `relative_imports/`. Tiap file trigger 1 edge case. |
| 4 | `tests/test_ast_parser.py` | 17 test. |
| 5 | `graps/scanner/resolver.py` | `resolve_import()` + `resolve_safe()`. |
| 6 | `graps/scanner/risk_analyzer.py` | `analyze_risks()` — Phase 1 hanya `star_import`. |
| 7 | `graps/scanner/graph_builder.py` | `build_graph()` — rakit semua jadi dict §7. |
| 8 | `tests/test_resolver.py` | 9 test. |
| 9 | `tests/test_risk_analyzer.py` | 4 test. |

Tambahan di luar daftar (perlu agar package importable): `graps/__init__.py` (`__version__ = "0.1.0"`, ini juga File 14 di plan — sudah jadi), `graps/scanner/__init__.py`, `tests/__init__.py`.

---

## 2. Deviasi dari plan (PENTING dibaca sebelum lanjut)

Hal-hal yang TIDAK seperti tertulis di `Task_plan.md` / BLUEPRINT. Bukan pelanggaran arsitektur — penyesuaian terhadap kondisi kode nyata. Semua keputusan diverifikasi lewat test.

1. **sanitize.py sudah ada sebelum sesi ini.** Lengkap + doctest, tapi di lokasi salah (`security/sanitize_constant_value.py`). Tindakan: di-`cp` ke `graps/scanner/sanitize.py`, file lama dihapus. Tidak ditulis ulang oleh subagent.
   - 1 doctest salah (contoh `sk-ant-abc123xyz...` cuma ~9 char, regex butuh `{20,}`) → contoh diperbaiki jadi token panjang. Implementasi TIDAK diubah.

2. **`safe_parse()` SELALU return `ParseResult`, tidak pernah `None`.** Plan menulis `-> ParseResult | None`, tapi skeleton yang sudah di-commit return `ParseResult` (warnings dipopulate). Diikuti skeleton karena lebih konsisten dengan dataclass. **Konsumen hilir (graph_builder, CLI nanti) harus cek `result.warnings`, bukan `is None`.**

3. **Bug `.lstrip(".")` di parser (ditemukan saat verifikasi cross-file).** `visit_ImportFrom` membuang leading dot penanda relative import → resolver tak bisa deteksi relative. Diperbaiki: leading dot dipertahankan, `sep` dihitung agar tak double-dot pada `from . import x`. Target relative sekarang berbentuk `.sub.helper`, `..pkg.mod`, dst.

4. **Resolver butuh fallback drop-segmen-terakhir.** `from .sub import helper` → target `.sub.helper`, di mana `helper` adalah nama yang diimpor, bukan submodul. `_try_module()` mencoba path penuh lalu drop segmen terakhir → resolve ke `sub.py`. Berlaku untuk relative & absolute import.

5. **Gap schema §7 vs data parser (deviasi terbesar — lihat Bagian 4).** Schema minta `constants[]`, `params`, `returns`, `classes`, `callers/callees`, `criticality`. Parser Phase 1 TIDAK mengekstrak itu. `graph_builder` mengisi field tsb dengan default Phase 1 (`[]`/`null`/`false`) + ponytail comment. **Jalur sanitize C-01 tetap di-wire** lewat `_sanitized_constants()` (input kosong sekarang, siap saat parser mengekstrak constants).

---

## 3. Flow & metodologi sesi ini (pola yang dipakai, lanjutkan di sesi berikut)

Tujuan: hindari context-loss/halusinasi pada implementasi 19 file. Caranya **bukan** satu agent menulis semua, tapi:

```
Untuk tiap file (URUTAN dependency, SEQUENTIAL — bukan paralel):
  1. Parent (sesi utama) cari nomor baris section BLUEPRINT yang relevan (Grep).
  2. Parent spawn 1 subagent (general-purpose) dengan brief SELF-CONTAINED:
     - WAJIB panggil skill `ponytail:ponytail` sebelum nulis kode.
     - Section BLUEPRINT mana yang dibaca (HANYA itu).
     - Shape dataclass/signature yang TIDAK boleh diubah.
     - Context boundary: file/konsep yang TIDAK perlu ia tahu.
     - Verifikasi sendiri sebelum lapor (compile + self-check + import).
  3. Subagent kerja di context window-nya sendiri (bersih) → lapor.
  4. Parent TIDAK percaya laporan mentah: baca file hasil + jalankan
     sendiri (pytest / self-check / uji pakai fixture nyata).
  5. Bug cross-file diperbaiki di AKAR (producer), bukan ditambal di hilir.
  6. Baru lanjut file berikutnya.
```

Aturan yang terbukti penting:
- **Sequential**, karena tiap file depend pada shape file sebelumnya. Paralel = subagent ngarang shape tak konsisten.
- **Verifikasi manual menangkap 2 bug nyata** (poin 2.3 & 2.4) yang lolos dari self-check subagent. Jangan skip langkah ini.
- **Tiap subagent WAJIB ponytail.** Semua file ditulis dengan filosofi ini: solusi terpendek yang benar, stdlib-first, Phase 2 ditunda dengan ponytail comment (bukan diimplementasi spekulatif).
- Logic non-trivial punya self-check `if __name__ == "__main__"` (assert-based) di tiap module scanner.

Env: venv di `venv/` (gitignored). pytest sudah terinstall di sana. Jalankan test via `venv/bin/pytest`. Python `python3` (bukan `python`).

---

## 4. Yang harus dilakukan sesi berikut (IKUTI Task_plan.md — JANGAN lompat)

Urutan plan: berikutnya adalah **File 10 → `graps/ai/cache.py`** (lihat Task_plan.md §10). Lanjutkan nomor demi nomor: 10 → 11 (ai/provider) → 12 (server/app) → 13 (cli) → 15 (frontend) → 16 (pyproject) → 17–19 (test graph_builder, test api, CI). File 14 (`graps/__init__.py`) SUDAH dibuat sesi ini.

Pakai flow Bagian 3 yang sama: subagent sequential + ponytail + parent verifikasi.

**Catatan kontrak untuk konsumen scanner (jangan dilanggar):**
- `safe_parse()` → cek `result.warnings`, BUKAN `is None`.
- Output graph dari `build_graph(results, root)` punya keys `meta/nodes/edges/warnings` (skema §7). Field Phase 2 saat ini default kosong/null.
- Path di output SELALU relative-to-root (security M-03). Jangan bocorkan absolute path.

**Hutang Phase 2 yang BELUM digarap (jangan dikira sudah ada):**
- Parser belum ekstrak: module constants, function params, returns, line_end, classes. (Schema §7 punya slot-nya, isinya default.)
- Akibatnya **File 17 `tests/test_graph_builder.py`** yang meng-assert `DB_PASSWORD → "[REDACTED]"` BELUM bisa hijau sampai parser mengekstrak constants. Jalur sanitize sudah di-wire di `graph_builder._sanitized_constants()` — tinggal beri ia input. Saat menggarap File 17, putuskan: tambah ekstraksi constants di parser dulu (update BLUEPRINT bila ada keputusan arsitektur baru), atau sesuaikan scope test.
- `risk_analyzer`: baru `star_import`. Sisa risk (none_return_unchecked, dead_code, circular_import_toplevel, uncaught_exception, missing_type_annotation, unused_parameter) = Phase 2, sudah dicatat sebagai comment di module.

System prompt siap-pakai untuk sesi berikut: lihat **`NEXT_SESSION_PROMPT.md`**.
