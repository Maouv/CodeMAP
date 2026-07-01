"""Test cache file permission 0o600 + gitignore startup warning (PHASE3 Task 3)."""

from __future__ import annotations

import threading

from graps import cli
from graps.ai.cache import read_cache, write_cache


def test_cache_file_created_with_600_permission(tmp_path):
    cache_path = tmp_path / ".graps" / "cache.json"
    write_cache(cache_path, "key", {"foo": "bar"})
    mode = oct(cache_path.stat().st_mode)[-3:]
    assert mode == "600", oct(cache_path.stat().st_mode)


def test_warn_if_cache_not_ignored__warns_when_absent(tmp_path, capsys):
    (tmp_path / ".gitignore").write_text("node_modules/\n*.pyc\n")
    cli._warn_if_cache_not_ignored(tmp_path)
    out = capsys.readouterr().out
    assert ".graps/" in out, out
    assert "belum ada di .gitignore" in out, out


def test_warn_if_cache_not_ignored__silent_when_listed(tmp_path, capsys):
    (tmp_path / ".gitignore").write_text(".graps/\nnode_modules/\n")
    cli._warn_if_cache_not_ignored(tmp_path)
    out = capsys.readouterr().out
    assert "belum ada di .gitignore" not in out, out


def test_write_cache__concurrent_different_keys_all_present(tmp_path):
    """Finding 3: concurrent writes to the same cache file must not lose entries.

    Barrier-synchronize N threads so they all hit read_cache at nearly the same
    time — without the per-path Lock, most entries are lost (lost-update race).
    """
    cache_path = tmp_path / "cache.json"
    n = 20
    barrier = threading.Barrier(n)

    def _writer(k: str, v: str) -> None:
        barrier.wait()
        write_cache(cache_path, k, {"file_modified_at": "2026-01-01", "summary": {"role": v}})

    threads = [
        threading.Thread(target=_writer, args=(f"f.py::fn{i}", f"v{i}"))
        for i in range(n)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    entries = read_cache(cache_path)["entries"]
    for i in range(n):
        assert f"f.py::fn{i}" in entries, f"lost update: fn{i} missing"
        assert entries[f"f.py::fn{i}"]["summary"]["role"] == f"v{i}"
