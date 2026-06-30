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


def write_cache(cache_path: Path, key: str, entry: dict) -> None:
    """Merge ``entry`` ke ``entries[key]`` lalu tulis atomik dengan permission 0o600.

    Atomik = tulis ke ``<path>.tmp`` dulu, chmod 0o600, baru rename. Ini
    menghindari race (pembaca tidak pernah lihat file setengah jadi) dan
    memastikan permission tidak di-loosen umask.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    data = read_cache(cache_path)
    data["entries"][key] = entry

    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(cache_path)


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
