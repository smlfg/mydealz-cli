"""Tests für mydealz.

Die Tests sind netz-frei: FakeHttpClient liefert die
Fixture-HTMLs aus tests/fixtures/. Die Akzeptanztests starten das
CLI als Subprozess mit der Network-Sandbox unter tests/harness
(sitecustomize), die alle Nicht-Loopback-Verbindungen blockiert.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mydealz_cli import parser, url_builder, watch  # noqa: E402
from mydealz_cli.cli import _apply_filters  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


# ---------- Fixtures / Helpers ----------

@pytest.fixture(scope="module")
def search_html() -> str:
    return (FIX / "search_kindle.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def search_coupon_html() -> str:
    return (FIX / "search_coupon.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def detail_html() -> str:
    return (FIX / "detail_2853300.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed_search(search_html) -> list[dict]:
    return parser.parse_search(search_html, limit=100)


# ---------- URL-Bau ----------

def test_build_search_url_basic():
    u = url_builder.build_search_url(query="kindle", hide_expired=True)
    # Suchanfragen MÜSSEN /search?q=… benutzen — die Homepage ignoriert q.
    assert u.startswith("https://www.mydealz.de/search?")
    assert "q=kindle" in u
    assert "hide-expired=1" in u


def test_build_search_url_no_query():
    # Filter ohne Stichwort: /search (Homepage ignoriert type/sortBy/…).
    u = url_builder.build_search_url(order="newest", hide_expired=True)
    assert u.startswith("https://www.mydealz.de/search?")
    assert "sortBy=new" in u
    assert "hide-expired=1" in u
    assert "q=" not in u


def test_build_search_url_filters_without_query_use_search_path():
    """Regression #7: coupon + order ohne --query."""
    u = url_builder.build_search_url(
        deal_type="coupon", order="price-low", hide_expired=True
    )
    assert u.startswith("https://www.mydealz.de/search?")
    assert "type=voucher" in u
    assert "sortBy=lowest_price" in u
    assert "hide-expired=1" in u
    assert "q=" not in u


def test_build_search_url_bare_defaults_stay_on_homepage():
    u = url_builder.build_search_url(hide_expired=True)
    assert u.startswith("https://www.mydealz.de/?")
    assert "/search" not in u


def test_build_search_url_uses_search_path_not_homepage():
    """Regression: q auf der Homepage-Route wurde stillschweigend ignoriert."""
    u = url_builder.build_search_url(query="macbook")
    assert "/search?" in u, f"erwartet /search?q=…, bekam {u}"
    assert "/?" not in u.replace("/search?", ""), "Homepage-Route würde q verschlucken"


def test_build_search_url_filters():
    u = url_builder.build_search_url(
        query="monitor",
        deal_type="deal",
        min_price=200,
        max_price=500,
        merchant_id=77,
        category_id=43,
        order="hot",
        page=2,
    )
    for p in [
        "q=monitor",
        "type=deal",
        "min-price=200",
        "max-price=500",
        "merchant-id=77",
        "group-id=43",
        "sortBy=temp",
        "page=2",
    ]:
        assert p in u, f"{p} fehlt in {u}"
def test_build_search_url_type_aliases():
    assert url_builder.build_search_url(deal_type="coupon")["type"] == "voucher" if False else "type=voucher" in url_builder.build_search_url(deal_type="coupon")
    assert "type=voucher" in url_builder.build_search_url(deal_type="voucher")
    assert "type=freebie" in url_builder.build_search_url(deal_type="freebie")


def test_build_search_url_order_aliases():
    assert "sortBy=discussion" in url_builder.build_search_url(order="discussed")
    assert "sortBy=temp" in url_builder.build_search_url(order="hot")


def test_build_search_url_sort_by_not_order_param():
    """Regression #10: mydealz ignoriert ``order=``; Sortierung läuft über ``sortBy``."""
    u = url_builder.build_search_url(query="monitor", order="price-low", hide_expired=True)
    assert "sortBy=lowest_price" in u
    assert "order=" not in u


def test_resolve_merchant_known():
    m = url_builder.resolve_merchant("amazon")
    assert m and m["name"] == "Amazon" and m["slug"] == "amazon-de"
    # keine "id" mehr — IDs sind nicht stabil
    assert "id" not in m or m.get("id") is None


def test_resolve_merchant_unknown():
    assert url_builder.resolve_merchant("nope-no-such-merchant") is None


def test_resolve_merchant_url():
    m = url_builder.resolve_merchant("https://www.mydealz.de/profile/amazon-de")
    assert m and m["name"] == "Amazon"


def test_resolve_category_known():
    c = url_builder.resolve_category("elektronik")
    assert c and c["slug"] == "elektronik"
    # keine "id" mehr
    assert "id" not in c or c.get("id") is None


