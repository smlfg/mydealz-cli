"""Akzeptanztests aus den UX-Sitzungen in ``docs/UX.md``.

Das Tool läuft als Subprozess gegen den Fake-Server. Alle Requests bleiben
loopback; ``MYDEALZ_BASE_URL`` zeigt auf den Fake-Server, die
Netzwerk-Sandbox aus ``tests/harness/`` blockt alles andere.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "harness"
SCRATCH_TMP = ROOT / "scratch" / "tmp"

sys.path.insert(0, str(HARNESS))

from fake_server import FakeServer  # noqa: E402
from ux_spec import parse  # noqa: E402


def _spec():
    spec = parse(ROOT / "docs" / "UX.md")
    assert not spec.errors, spec.errors
    return spec


def _workspace() -> Path:
    SCRATCH_TMP.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="mydealz-accept-", dir=SCRATCH_TMP))


def _env(server: FakeServer, home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(HARNESS),
            "PYTHONUNBUFFERED": "1",
            "ACCEPTANCE_SANDBOX": "1",
            "ACCEPTANCE_NET_LOG": str(home / "net.log"),
            "MYDEALZ_BASE_URL": server.base_url,
            "XDG_CONFIG_HOME": str(home / ".config"),
            "HOME": str(home),
            "MDZ_MIN_INTERVAL_MS": "0",
            "TERM": "xterm",
        }
    )
    return env


def _run(server: FakeServer, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mydealz_cli.cli", *args],
        capture_output=True,
        text=True,
        env=_env(server, home),
        cwd=str(ROOT),
        timeout=30,
    )


def _payload(result: subprocess.CompletedProcess) -> dict:
    assert result.returncode == 0, (
        f"Exit {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return json.loads(result.stdout)


def _assert_no_external_requests(home: Path) -> None:
    log = home / "net.log"
    if log.exists():
        assert log.read_text(encoding="utf-8").strip() == "", log.read_text(
            encoding="utf-8"
        )


def test_search_session():
    """UX-Sitzung: ``mydealz search airpods --max-price 150``."""
    home = _workspace()
    try:
        with FakeServer(_spec(), ROOT) as server:
            result = _run(server, home, "search", "airpods", "--max-price", "150")
            payload = _payload(result)

            assert payload["anzahl"] >= 1
            first = payload["deals"][0]
            assert first["id"] == "2854689"
            assert "OTTO" in ((first.get("haendler") or {}).get("name") or "")

            requests = [r for r in server.requests if r.path == "/search"]
            assert requests, "Suche hat den Fake-Server nicht erreicht"
            query = requests[0].query
            assert "q=airpods" in query
            assert "max-price=150" in query
            assert "hide-expired=1" in query
            _assert_no_external_requests(home)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_show_session():
    """UX-Sitzung: ``mydealz show 2853300``."""
    home = _workspace()
    try:
        with FakeServer(_spec(), ROOT) as server:
            result = _run(server, home, "show", "2853300")
            payload = _payload(result)

            deal = payload["deal"]
            assert deal["id"] == "2853300"
            assert "Schachnovelle" in deal["titel"]
            assert "JS-only" in (deal.get("hinweis") or "")
            assert any(r.path == "/deals/2853300" for r in server.requests)
            _assert_no_external_requests(home)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_watch_session():
    """UX-Sitzung: ``mydealz watch "switch 2"`` zweimal."""
    home = _workspace()
    try:
        with FakeServer(_spec(), ROOT) as server:
            first = _payload(_run(server, home, "watch", "switch 2"))
            assert first["anzahl_neu"] == 3
            assert first["anzahl_aktuell"] == 3
            assert {d["id"] for d in first["neue_deals"]} == {
                "2864775",
                "2864665",
                "2864186",
            }

            second = _payload(_run(server, home, "watch", "switch 2"))
            assert second["anzahl_neu"] == 0
            assert second["anzahl_aktuell"] == 3

            state_path = Path(second["state_datei"])
            assert state_path.is_file()
            assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
            assert len([r for r in server.requests if r.path == "/search"]) >= 2
            _assert_no_external_requests(home)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_watch_dry_run_keeps_state():
    """UX-Sitzung: ``mydealz watch "switch 2" --dry-run`` ändert nichts."""
    home = _workspace()
    try:
        with FakeServer(_spec(), ROOT) as server:
            first = _payload(_run(server, home, "watch", "switch 2"))
            state_path = Path(first["state_datei"])
            before = state_path.read_bytes()

            dry = _payload(_run(server, home, "watch", "switch 2", "--dry-run"))
            assert dry["anzahl_neu"] == 0
            assert dry["anzahl_aktuell"] == 3
            assert "Dry-Run" in (dry.get("hinweis") or "")
            assert state_path.read_bytes() == before
            _assert_no_external_requests(home)
    finally:
        shutil.rmtree(home, ignore_errors=True)
