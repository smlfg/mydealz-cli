"""Fehlerpfade: keine Tracebacks, saubere Exit-Codes, nächster Schritt."""

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


def _run_cli(*args, env_extra=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT / "tests" / "harness")
    env["ACCEPTANCE_SANDBOX"] = "1"
    env["MDZ_MIN_INTERVAL_MS"] = "0"
    env.pop("MYDEALZ_BASE_URL", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "mydealz_cli.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=30,
    )


def test_invalid_base_url_clean_json_error():
    r = _run_cli("search", "airpods", "--json", env_extra={"MYDEALZ_BASE_URL": "localhost"})
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    payload = json.loads(r.stderr.strip())
    assert "MYDEALZ_BASE_URL" in payload["error"]
    assert "Nächster Schritt" in payload["error"]


def test_invalid_interval_clean_json_error():
    r = _run_cli("search", "airpods", "--json", env_extra={"MDZ_MIN_INTERVAL_MS": "abc"})
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    payload = json.loads(r.stderr.strip())
    assert "MDZ_MIN_INTERVAL_MS" in payload["error"]
    assert "Nächster Schritt" in payload["error"]


def test_network_error_no_traceback():
    r = _run_cli(
        "search", "airpods", "--json",
        env_extra={"MYDEALZ_BASE_URL": "http://127.0.0.1:1"},
    )
    assert r.returncode == 3
    assert "Traceback" not in r.stderr
    payload = json.loads(r.stderr.strip())
    assert "Nächster Schritt" in payload["error"]


class _BoomClient:
    def __init__(self, exc):
        self._exc = exc

    def get(self, url):
        raise self._exc


def test_unexpected_exception_clean_json_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "HttpClient", lambda: _BoomClient(RuntimeError("kaputt")))
    with pytest.raises(SystemExit) as exc:
        cli.main(["search", "airpods", "--json"])
    assert exc.value.code == 3
    err = capsys.readouterr().err
    assert "Traceback" not in err
    payload = json.loads(err.strip())
    assert "Unerwarteter Fehler" in payload["error"]


def test_eof_returns_130_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr(cli, "HttpClient", lambda: _BoomClient(EOFError()))
    with pytest.raises(SystemExit) as exc:
        cli.main(["search", "airpods", "--json"])
    assert exc.value.code == 130
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "Abgebrochen" in err
