# Security Policy

## Threat Model

graps adalah tool yang berjalan 100% di komputer kamu (localhost). Tidak ada
data yang dikirim kemana pun **kecuali** saat kamu secara eksplisit generate AI
Insight — saat itu, source code function yang kamu klik dikirim ke provider AI
(Anthropic atau OpenAI) sesuai API key yang kamu set sendiri.

graps bukan multi-user server. Attacker yang realistis bukan hacker di internet,
melainkan: website lain yang kebetulan terbuka di browser kamu saat graps
berjalan, proses lain di mesin yang sama, atau user lain di shared machine.

## Apa yang TIDAK pernah dikirim

- Seluruh codebase kamu — hanya function yang kamu klik.
- File di luar direktori yang kamu scan.
- API key kamu sendiri (dipakai untuk auth ke provider, tidak pernah dikirim ke
  pihak lain, tidak disimpan di cache, tidak di-log).

## Secret Scrubbing

Sebelum source code dikirim ke AI provider, graps melakukan scrub otomatis
terhadap pola yang terlihat seperti credential (API key, password, token,
private key, connection string, dsb.) memakai detector `detect-secrets` (27
plugin built-in) ditambah regex fallback sebagai defense-in-depth.

Ini **best-effort, BUKAN jaminan**. Scrubber bisa miss format yang tidak
dikenal atau secret yang disamarkan. Review kode kamu sendiri sebelum generate
AI insight pada file yang berisi secret — terutama file yang belum kamu tulis
sendiri (output AI agent, dependency, konfigurasi yang di-paste).

## Cara Report Vulnerability

Kirim laporan lewat **GitHub Security Advisory**: buka tab "Security" →
"Report a vulnerability" di repository, atau langsung di
<https://github.com/Maouv/CodeMAP/security/advisories/new>.

Sertakan: langkah repro, versi graps, dan dampak yang kamu observasi. Tolong
jangan buka public issue untuk vulnerability yang belum di-fix — biar maintainer
bisa triage diam-diam sebelum patch dirilis.

## Known Limitations

- **Server localhost tanpa authentication.** Siapapun yang punya akses ke mesin
  yang sama bisa membuka `localhost:8765` selama server berjalan. Jangan
  jalankan graps di shared/public machine tanpa kesadaran risiko ini; bind
  sudah di-hardcode ke `127.0.0.1` (bukan `0.0.0.0`) supaya tidak expose ke
  local network.
- **Cache AI summary disimpan plaintext di disk** di `.graps/cache.json`
  (permission `0600`). Cache berisi inferensi AI tentang struktur codebase kamu
  yang bisa jadi sensitive IP. graps memperingatkan di startup kalau `.graps/`
  belum ada di `.gitignore`, tapi kamu yang bertanggung jawab menambahkannya
  agar tidak ter-commit ke Git.
- **Secret scrubbing best-effort** (lihat bagian di atas) — bukan pengganti
  review manual sebelum mengirim file sensitif ke AI.
- **Browser attack surface.** graps memakai CORS + server-side Origin/Host
  validation + bind `127.0.0.1`, tapi malicious website yang aktif di tab
  browser kamu saat graps berjalan tetap bisa mencoba request ke localhost.
  Mitigasi terkuat: tutup graps (Ctrl+C) saat tidak dipakai.
