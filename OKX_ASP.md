# OKX ASP Plan — Graps di Marketplace OKX.AI

> Event: OKX AI Agent Competition, $100K prize pool
> Deadline: Jul 17, 00:00 UTC (submit Google form + X demo)
> Target kategori: Software Utility ($2,500 × 3) / Best Product ($10K)
> Pre-condition: PHASE5 selesai (chat interface, Option C, build_ai_context)

---

## 0. Keputusan Final

| Keputusan | Alasan |
|-----------|--------|
| A2A registration (bukan A2MCP) | Graps menjual "report + visualisasi", bukan API call mentah. A2A cocok: user post task "scan repo X, kasih laporan" → graps kirim link HTML report |
| OKX files di `graps/okx/` — isolated directory | Bersih: kalau tidak menang, delete 1 folder + revert 2 file. Nol dependency ke core scanner/server |
| Hermes = agent wrapper | Onchain OS diinstall di Hermes, pakai Hermes untuk register ASP. Graps hanya expose API — Hermes yang "bicara ke OKX marketplace" |
| `--public` flag di CLI | Opt-in. Default tetap localhost-locked. Hanya longgar kalau user explicitly minta |
| HTML report viewer add-on | Graps generate halaman HTML interaktif (graf D3 + AI insight) per-scan, di-serve sebagai output. Nilai jual utama di demo video |

---

## 1. Prinsip Wajib

Sama seperti PHASE3.md / PHASE4.md / PHASE5.md:

1. Simple tapi works
2. Minimalisir bug — defensive
3. Separation of concern — `okx/` tidak tahu internal scanner
4. Riset dulu sebelum tulis manual
5. Jangan build dari nol kalau ada yang sudah dibangun

**Tambahan spesifik OKX:**

- Semua file OKX di `graps/okx/` — tidak menyentuh `graps/scanner/`, `graps/ai/`
- Server changes additive-only: `--public` flag relax CORS/host, tanpa ubah flow dasar
- `pyproject.toml` — OKX deps sebagai `[project.optional-dependencies]` group `okx`, bukan core dep
- Cleanup = `rm -rf graps/okx/` + revert 2 file (`cli.py`, `app.py`) + uninstall 1 npm skill

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  OKX Marketplace                                 │
│  ┌───────────┐    ┌──────────┐    ┌───────────┐ │
│  │ User post │───→│ Payment  │───→│ Forward   │ │
│  │ task      │    │ escrow   │    │ to agent  │ │
│  └───────────┘    └──────────┘    └─────┬─────┘ │
└─────────────────────────────────────────┼───────┘
                                          │
                                    ┌─────▼─────┐
                                    │  Hermes    │  ← Onchain OS terinstall
                                    │  + Agent   │    (npx skills add okx/...)
                                    └─────┬─────┘
                                          │ "Scan repo X, return report"
                                          │
                              ┌───────────▼───────────┐
                              │   Graps API (VPS)     │
                              │                        │
                              │  POST /okx/scan        │ ← endpoint buat Hermes
                              │  ┌──────────────────┐ │
                              │  │ clone repo        │ │
                              │  │ scan → graph      │ │
                              │  │ generate HTML rpt │ │
                              │  │ return {url, json} │ │
                              │  └──────────────────┘ │
                              └────────────────────────┘
