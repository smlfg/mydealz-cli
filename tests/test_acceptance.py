"""Akzeptanztests – führen die CLI als Subprozess aus.

Lädt die agent-learnings-Sandbox via PYTHONPATH, so dass der
CLI-Subprozess nur Loopback-Verbindungen öffnen darf.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HARNESS = Path("/home/box/cli-daily/agent-learnings/tests/harness")


def _run_cli(*args, env_extra=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(HARNESS)
    env["ACCEPTANCE_SANDBOX"] = "1"
    # Schnelles Testen: 0 ms Rate-Limit
    env["MDZ_MIN_INTERVAL_MS"] = "0"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "mydealz_cli.cli", *args],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30,
    )


def test_no_network_access_at_all():
    """Der CLI-Aufruf ohne Subbefehl darf nirgendwo hin telefonieren."""
    r = _run_cli("--version")
    assert r.returncode == 0
    assert "mydealz" in r.stdout


def test_help_runs():
    r = _run_cli("--help")
    assert r.returncode == 0
    assert "search" in r.stdout
    assert "watch" in r.stdout


def test_search_fails_cleanly_when_no_network():
    """Wenn der CLI-Subprozess versucht, echte Hosts zu erreichen,
    blockt die Sandbox und der Prozess antwortet mit Exit 3 oder
    wirft eine Exception."""
    r = _run_cli("search", "--query", "kindle", "--limit", "1", "--json")
    # akzeptabel: 3 (HTTP/Netz)
    assert r.returncode != 0
    assert '"error"' in r.stderr or "DNS" in r.stderr or "blocked" in r.stderr


def test_show_invalid_input_exits_1():
    r = _run_cli("show", "not-a-number")
    assert r.returncode == 1
    assert '"error"' in r.stderr


def test_search_no_query_is_allowed():
    """`search` ohne --query listet alle Deals; ohne Netz → Exit 3 (HTTP)."""
    r = _run_cli("search", "--limit", "1", "--json")
    # Wir akzeptieren 1 (parse, kein HTTP nötig — wir haben keine Filter, also würde
    # der URL-Bau stattfinden und der HTTP-Client blockieren). Akzeptabel: 3.
    assert r.returncode in (1, 3)
    assert r.stderr.strip() != ""


def test_watch_missing_query_exits_1():
    r = _run_cli("watch", "--json")
    assert r.returncode == 1