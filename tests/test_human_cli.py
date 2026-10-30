"""Tests für menschliche CLI-UX (Teil 1): positionales STICHWORT und
argparse-Fehlermeldungen im Terminal (Usage statt JSON).

Pipe/Agent-Verhalten bleibt unverändert: JSON-Fehlerobjekt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mydealz_cli import cli  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def search_html() -> str:
    return (FIX / "search_kindle.html").read_text(encoding="utf-8")


class FakeClient:
    def __init__(self, html):
        self._html = html

    def get(self, url):
        from mydealz_cli.http_client import Response

        return Response(status=200, url=url, text=self._html)


# ---------- Positionales STICHWORT ----------

def test_search_positional_sets_query(search_html, capsys, monkeypatch):
    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient(search_html))
    rc = cli.main(["search", "airpods", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["filter"]["q"] == "airpods"


def test_search_positional_multiword(search_html, capsys, monkeypatch):
    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient(search_html))
    rc = cli.main(["search", "switch", "2", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["filter"]["q"] == "switch 2"


def test_search_flag_wins_over_positional(
    search_html, capsys, monkeypatch,
):
    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient(search_html))
    rc = cli.main(["search", "pos", "--query", "flag", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["filter"]["q"] == "flag"


def test_search_no_query_still_json_and_empty_q(
    search_html, capsys, monkeypatch,
):
    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient(search_html))
    rc = cli.main(["search", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["filter"]["q"] is None


def test_watch_positional_sets_query(
    search_html, capsys, monkeypatch, tmp_path,
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient(search_html))
    rc = cli.main(["watch", "kindle", "--dry-run", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["filter"]["q"] == "kindle"


# ---------- Fehlermeldungen ----------

def _subprocess_run(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["MDZ_MIN_INTERVAL_MS"] = "0"
    return subprocess.run(
        [sys.executable, "-m", "mydealz_cli.cli", *args],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30,
    )


def _run_in_tty(*args):
    """Führt die CLI aus, deren stdio ein Pseudo-Terminal ist."""
    import select
    import pty

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["MDZ_MIN_INTERVAL_MS"] = "0"
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-m", "mydealz_cli.cli", *args],
        stdin=slave, stdout=slave, stderr=slave,
        env=env, cwd=str(ROOT),
    )
    os.close(slave)
    chunks = []
    while True:
        r, _, _ = select.select([master], [], [], 1.0)
        if r:
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        elif proc.poll() is not None:
            break
    rc = proc.wait(timeout=10)
    try:
        os.close(master)
    except OSError:
        pass
    return rc, b"".join(chunks).decode("utf-8", "replace")


def test_argparse_error_in_pipe_stays_json():
    r = _subprocess_run("search", "--type", "bogus")
    assert r.returncode != 0
    assert '"error"' in r.stderr


def test_argparse_error_in_terminal_shows_usage():
    """In einem echten Terminal: argparse-Usage statt JSON-Fehler."""
    rc, out = _run_in_tty("search", "--type", "bogus")
    assert rc == 2
    assert "usage:" in out
    assert "invalid choice" in out
    assert '"error"' not in out


def test_bare_cli_in_pipe_stays_json():
    r = _subprocess_run()
    assert r.returncode != 0
    assert '"error"' in r.stderr
    assert "Subbefehl" in r.stderr


def test_bare_cli_in_terminal_shows_usage_hint():
    rc, out = _run_in_tty()
    assert rc != 0
    assert "usage:" in out
    assert "mydealz search airpods" in out