def test_resolve_category_unknown():
    assert url_builder.resolve_category("nope-no-such") is None


def test_deal_url():
    assert url_builder.deal_url("2853300") == "https://www.mydealz.de/deals/2853300"


def test_normalize_thread_id():
    assert parser.normalize_thread_id("2853300") == "2853300"
    assert parser.normalize_thread_id("https://www.mydealz.de/deals/foo-2853300") == "2853300"
    with pytest.raises(ValueError):
        parser.normalize_thread_id("foo")


# ---------- Parser (echte HTML-Fixtures) ----------

def test_parse_search_returns_deals(parsed_search):
    assert len(parsed_search) >= 5
    for d in parsed_search[:5]:
        assert d["id"]
        assert d["url"].startswith("https://www.mydealz.de/deals/")
        assert d["titel"]


def test_parse_search_first_deal_shape(parsed_search):
    d = parsed_search[0]
    assert d["haendler"]["name"] in ("Amazon", "Thalia", "Kindle")
    assert d["kategorie"]["name"] in ("Kultur & Freizeit", None) or d["kategorie"]["slug"]
    assert isinstance(d["temperatur"], (int, float)) or d["temperatur"] is None
    assert d["temperatur_level"] in ("Hot1", "Hot2", "Hot3", "Cold", "Lukewarm", None)
    assert d["veroeffentlicht_am"] is None or "T" in d["veroeffentlicht_am"]


def test_parse_search_extracts_voucher_code(search_coupon_html):
    """Suche nach Gutscheinen sollte einen Deal mit Code liefern."""
    items = parser.parse_search(search_coupon_html, limit=100)
    codes = [i for i in items if i.get("gutschein_code")]
    assert codes, "mindestens ein Deal mit voucherCode erwartet"
    assert any(c["gutschein_code"].strip() for c in codes)


def test_parse_search_limit(parsed_search):
    small = parser.parse_search(open(FIX / "search_kindle.html", encoding="utf-8").read(), limit=3)
    assert len(small) == 3


def test_parse_detail_og_meta(detail_html):
    ang = parser.parse_detail_from_html(detail_html, "2853300")
    assert ang["id"] == "2853300"
    assert ang["url"]
    assert "Schachnovelle" in (ang["titel"] or "") or "Stefan Zweig" in (ang["titel"] or "")
    # beschreibung_text kann None sein (Detail-Seite ist JS-only);
    # og:description wird ergänzt, falls vorhanden, Fallback auf <title>
    assert ang["titel"] is not None


# ---------- Client-Filter ----------

def test_apply_filters_by_merchant(parsed_search):
    out = _apply_filters(parsed_search, haendler="Amazon", min_preis=None, max_preis=None,
                          min_temperatur=None, nur_aktiv=False, nur_mit_code=False)
    assert all(o["haendler"]["name"] == "Amazon" for o in out)


def test_apply_filters_by_min_price(parsed_search):
    out = _apply_filters(parsed_search, haendler=None, min_preis=10, max_preis=None,
                          min_temperatur=None, nur_aktiv=False, nur_mit_code=False)
    for o in out:
        if o["preis_eur"] is not None:
            assert o["preis_eur"] >= 10


def test_apply_filters_by_max_price(parsed_search):
    out = _apply_filters(parsed_search, haendler=None, min_preis=None, max_preis=10,
                          min_temperatur=None, nur_aktiv=False, nur_mit_code=False)
    for o in out:
        if o["preis_eur"] is not None:
            assert o["preis_eur"] <= 10


def test_apply_filters_only_active(parsed_search):
    out = _apply_filters(parsed_search, haendler=None, min_preis=None, max_preis=None,
                          min_temperatur=None, nur_aktiv=True, nur_mit_code=False)
    for o in out:
        if "ist_aktiv" in o:
            assert o["ist_aktiv"] is True


def test_apply_filters_only_with_code(parsed_search):
    out = _apply_filters(parsed_search, haendler=None, min_preis=None, max_preis=None,
                          min_temperatur=None, nur_aktiv=False, nur_mit_code=True)
    for o in out:
        assert o.get("gutschein_code")


def test_apply_filters_min_temperature(parsed_search):
    out = _apply_filters(parsed_search, haendler=None, min_preis=None, max_preis=None,
                          min_temperatur=600, nur_aktiv=False, nur_mit_code=False)
    for o in out:
        if o["temperatur"] is not None:
            assert o["temperatur"] >= 600


# ---------- Watch (lokal, ohne HTTP) ----------

