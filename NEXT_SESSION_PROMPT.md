# SYSTEM PROMPT — Sesi berikutnya (graps Phase 1, lanjutan)

Salin blok di bawah sebagai prompt pembuka sesi berikutnya.

---

Kamu melanjutkan implementasi **graps Phase 1**. Sesi sebelumnya menyelesaikan File 1–9 (scanner core). Baca `HANDOFF.md` di root SEBELUM mulai — itu berisi rangkuman, deviasi dari plan, dan kontrak yang tidak boleh dilanggar.

## Sumber kebenaran (urutan prioritas)
1. `Task_plan.md` — urutan implementasi & detail per file. JANGAN lompati nomor.
2. `BLUEPRINT.md` — keputusan arsitektur. JANGAN buat keputusan arsitektur baru tanpa update BLUEPRINT dulu.
3. `HANDOFF.md` — apa yang sudah ada & hutang Phase 2.

## Yang dikerjakan sesi ini
Mulai dari **File 10 → `graps/ai/cache.py`** (Task_plan.md §10). Lalu lanjut berurutan: 11 (ai/provider) → 12 (server/app) → 13 (cli) → 15 (frontend) → 16 (pyproject) → 17 (test_graph_builder) → 18 (test_api) → 19 (CI). File 14 sudah dibuat.

## Metodologi WAJIB (terbukti di sesi sebelumnya, jangan diubah)
Untuk tiap file, SEQUENTIAL (bukan paralel, karena dependency shape):
1. Grep BLUEPRINT untuk nomor baris section yang relevan ke file itu.
2. Spawn 1 subagent (general-purpose) dengan brief self-contained: section mana yang dibaca, shape/signature yang tak boleh diubah, context boundary (apa yang TIDAK perlu ia tahu), dan perintah verifikasi-sendiri.
3. **Setiap subagent WAJIB memanggil skill `ponytail:ponytail` sebelum menulis kode.** Solusi terpendek yang benar, stdlib-first, Phase 2 ditunda dengan ponytail comment.
4. Setelah subagent lapor, JANGAN percaya laporan mentah — baca file hasil & jalankan sendiri (compile + pytest + uji pakai fixture/skenario nyata).
5. Bug cross-file diperbaiki di AKAR (producer), bukan ditambal di hilir.
6. Tandai task selesai, lanjut file berikutnya.

## Kontrak scanner (jangan dilanggar saat menggarap server/cli/test)
- `safe_parse(path) -> ParseResult` SELALU return ParseResult (tidak pernah None). Cek `result.warnings`.
- `build_graph(results, root) -> dict` dengan keys `meta/nodes/edges/warnings` (skema BLUEPRINT §7). Field Phase 2 default kosong/null.
- Semua path di output relative-to-root (security M-03). Jangan bocorkan absolute path.
- AI provider (File 11): `claude-haiku-4-5-20251001` (Anthropic) & `gpt-4o-mini` (OpenAI resmi). Jangan store API key sebagai instance attribute — baca dari env tiap call. `scrub_secrets()` sebelum kirim ke AI. (BLUEPRINT §10)
- Server (File 12): `host="127.0.0.1"` HARDCODE; CORS + enforce_origin + validate_host wajib (BLUEPRINT §11).

## Hutang Phase 2 (sudah dicatat, jangan dikira beres)
- Parser belum ekstrak constants/params/returns/classes. File 17 (test_graph_builder) yang assert redaksi `DB_PASSWORD` belum bisa hijau sampai parser mengekstrak constants — jalur `graph_builder._sanitized_constants()` sudah di-wire, tinggal diberi input. Putuskan saat menggarap File 17 (mungkin perlu update BLUEPRINT).
- `risk_analyzer` baru `star_import`; risk lain Phase 2.

## Lingkungan
- venv di `venv/` (gitignored), pytest terinstall. Test: `venv/bin/pytest tests/ -q`.
- Python interpreter: `python3` (bukan `python`).
- Bahasa komunikasi: Indonesia.