```

---

## 3. File Perubahan — Detail

### 3.1 `graps/okx/` — Direktori Baru (Semua OKX Disini)

Struktur:

```
graps/okx/
├── __init__.py          # Package init, kosong
├── router.py            # FastAPI router: POST /okx/scan, GET /okx/report/{id}
├── scanner.py           # Clone repo → jalankan graps scanner → build graph
├── reporter.py          # Generate HTML report viewer dari graph data
└── cleanup.py           # Cleanup cron: hapus report >24 jam
```

#### `graps/okx/router.py`

FastAPI APIRouter yang di-mount ke main app saat `--public` flag aktif:

- `POST /okx/scan` — body `{repo_url: str, language?: str}` → clone repo, scan, generate report → return `{report_id, report_url, summary}`
- `GET /okx/report/{report_id}` — serve HTML report yang sudah di-generate
- Tidak ada auth di layer ini — OKX handle auth sebelum forward

#### `graps/okx/scanner.py`

Wrapper di atas graps scanner core:

- `clone_repo(url) -> Path` — `git clone --depth=1` ke tempdir
- `scan_repo(path) -> dict` — reuse `graps.cli._discover` + `_parse_file` + `build_graph`
- Return graph dict yang sama seperti `GET /api/graph`

Tidak import internal `cli._build` — kopi logika scan minimal. Supaya tidak tight-couple.

#### `graps/okx/reporter.py`

Generate HTML self-contained viewer dari graph data:

- Template HTML dengan embedded D3.js (CDN) + graph data inline
- Sama seperti frontend sekarang, tapi single-file, no server needed
- Bisa dibuka langsung di browser (no CORS issue)
- Simpan di `~/.graps/reports/{report_id}.html`

**Deps baru:** `jinja2` (untuk template HTML) — ringan, std industry.

#### `graps/okx/cleanup.py`

- Scheduled task / cron: hapus report >24 jam
- Atau: lazy cleanup tiap kali `POST /okx/scan` dipanggil

### 3.2 `graps/cli.py` — Tambah `--public` flag

Perubahan:

```python
# Parameter baru
public: bool = typer.Option(
    False, "--public",
    help="Relax host/origin untuk deployment publik (OKX ASP mode)"
)
# Pass ke create_app
fastapi_app = create_app(
    graph, port=port, cache_path=cache_path, scan_root=path,
    public=public,  # BARU
)
```

+ import `okx` router (lazy import, cuma kalau `--public`).

**File diubah:** 1 baris parameter + 1 line `create_app(...)` + optional okx router mount.

### 3.3 `graps/server/app.py` — `public` mode + OKX router

`create_app` signature tambah `public: bool = False`:

```python
def create_app(
    graph_data: dict[str, Any],
    port: int,
    cache_path: Path | None = None,
    scan_root: Path | None = None,
    public: bool = False,       # BARU
) -> FastAPI:
```

**Kalau `public=True`:**

| Middleware | Default | Public mode |
|---|---|---|
| CORS `allow_origins` | `localhost:{port}` only | `["*"]` — OKX forward dari domain mana aja |
| `enforce_origin` CSRF | Block POST tanpa Origin valid | **Tetap jalan** — Origin dicek dari request OKX |
| `validate_host` DNS rebinding | `localhost:{port}` only | **Disabled** — Host header bisa domain publik |
| OKX router mount | Tidak | Mount `graps.okx.router` |

**Kalau `public=False`:** behavior persis seperti sekarang, tidak ada perubahan.

### 3.4 `pyproject.toml` — OKX optional deps

```toml
[project.optional-dependencies]
# ... existing groups ...
okx = ["jinja2>=3.0", "GitPython>=3.1"]
```

- `jinja2` — HTML report template
- `GitPython` — clone repo via Python (tanpa subprocess `git clone`)

**Tidak ditambahkan ke `full` atau `dev`**. Hanya diinstall kalau user explicitly `pip install graps[okx]`.

### 3.5 Frontend — `graps/frontend/index.html`

Tambah hidden link/note di footer (hanya tampil saat `--public`):

```html
<!-- OKX ASP mode: powered by graps -->
```

Atau: tidak ada perubahan frontend sama sekali. Report viewer = file HTML terpisah.

### 3.6 Dokumentasi — `OKX_ASP.md` (file ini sendiri)

Disimpan di repo root. Referensi lengkap.

---

## 4. Yang TIDAK Disentuh

```
✓ graps/scanner/*          — tidak ada perubahan
✓ graps/ai/provider.py     — tidak ada perubahan
✓ graps/ai/cache.py        — tidak ada perubahan
✓ graps/frontend/*.js      — tidak ada perubahan (kecuali html note opsional)
✓ graps/server/app.py logic selain public flag — tidak ada perubahan route existing
✓ tests/*                  — test existing tetap jalan
✓ BLUEPRINT.md             — tidak perlu update (OKX = add-on, bukan core)
✓ SECURITY.md              — tidak perlu update (security model tetap sama)
```

---

## 5. Hermes + Onchain OS Setup (Terpisah dari Graps)

Ini dijalankan di Hermes, bukan di repo graps:

### Step 1: Install Onchain OS
```bash
npx skills add okx/onchainos-skills --yes -g
```
Output: skill baru di `~/.hermes/skills/onchain-os/`

### Step 2: Login Agentic Wallet
Prompt ke Hermes:
> "Log in to Agentic Wallet on Onchain OS with my email"

Perlu email, verifikasi.

### Step 3: Register A2A ASP
Prompt ke Hermes:
> "Help me register an A2A ASP on OKX.AI using OKX Agent Identity from Onchain OS"

Agent akan minta:
- Name: "Graps — Codebase Dependency Analyzer"
- Description: "Scans 306 programming languages, builds interactive dependency graph with risk analysis and AI-powered debugging chat. Returns hosted HTML report with full interactive visualization."
- Service list: ["Codebase scanning", "Dependency graph", "Risk analysis", "AI debugging chat"]
- Default pricing: e.g. $5 per scan
- Endpoint: URL VPS graps (didapat setelah deploy)

### Step 4: List ASP
Prompt:
> "Help me list my ASP on OKX.AI using Onchain OS"

Review ~24 jam.

---

## 6. Deployment (Manual / Sekali)

Tanpa Docker (user Docker skeptic):

### Opsi: VPS baremetal — uvicorn + systemd

```bash
# 1. SCP graps ke VPS
rsync -avz /workspace/codemap/ user@vps:/opt/graps/

# 2. Install di VPS
pip install /opt/graps/[okx]

# 3. Systemd service
cat > /etc/systemd/system/graps.service << EOF
[Unit]
Description=Graps API Server
After=network.target

[Service]
Type=simple
User=nobody
WorkingDirectory=/opt/graps
ExecStart=/usr/bin/python -m graps.cli /tmp/graps-scans --port 8080 --public --no-browser
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now graps
```

**Atau** Railway / Fly.io free tier (lebih simple, no VPS maintenance).

---

## 7. Cleanup Plan — Kalau Tidak Menang

```
# 1. Hapus direktori OKX
rm -rf graps/okx/

# 2. Revert cli.py — hapus --public parameter
git checkout HEAD -- graps/cli.py

# 3. Revert app.py — hapus public parameter + okx router
git checkout HEAD -- graps/server/app.py

# 4. Revert pyproject.toml — hapus okx optional-deps
git checkout HEAD -- pyproject.toml

# 5. Uninstall Onchain OS dari Hermes
#    (hapus skill dari ~/.hermes/skills/)

# 6. Destroy VPS instance
#    (atau stop service kalau pakai existing server)

# 7. Delete OKX_ASP.md (optional)
```

**File yang berubah permanen:** tidak ada. Semua revertable via git.

**Deps yang terinstall di graps venv:** `jinja2`, `GitPython` — hapus manual atau abaikan.

---

## 8. Dependency Tree

```
graps core
├── fastapi, uvicorn, typer (existing)
├── tree-sitter-language-pack (optional, multilang) (existing)
├── anthropic / openai (optional, ai) (existing)
└── jinja2, GitPython (optional, okx) ← BARU, cuma untuk --public mode

Hermes
└── npx skills: okx/onchainos-skills ← npm package, bukan Python
```

---

## 9. Timeline

| # | Task | Estimasi | Dependencies |
|---|---|---|---|
| 1 | Bikin `graps/okx/` — router + scanner + reporter | 3-4 jam | PHASE5 done |
| 2 | Tambah `--public` di cli.py + app.py | 30 menit | #1 |
| 3 | Update pyproject.toml + test `--public` mode | 30 menit | #2 |
| 4 | Deploy ke VPS | 1-2 jam | #3 |
| 5 | Install Onchain OS di Hermes | 15 menit | — |
| 6 | Register ASP via Hermes + Onchain OS | 30 menit | #4, #5 |
| 7 | Test end-to-end: marketplace → graps → report | 1 jam | #6 |
| 8 | Rekam demo 90 detik | 1 jam | #7 |
| 9 | Submit Google form + post X #okxai | 15 menit | #8 |

**Total: 1-2 hari**

---

## 10. Risk & Mitigasi

| Risk | Impact | Mitigasi |
|---|---|---|
| Onchain OS skill broken / not compatible with Hermes | Blocker ASP registration | Fallback: register manual via OKX web UI kalau ada |
| VPS cost | ~$5-7/bulan | Railway free tier / Fly.io free allowance |
| OKX Payment SDK integration complex | Delay go-live | Onchain OS claims to handle this. Kalau gagal → A2A dengan escrow (manual release) |
| Git clone abuse (arbitrary repo URL) | VPS penuh, abuse | Depth=1, cleanup >24 jam, max repo size limit |
| Report HTML size besar | Bandwidth cost | Graph data di-compress, no base64 embed |

---

## 11. Non-Goals (Out of Scope)

- ❌ User auth / login system
- ❌ Persistent user history / dashboard
- ❌ Multi-tenant isolation (selain report ID unik)
- ❌ Rate limiting (OKX handle di layer mereka)
- ❌ Billing integration manual (Onchain OS handle)
- ❌ CI/CD pipeline
- ❌ Monitoring / alerting
- ❌ Docker containerization