def test_watch_diff_no_prior_state():
    state = watch.load_state()  # leer
    items = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    new_items, ids = watch.diff_for_query(state, query="kindle", items=items)
    assert ids == ["1", "2", "3"]
    assert len(new_items) == 3


def test_watch_diff_after_update():
    state = watch.load_state()
    items = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    new_items, _ = watch.diff_for_query(state, query="kindle", items=items)
    watch.update_state(state, query="kindle", ids=["1", "2", "3"])
    new_items2, _ = watch.diff_for_query(state, query="kindle", items=items)
    assert new_items2 == []


def test_watch_diff_partial_overlap():
    state = watch.load_state()
    watch.update_state(state, query="kindle", ids=["1", "2"])
    items = [{"id": "2"}, {"id": "3"}, {"id": "4"}]
    new_items, ids = watch.diff_for_query(state, query="kindle", items=items)
    assert ids == ["2", "3", "4"]
    new_ids = [i["id"] for i in new_items]
    assert sorted(new_ids) == ["3", "4"]


def test_watch_save_load_roundtrip(tmp_path, monkeypatch):
    state_file = tmp_path / "watch.json"
    state_file.write_text('{"version": 1, "watches": {}}', encoding="utf-8")
    state = watch.load_state(str(state_file))
    watch.update_state(state, query="monitor", ids=["42", "43"], extra_filters={"order": "hot"})
    out = watch.save_state(state, str(state_file))
    assert out == str(state_file)
    loaded = watch.load_state(str(state_file))
    # Key enthält Query+Filter, also nicht nackt "monitor"
    keys = list(loaded["watches"].keys())
    assert any(k.startswith("monitor|") for k in keys), keys
    bucket = loaded["watches"][keys[0]]
    assert bucket["ids"] == ["42", "43"]
    # Filter-Marker wird mitgespeichert
    assert bucket["filters"]["order"] == "hot"


def test_watch_state_file_permissions(tmp_path, monkeypatch):
    state_file = tmp_path / "watch.json"
    state_file.write_text('{"version": 1, "watches": {}}', encoding="utf-8")
    state = watch.load_state(str(state_file))
    watch.update_state(state, query="x", ids=["a"])
    watch.save_state(state, str(state_file))
    mode = oct(state_file.stat().st_mode)[-3:]
    assert mode in ("600",)  # Modus strikt gesetzt (oder wie umask es erlaubt)


def _watch_cli_args(**overrides):
    import argparse

    defaults = {
        "q": "kindle",
        "limit": 5,
        "merchant": None,
        "category": None,
        "type": None,
        "order": None,
        "page": None,
        "min_price": None,
        "max_price": None,
        "merchant_id": None,
        "category_id": None,
        "include_expired": False,
        "only_active": False,
        "min_temperature": None,
        "only_with_code": False,
        "dry_run": False,
        "json": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_cmd_watch_persists_state_and_second_run_has_no_new(
    tmp_path, monkeypatch, search_html, capsys,
):
    """Regression: save_state bekam None von update_state (CLI-Pfad)."""
    from mydealz_cli import cli
    from mydealz_cli.http_client import Response

    config = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))

    class FakeClient:
        def get(self, url):
            return Response(status=200, url=url, text=search_html)

    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient())

    args = _watch_cli_args()
    assert cli.cmd_watch(args) == 0
    state_file = config / "mydealz-cli" / "watch.json"
    raw = state_file.read_text(encoding="utf-8")
    assert raw.strip() != "null"
    data = json.loads(raw)
    assert data["version"] == 1
    assert len(data["watches"]) >= 1

    out1 = json.loads(capsys.readouterr().out)
    assert out1["anzahl_neu"] == 5

    assert cli.cmd_watch(args) == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["anzahl_neu"] == 0


def test_cmd_watch_dry_run_does_not_write_state(
    tmp_path, monkeypatch, search_html, capsys,
):
    """--dry-run meldet neue Deals, schreibt aber keine State-Datei."""
    from mydealz_cli import cli
    from mydealz_cli.http_client import Response

    config = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))

    class FakeClient:
        def get(self, url):
            return Response(status=200, url=url, text=search_html)

    monkeypatch.setattr(cli, "HttpClient", lambda: FakeClient())

    state_file = config / "mydealz-cli" / "watch.json"
    args = _watch_cli_args(dry_run=True)

    assert cli.cmd_watch(args) == 0
    assert not state_file.exists()

    out1 = json.loads(capsys.readouterr().out)
    assert out1["anzahl_neu"] == 5
    assert out1["hinweis"] == "Dry-Run: State wurde nicht aktualisiert."

    assert cli.cmd_watch(args) == 0
    assert not state_file.exists()

    out2 = json.loads(capsys.readouterr().out)
    assert out2["anzahl_neu"] == 5