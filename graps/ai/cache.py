"""I/O cache murni untuk AI summary graps.

Module ini hanya tahu cara membaca/menulis file cache JSON dengan permission 0o600.
Tidak tahu apa-apa tentang AI provider, FastAPI, atau scanner.

Bentuk cache (lihat BLUEPRINT.md §10):
    {
        "version": "1",
        "entries": {
            "<file>::<func>": {
                "generated_at": "...",
                "file_modified_at": "...",
                "provider": "...",
                "summary": {...}
            }
        }
    }
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_DEFAULT: dict = {"version": "1", "entries": {}}


def read_cache(cache_path: Path) -> dict:
    """Parse cache JSON dari ``cache_path``.

    Return default ``{"version": "1", "entries": {}}`` kalau file belum ada,
    JSON corrupt, atau root bukan dict. Tidak pernah raise — caller yang
    putuskan mau log atau tidak.
    """
    try:
        data = json.loads(cache_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": "1", "entries": {}}
    if not isinstance(data, dict):
        return {"version": "1", "entries": {}}
    # ponytail: tidak validasi shape lebih dalam (entries harus dict, version harus "1").
    # Tambahkan kalau ada bug nyata dari cache yang setengah-corrupt.
    data.setdefault("version", "1")
    data.setdefault("entries", {})
    return data


# report-bug-finder Finding 3: FastAPI sync route (post_summary) jalan di
# thread pool, jadi dua POST konkuren ke cache yang sama bisa bareng-bareng
# read_cache -> modify -> write tanpa mutual exclusion. Lost-update: writer
# kedua overwrite entry writer pertama. Shared .tmp: writer A tulis .tmp,
# writer B overwrite .tmp yang sama, writer A rename isi milik B. Fix: Lock
# per-cache_path serialisasi read-modify-write, plus nama .tmp unik per call
# (defense-in-depth kalau lock pernah di-refactor keluar).
_cache_locks: dict[Path, threading.Lock] = {}
_cache_locks_lock = threading.Lock()


def _get_lock(cache_path: Path) -> threading.Lock:
    with _cache_locks_lock:
        return _cache_locks.setdefault(cache_path, threading.Lock())


def write_cache(cache_path: Path, key: str, entry: dict) -> None:
    """Merge ``entry`` ke ``entries[key]`` lalu tulis atomik dengan permission 0o600.

    Atomik = tulis ke ``<path>.tmp`` dulu, chmod 0o600, baru rename. Ini
    menghindari race (pembaca tidak pernah lihat file setengah jadi) dan
    memastikan permission tidak di-loosen umask.

    Concurrency: read-modify-write diserialisasi per ``cache_path`` dengan
    ``threading.Lock`` supaya writer konkuren tidak saling overwrite
    (lost-update) atau bertabrakan di file ``.tmp`` yang sama.
    ponytail: hanya cover konkurensi in-process (thread pool Starlette);
    multi-process butuh file lock (fcntl) — belum ada use-case graps jalan
    >1 instance ke cache yang sama.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with _get_lock(cache_path):
        data = read_cache(cache_path)
        data["entries"][key] = entry

        tmp = cache_path.with_name(
            f"{cache_path.stem}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        tmp.write_text(json.dumps(data, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(cache_path)
        # ponytail: replace() swap inode -> mode 0o600 dari tmp sudah bawa di POSIX;
        # chmod eksplisit di sini menutupi FS yang preserve perm target (cache
        # pre-existing bawaan OS lain) dan memenuhi kontrak "fix wrong perms on write".
        os.chmod(cache_path, 0o600)


def is_valid(entry: dict, current_modified_at: str) -> bool:
    """True kalau ``entry.file_modified_at`` sama dengan ``current_modified_at``."""
    return entry.get("file_modified_at") == current_modified_at


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 1. File belum ada -> default.
        missing = tmp / "nope.json"
        assert read_cache(missing) == {"version": "1", "entries": {}}

        # 2. Write + read roundtrip.
        path = tmp / "cache.json"
        write_cache(
            path,
            "f.py::foo",
            {"file_modified_at": "2026-01-01", "summary": {"role": "x"}},
        )
        assert read_cache(path)["entries"]["f.py::foo"]["summary"]["role"] == "x"

        # 3. is_valid match.
        assert is_valid({"file_modified_at": "2026-01-01"}, "2026-01-01") is True

        # 4. is_valid mismatch.
        assert is_valid({"file_modified_at": "2026-01-01"}, "2026-02-02") is False

        # 5. Permission 0o600.
        assert oct(os.stat(path).st_mode)[-3:] == "600"

        # 6. Corrupt JSON -> default, tidak raise.
        path.write_text("{not json")
        assert read_cache(path) == {"version": "1", "entries": {}}

        # 7. Write kedua dengan key berbeda -> kedua entries hadir (merge).
        write_cache(
            path,
            "f.py::foo",
            {"file_modified_at": "2026-01-01", "summary": {"role": "x"}},
        )
        write_cache(
            path,
            "g.py::bar",
            {"file_modified_at": "2026-01-02", "summary": {"role": "y"}},
        )
        after = read_cache(path)
        assert "f.py::foo" in after["entries"]
        assert "g.py::bar" in after["entries"]
        assert after["entries"]["g.py::bar"]["summary"]["role"] == "y"

        # 8. Concurrent writes key berbeda -> semua hadir (Finding 3 race fix).
        #    Barrier sync semua thread supaya read_cache hampir bareng — tanpa
        #    Lock, sebagian besar entry hilang (lost-update). Dengan Lock, semua
        #    N key utuh.
        N = 20
        barrier = threading.Barrier(N)

        def _cw(p, k, v):
            barrier.wait()
            write_cache(p, k, {"file_modified_at": "2026-01-01", "summary": {"role": v}})

        threads = [
            threading.Thread(target=_cw, args=(path, f"f.py::fn{i}", f"v{i}"))
            for i in range(N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        after = read_cache(path)
        for i in range(N):
            assert f"f.py::fn{i}" in after["entries"], f"lost update: fn{i} missing"
            assert after["entries"][f"f.py::fn{i}"]["summary"]["role"] == f"v{i}"
