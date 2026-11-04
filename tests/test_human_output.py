"""Tests für menschliche Club-Ausgabe (Teil 2): search/show/watch im
Terminal ohne --json lesbar; Pipe (nicht-TTY) bleibt unverändert JSON.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mydealz_cli import cli  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


class FakeClient:
    def __init__(self, html, url=None):
        self._html = html
        self._url = url

    def get(self, url):
        from mydealz_cli.http_client import Response

        return Response(status=200, url=self._url or url, text=self._html)


@pytest.fixture(scope="module")
def search_html() -> str:
    return (FIX / "search_kindle.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def detail_html() -> str:
    return (FIX / "detail_2853300.html").read_text(encoding="utf-8")


@pytest.fixture()
def tty(monkeypatch):
    """Fake-TTY für stdout/stderr (capsys bleibt aktiv)."""
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
    monkeypatch.setattr(cli, "_stderr_is_tty", lambda: True)


def _fake_http(monkeypatch, html):
    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient(html))


# ---------- search ----------

def test_search_pipe_without_json_stays_json(search_html, capsys, monkeypatch):
    _fake_http(monkeypatch, search_html)
    assert cli.main(["search", "kindle"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["anzahl"] >= 1


def test_search_terminal_readable(search_html, capsys, monkeypatch, tty):
    _fake_http(monkeypatch, search_html)
    assert cli.main(["search", "kindle"]) == 0
    out = capsys.readouterr().out
    assert " Treffer · https://" in out
    lines = [ln for ln in out.splitlines() if ln.startswith(" [")]
    assert lines, out
    pattern = re.compile(
        r"^ \[\d+\] .+ \| .+ \| .+ \| \d+° \| ID \d+$"
    )
    assert pattern.match(lines[0]), lines[0]
    # IDs der Fixture-Deals kommen vor
    assert "ID 2853300" in out


def test_search_terminal_with_explicit_json_stays_json(
    search_html, capsys, monkeypatch, tty,
):
    _fake_http(monkeypatch, search_html)
    assert cli.main(["search", "kindle", "--json"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["anzahl"] >= 1


@pytest.fixture(scope="module")
def coupon_html() -> str:
    return (FIX / "search_coupon.html").read_text(encoding="utf-8")


def test_search_terminal_free_coupon_line(coupon_html, capsys,
                                          monkeypatch, tty):
    _fake_http(monkeypatch, coupon_html)
    assert cli.main(["search", "gutschein", "--type", "coupon"]) == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith(" [")]
    assert lines, out
    assert any("Code " in ln or "Gratis" in ln or "ID " in ln for ln in lines)


# ---------- show ----------

def test_show_pipe_without_json_stays_json(detail_html, capsys, monkeypatch):
    _fake_http(monkeypatch, detail_html)
    assert cli.main(["show", "2853300"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "deal" in payload


def test_show_terminal_readable(detail_html, capsys, monkeypatch, tty):
    _fake_http(monkeypatch, detail_html)
    assert cli.main(["show", "2853300"]) == 0
    out = capsys.readouterr().out
    assert '"deal"' not in out
    assert "Deal-URL: https://" in out
    assert out.splitlines()[0]  # Titel als erste Zeile


def test_show_falls_back_to_share_deal_on_410(detail_html, capsys, monkeypatch):
    from mydealz_cli.http_client import Response

    seen = []

    class Client:
        def get(self, url):
            seen.append(url)
            if url.endswith("/deals/2853300"):
                return Response(status=410, url=url, text="gone")
            if url.endswith("/share-deal/2853300"):
                return Response(
                    status=200,
                    url="https://www.mydealz.de/deals/schachnovelle-2853300",
                    text=detail_html,
                )
            raise AssertionError(url)

    monkeypatch.setattr(cli, "HttpClient", lambda: Client())
    assert cli.main(["show", "2853300", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["deal"]["id"] == "2853300"
    assert "Schachnovelle" in payload["deal"]["titel"]
    assert seen == [
        "https://www.mydealz.de/deals/2853300",
        "https://www.mydealz.de/share-deal/2853300",
    ]


def test_show_uses_given_slug_url_unchanged(detail_html, capsys, monkeypatch):
    from mydealz_cli.http_client import Response

    seen = []
    slug = (
        "https://www.mydealz.de/deals/amazon-kindle-schachnovelle-"
        "2853300"
    )

    class Client:
        def get(self, url):
            seen.append(url)
            return Response(status=200, url=url, text=detail_html)

    monkeypatch.setattr(cli, "HttpClient", lambda: Client())
    assert cli.main(["show", slug, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["deal"]["id"] == "2853300"
    assert seen == [slug]


# ---------- watch ----------

def test_watch_pipe_without_json_stays_json(
    search_html, capsys, monkeypatch, tmp_path,
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _fake_http(monkeypatch, search_html)
    state = tmp_path / "xdg" / "mydealz-cli" / "watch.json"
    assert cli.main(["watch", "kindle"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["anzahl_neu"] >= 1
    assert state.exists()


def test_watch_terminal_readable(
    search_html, capsys, monkeypatch, tmp_path, tty,
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    _fake_http(monkeypatch, search_html)
    assert cli.main(["watch", "kindle"]) == 0
    out = capsys.readouterr().out
    assert "neue Deal(s) für 'kindle'" in out
    assert "ID 2853300" in out
    assert '"neue_deals"' not in out

    # zweiter Lauf: nichts neu, State-Datei genannt
    assert cli.main(["watch", "kindle"]) == 0
    out2 = capsys.readouterr().out
    assert "0 neue Deal(s) für 'kindle'" in out2
    assert "State-Datei: " in out2
