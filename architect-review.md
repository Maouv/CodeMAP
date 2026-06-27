# Architect Review — CodeMap

> Tanggal: 2026-06-27
> Reviewer: Architect (Hermes)
> Status: Draft

---

## Ringkasan

CodeMap adalah tool visualisasi codebase berbasis:
- **Python AST parsing** — static analysis dependensi
- **FastAPI** — backend API + static file serving
- **D3 force-directed graph** — visualisasi dependensi di browser

Di bawah ini review teknis tiga komponen kritis.

---

## 1. AST Approach: Kecukupan & Edge Cases

### Verdict: **Tidak cukup untuk semua Python patterns**

`ast` module hanya menangani *static syntax tree* dari source code valid. Berikut failure modes:

### Edge Cases — Bisa Crash / Silent Wrong

| Pattern | Masalah | Severity |
|---------|---------|----------|
| `exec()` / `eval()` | Kode string dibangun runtime — AST parser tidak bisa lihat isinya | **High** |
| Decorator pabrik dinamis (`@decorator(arg)`) | AST lihat `Call` node, efek transformasi terjadi runtime | Medium |
| Metaclass + `__init_subclass__` | Method/attribute injection saat class *executed*, bukan di AST | **High** |
| Conditional import + `TYPE_CHECKING` | `if TYPE_CHECKING: from x import y` — AST lihat, import sebenarnya beda | Medium |
| `try: import X except: import Y` | AST lihat keduanya; mana yang benar dipakai perlu runtime | Medium |
| `__getattr__` / `__getattribute__` dinamis | Attribute lookup ditentukan runtime, AST tidak bisa infer | **High** |
| `functools.singledispatch` | Overload dispatch berdasarkan type argumen pertama — runtime | Medium |
| **C extensions** (`.so`/`.pyd`) | Tidak ada Python source → AST buta total | **Critical** |
| Namespace packages (PEP 420) | Tidak ada `__init__.py` — struktur package tidak jelas dari AST | Medium |
| String annotations + `from __future__ import annotations` | AST dapat string literal, bukan resolved type | Medium |
| Monkey-patching di modul lain | Import time side-effect mengubah method/attribute modul lain | **High** |
| `inspect.getsource()` patterns | Kode yang fungsi sebenarnya di C, atau generated — crash | **High** |

### Rekomendasi: Hybrid Approach

```
Layer 1: AST static analysis     →  80% cases (import, class, function, decorator)
Layer 2: Runtime import probe    →  metaclass, singleton dispatch, conditional import
Layer 3: C extension scanner     →  deteksi .so/.pyd, fallback ke stub/metadata
Layer 4: Type annotation resolver →  typing.get_type_hints() + string eval
```

### Strategi Parsing Aman

1. **Graceful degradation** — setiap file parse gagal → log warning, jangan crash pipeline
2. **Per-file try/except** — `ast.parse()` dibungkus, file corrupt / syntax error tidak memblok file lain
3. **Encoding detection** — `tokenize.detect_encoding()` sebelum parse untuk non-UTF-8 files
4. **Max file size cutoff** — file > 1MB skip / truncate untuk hindari DoS
5. **Timeout per parse** — `ast.parse()` bisa lambat di deeply nested code; beri timeout 5s

---

## 2. FastAPI + Static File Serving: Bottleneck Analysis

### Verdict: **Bermasalah untuk project besar**

### Bottleneck

| Layer | Masalah | Dampak |
|-------|---------|--------|
| Starlette `StaticFiles` | Per-request: `os.stat()` + open + read + close. Tanpa caching bawaan | Latency spike per file |
| OS file descriptor limit | Default 1024. Concurrent >1024 → `EMFILE` crash | High concurrency → crash |
| Async I/O bukan solusi | `StaticFiles` pakai `anyio.to_thread.run_sync()` — blocking di threadpool | >100 concurrent → thread exhaustion |
| No ETag/304 caching | Setiap request full re-send. Bandwidth waste | Bandwidth boros |
| GIL contention | Threadpool I/O terbatas GIL | CPU-bound di serialisasi response |

