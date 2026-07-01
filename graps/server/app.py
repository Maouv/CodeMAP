"""FastAPI app factory untuk graps (lihat BLUEPRINT.md §10–§12).

Module ini hanya tahu cara menyusun :class:`FastAPI` dengan:

- middleware keamanan ``enforce_origin`` + ``validate_host`` (BLUEPRINT §11),
- route ``GET /api/graph`` yang mengembalikan ``graph_data`` apa adanya,
- route ``POST /api/ai/summary`` yang dispatch ke ``graps.ai.provider`` dan
  cache hasilnya via ``graps.ai.cache``,
- mount static frontend di ``/`` (paling akhir supaya API tidak ke-shadow).

Pinning host ``127.0.0.1`` adalah tanggung jawab caller (``cli.py``). Module
ini cuma butuh ``port`` untuk membentuk daftar origin yang diizinkan.

ponytail: tidak pakai ``APIRouter``/DI framework — semua route di satu file,
``cache_path`` di-close-over dari ``create_app``. Pindah ke router kalau
endpoint sudah lewat ~10.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ponytail: dipanggil sebagai `python graps/server/app.py` (self-check) butuh
# repo root di sys.path supaya `import graps.ai...` ketemu. Tambah sebelum
# import graps.* di bawah. No-op kalau dijalankan via `python -m`.
if __name__ == "__main__":
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ponytail: import modul, BUKAN ``from ... import get_provider``. Supaya test
# (dan integrasi lain) bisa monkeypatch ``provider_module.get_provider`` dan
# perubahan terlihat di sini juga.
from graps.ai import cache as cache_module  # noqa: E402
from graps.ai import provider as provider_module  # noqa: E402
from graps.ai.provider import AIError  # noqa: E402

logger = logging.getLogger(__name__)

FRONTEND_DIR: Path = Path(__file__).parent.parent / "frontend"
DEFAULT_CACHE_PATH: Path = Path.cwd() / ".graps" / "cache.json"


class SummaryRequest(BaseModel):
    """Body untuk ``POST /api/ai/summary`` (lihat BLUEPRINT §10).

    Phase 1 trust input: frontend mengirim ``source`` mentah dari file yang
    sudah dia baca via ``GET /api/graph`` + fetch lokal. Tidak ada validasi
    panjang/charset di sini — provider yang akan menolak kalau over-limit.
    """

    file: str
    function: str
    line: int
    modified_at: str
    source: str


def create_app(
    graph_data: dict,
    port: int,
    cache_path: Path | None = None,
) -> FastAPI:
    """Bangun :class:`FastAPI` lengkap dengan middleware, route, dan static mount.

    Parameters
    ----------
    graph_data:
        Dict graph hasil scanner. Dikembalikan apa adanya oleh ``GET /api/graph``.
    port:
        Port yang akan dipakai uvicorn — dipakai untuk membentuk daftar origin
        & host yang sah (``localhost:<port>`` / ``127.0.0.1:<port>``).
    cache_path:
        Lokasi file cache AI summary. ``None`` → :data:`DEFAULT_CACHE_PATH`.
        Caller (CLI) yang boleh memilih, frontend tidak.
    """
    if cache_path is None:
        cache_path = DEFAULT_CACHE_PATH

    app = FastAPI()
    allowed = (f"http://localhost:{port}", f"http://127.0.0.1:{port}")

    # CORS — Phase 1 hanya GET/POST, tidak ada cookie (allow_credentials=False).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def enforce_origin(request: Request, call_next):
        """Tolak POST/PUT/DELETE tanpa Origin valid (CSRF guard, BLUEPRINT §11).

        Fail-closed: state-mutating methods WAJIB membawa Origin yang sah.
        Browser selalu set Origin pada same-origin POST, jadi frontend tetap
        jalan; non-browser client (curl/script) yang omit Origin ditolak 403
        supaya tidak bisa bypass CSRF guard (report-bug-finder Finding 2).
        """
        if request.method in ("POST", "PUT", "DELETE"):
            origin = request.headers.get("origin", "")
            if not origin or not any(origin.startswith(a) for a in allowed):
                return JSONResponse({"error": "Forbidden"}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def validate_host(request: Request, call_next):
        """DNS rebinding protection — Host header harus localhost/127.0.0.1."""
        host = request.headers.get("host", "")
        if host not in (f"localhost:{port}", f"127.0.0.1:{port}"):
            return JSONResponse({"error": "Invalid Host"}, status_code=400)
        return await call_next(request)

    @app.get("/api/graph")
    def get_graph() -> dict:
        """Return graph hasil scanner apa adanya."""
        return graph_data

    @app.post("/api/ai/summary")
    def post_summary(req: SummaryRequest) -> dict:
        """Generate (atau ambil dari cache) AI summary untuk satu function.

        Semua error AI dikembalikan sebagai HTTP 200 dengan ``error_type``
        supaya browser tidak memunculkan dialog auth dan frontend bisa
        memutuskan UI sendiri (BLUEPRINT §10).
        """
        provider = provider_module.get_provider()
        if provider is None:
            return {"enabled": False, "reason": "no_api_key"}

        key = f"{req.file}::{req.function}"
        cache = cache_module.read_cache(cache_path)
        hit = cache["entries"].get(key)
        if hit and cache_module.is_valid(hit, req.modified_at):
            return {
                "enabled": True,
                "cached": True,
                "summary": hit["summary"],
                "provider": hit["provider"],
            }

        try:
            summary = provider.generate_summary(
                req.source,
                {"name": req.function, "file": req.file, "line": req.line},
            )
        except AIError as e:
            # sdk_not_installed = AI tidak tersedia fungsional → enabled False.
            if e.error_type == "sdk_not_installed":
                return {"enabled": False, "reason": "sdk_not_installed"}
            payload: dict = {"enabled": True, "error_type": e.error_type}
            if e.error_type == "rate_limited" and e.retry_after is not None:
                payload["retry_after"] = e.retry_after
            return payload
        # ponytail: SENGAJA tidak catch ``Exception`` di sini — bug nyata (mis.
        # bug di cache.py) harus bubble jadi 500 supaya kelihatan, bukan
        # dibungkus jadi error_type="unknown".

        cache_module.write_cache(
            cache_path,
            key,
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "file_modified_at": req.modified_at,
                "provider": provider.name,
                "summary": summary,
            },
        )
        return {
            "enabled": True,
            "cached": False,
            "summary": summary,
            "provider": provider.name,
        }

    # Static mount HARUS terakhir — kalau di-mount sebelum route, "/" akan
    # menelan request dan API ter-shadow. Skip dengan warning kalau frontend
    # belum ada (mis. saat test atau saat dev install tanpa frontend bundle).
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
    else:
        logger.warning("FRONTEND_DIR %s tidak ada — static mount di-skip", FRONTEND_DIR)

    return app


if __name__ == "__main__":
    # Self-check: pakai TestClient supaya tidak perlu jalan uvicorn beneran.
    import os
    import stat
    import tempfile

    from fastapi.testclient import TestClient

    PORT = 8765
    HOST_OK = f"127.0.0.1:{PORT}"
    ORIGIN_OK = f"http://127.0.0.1:{PORT}"
    GRAPH = {"meta": {}, "nodes": [], "edges": [], "warnings": []}

    # Save env supaya self-check tidak bocor key dev ke logika "no_api_key".
    saved_env = {
        "ANTHROPIC_API_KEY": os.environ.pop("ANTHROPIC_API_KEY", None),
        "OPENAI_API_KEY": os.environ.pop("OPENAI_API_KEY", None),
    }
    saved_get_provider = provider_module.get_provider
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            app = create_app(GRAPH, port=PORT, cache_path=cache_path)
            client = TestClient(app, base_url=f"http://{HOST_OK}")

            # 1. GET /api/graph mengembalikan dict apa adanya.
            r = client.get("/api/graph", headers={"host": HOST_OK})
            assert r.status_code == 200, r.status_code
            assert r.json() == GRAPH, r.json()

            # 2. Host header jahat ditolak 400.
            r = client.get("/api/graph", headers={"host": "evil.com:1234"})
            assert r.status_code == 400, r.status_code
            assert r.json() == {"error": "Invalid Host"}, r.json()

            body = {
                "file": "a.py",
                "function": "foo",
                "line": 1,
                "modified_at": "2026-01-01",
                "source": "def foo(): pass",
            }

            # 3. Origin asing + Host valid → 403 (CSRF guard).
            r = client.post(
                "/api/ai/summary",
                json=body,
                headers={"host": HOST_OK, "origin": "http://evil.com"},
            )
            assert r.status_code == 403, r.status_code
            assert r.json() == {"error": "Forbidden"}, r.json()

            # 3b. Tanpa Origin (curl-style) → 403 (fail-closed CSRF guard, Finding 2).
            r = client.post("/api/ai/summary", json=body, headers={"host": HOST_OK})
            assert r.status_code == 403, r.status_code
            assert r.json() == {"error": "Forbidden"}, r.json()

            # 4. Tanpa API key → enabled False, no_api_key.
            r = client.post(
                "/api/ai/summary",
                json=body,
                headers={"host": HOST_OK, "origin": ORIGIN_OK},
            )
            assert r.status_code == 200, r.status_code
            assert r.json() == {"enabled": False, "reason": "no_api_key"}, r.json()

            # 5. Provider raise AIError("auth_failed") → status 200, error_type.
            class _FakeAuthFail:
                name = "fake"

                def generate_summary(self, src, ctx):
                    raise AIError("auth_failed")

            provider_module.get_provider = lambda: _FakeAuthFail()
            r = client.post(
                "/api/ai/summary",
                json=body,
                headers={"host": HOST_OK, "origin": ORIGIN_OK},
            )
            assert r.status_code == 200, r.status_code
            assert r.json() == {"enabled": True, "error_type": "auth_failed"}, r.json()

            # 6. Sukses + cache roundtrip.
            class _FakeOK:
                name = "fake"
                calls = 0

                def generate_summary(self, src, ctx):
                    type(self).calls += 1
                    return {"role": "r", "importance": "i", "hidden_assumption": "h"}

            provider_module.get_provider = lambda: _FakeOK()
            r1 = client.post(
                "/api/ai/summary",
                json=body,
                headers={"host": HOST_OK, "origin": ORIGIN_OK},
            )
            assert r1.status_code == 200, r1.status_code
            j1 = r1.json()
            assert j1["enabled"] is True and j1["cached"] is False, j1
            assert j1["summary"]["role"] == "r", j1
            assert j1["provider"] == "fake", j1

            r2 = client.post(
                "/api/ai/summary",
                json=body,
                headers={"host": HOST_OK, "origin": ORIGIN_OK},
            )
            j2 = r2.json()
            assert j2["cached"] is True, j2
            assert j2["summary"]["role"] == "r", j2

            # Cache file ada di tempdir dengan permission 0o600.
            assert cache_path.exists(), cache_path
            mode = stat.S_IMODE(os.stat(cache_path).st_mode)
            assert mode == 0o600, oct(mode)

        print("app.py self-check OK")
    finally:
        provider_module.get_provider = saved_get_provider
        for k, v in saved_env.items():
            if v is not None:
                os.environ[k] = v

