"""Test cache file permission 0o600 + gitignore startup warning (PHASE3 Task 3)."""

from __future__ import annotations

from graps import cli
from graps.ai.cache import write_cache


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