### Catatan: 1000 files bukan 1000 concurrent request

Kalau yang dimaksud adalah **project tree dengan 1000 file** (bukan serving 1000 file bersamaan), bottleneck bukan di static serving tapi di **scanning/parsing pipeline**. Static serving hanya serve file hasil build (HTML/JS/CSS/JSON graph data), jumlahnya sedikit.

### Rekomendasi

```
Production:  nginx / Caddy → static files (X-Sendfile/X-Accel)
             FastAPI → API only (JSON endpoints)

Dev:         Custom StaticFiles + aiofiles + LRU in-memory cache + ETag

Large:       CDN origin (Cloudflare R2 / S3 + CloudFront)
```

---

## 3. D3 Force-Directed Graph: Performance Limit

### Verdict: **500-3000 node tergantung renderer**

### SVG-based (default D3)

| Node Count | Experience | Root Cause |
|------------|------------|------------|
| < 500 | Smooth | — |
| 500-1500 | Noticeable lag | SVG DOM size, reflow overhead |
| 1500-3000 | Janky, 5-15 FPS | Tick simulation + DOM update per frame |
| > 3000 | **Unusable** | Browser crash / tab freeze |

### Canvas-based (d3-force + Canvas renderer)

| Node Count | Experience |
|------------|------------|
| < 5000 | Smooth |
| 5000-15k | Usable with optimizations |
| 15k-50k | Laggy but functional |
| > 50k | WebWorker + spatial indexing needed |

### WebGL (three.js / regl)

100k+ nodes feasible (contoh: Neo4j Bloom, Graphistry)

### Optimasi yang Tersedia

1. **Canvas rendering** — hapus DOM overhead (wajib di atas 2000 node)
2. **WebWorker simulation** — `d3.forceSimulation().stop()` + manual tick di worker
3. **Spatial indexing (quadtree)** — built-in via `d3.forceCollide()`
4. **Alpha decay tuning** — `alphaDecay(0.02)` lebih aggressive → simulasi selesai lebih cepat
5. **LOD (Level of Detail)** — zoom out → aggregate cluster; zoom in → detail node
6. **Viewport culling** — hanya render node dalam viewport
7. **Throttled rendering** — skip frame jika tick delta terlalu kecil

### Rekomendasi Stack per Skala

```
< 2000 nodes   →  SVG (D3 default) — cukup
2000-15k       →  Canvas + d3-force + WebWorker
15k+           →  WebGL + spatial index + LOD clustering
```

---

## Rekomendasi Arsitektur Keseluruhan

```
┌─────────────────────────────────────────────┐
│  FRONTEND (Static HTML/JS)                  │
│  D3 force-graph → Canvas renderer           │
│  WebWorker simulation tick                  │
└──────────────┬──────────────────────────────┘
               │ JSON API
┌──────────────▼──────────────────────────────┐
│  BACKEND (FastAPI)                          │
│  /api/graph       → graph data endpoint     │
│  /api/scan        → trigger scan            │
│  /api/file/:path  → file detail             │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  ANALYSIS ENGINE (Python)                   │
│  Layer 1: AST parser (ast module)           │
│  Layer 2: Runtime import probe              │
│  Layer 3: C extension scanner               │
│  Layer 4: Type resolver                     │
│  ┌──────────────────────────────────┐       │
│  │ Error handling per file:         │       │
│  │ - try/except ast.parse           │       │
│  │ - encoding detection             │       │
│  │ - max file size guard            │       │
│  │ - 5s timeout per parse           │       │
│  │ - skip & log, jangan crash       │       │
│  └──────────────────────────────────┘       │
└─────────────────────────────────────────────┘
```

---

## Action Items

- [ ] Pilih renderer: **Canvas** (target 2000-5000 node awal)
- [ ] Implement WebWorker untuk simulation tick
- [ ] AST parser dengan graceful degradation per file
- [ ] Tambah runtime import probe untuk metaclass/dynamic patterns
- [ ] Nginx di depan FastAPI untuk static serving (production)
- [ ] Tambah ETag + Cache-Control header di endpoint static
