"""CLI für mydealz (smlfg/mydealz-cli).

Subbefehle:
  search       Deals/Gutscheine suchen (öffentlich, kein Login)
  show         Deal-Details anzeigen (öffentlich, JS-only, optional Playwright)
  watch        Stichwort beobachten – neue Deals seit letztem Lauf
  --version
  --help

Nur Lesezugriffe: kein Login, keine POSTs, keine Messages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, NoReturn, Optional

from . import __version__, parser, url_builder, watch
from .http_client import HTTPError, HttpClient, ParseError


def _emit(payload: Any, as_json: bool) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _err(msg: str, *, code: int, **extra: Any) -> NoReturn:
    payload = {"error": msg, **extra}
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(code)


# ---------- Filter / gemeinsame Logik ----------

def _apply_filters(
    items: list[dict],
    *,
    haendler: Optional[str],
    min_preis: Optional[float],
    max_preis: Optional[float],
    min_temperatur: Optional[float],
    nur_aktiv: bool,
    nur_mit_code: bool,
) -> list[dict]:
    out = list(items)
    if haendler:
        sl = haendler.lower()
        out = [
            i for i in out
            if (i.get("haendler", {}).get("name") or "").lower() == sl
            or (i.get("haendler", {}).get("slug") or "").lower() == sl
        ]
    if min_preis is not None:
        out = [i for i in out if i["preis_eur"] is None or i["preis_eur"] >= min_preis]
    if max_preis is not None:
        out = [i for i in out if i["preis_eur"] is None or i["preis_eur"] <= max_preis]
    if min_temperatur is not None:
        out = [i for i in out if i["temperatur"] is None or i["temperatur"] >= min_temperatur]
    if nur_aktiv:
        out = [i for i in out if i.get("ist_aktiv") is True]
    if nur_mit_code:
        out = [i for i in out if i.get("gutschein_code")]
    return out


def _build_filters_dict(args: argparse.Namespace) -> dict:
    return {
        "q": getattr(args, "q", None),
        "type": getattr(args, "type", None),
        "order": getattr(args, "order", None),
        "page": getattr(args, "page", None),
        "min_price": getattr(args, "min_price", None),
        "max_price": getattr(args, "max_price", None),
        "merchant": getattr(args, "merchant", None),
        "merchant_id": getattr(args, "merchant_id", None),
        "category": getattr(args, "category", None),
        "category_id": getattr(args, "category_id", None),
        "only_active": getattr(args, "only_active", None),
        "only_with_code": getattr(args, "only_with_code", None),
        "min_temperature": getattr(args, "min_temperature", None),
        "limit": getattr(args, "limit", None),
    }


# ---------- search ----------

def cmd_search(args: argparse.Namespace) -> int:
    merchant_obj = None
    if args.merchant:
        merchant_obj = url_builder.resolve_merchant(args.merchant)
        if merchant_obj is None:
            _err(
                f"Unbekannter Händler: {args.merchant!r}. "
                "Nutze --merchant-id, einen bekannten Kurznamen "
                "(amazon, ebay, …) oder eine Profil-URL.",
                code=1,
            )

    category_obj = None
    if args.category:
        category_obj = url_builder.resolve_category(args.category)
        if category_obj is None:
            _err(
                f"Unbekannte Kategorie: {args.category!r}. "
                "Nutze einen bekannten Slug (elektronik, computer, …) "
                "oder eine /group/<slug>-URL.",
                code=1,
            )

    # Händler-/Kategorie-Filter wirken LOKAL auf den geparsten Treffern.
    # Die numerische mydealz-ID ist nicht stabil genug, um sie in der
    # URL zu setzen; mydealz' UI nutzt dafür JS-Routing.
    url = url_builder.build_search_url(
        query=args.q,
        deal_type=args.type,
        order=args.order,
        page=args.page,
        min_price=args.min_price,
        max_price=args.max_price,
        merchant_id=args.merchant_id,
        category_id=args.category_id,
        hide_expired=not args.include_expired,
        only_active=args.only_active,
    )
    http = HttpClient()
    try:
        r = http.get(url)
    except HTTPError as e:
        _err(f"HTTP-Fehler: {e}", code=3, url=url)
    if r.status >= 400:
        _err(f"HTTP {r.status} beim Laden der Suche", code=3, status=r.status, url=url)
    try:
        # großzügig parsen, damit Client-Filter (Händler, Kategorie, …)
        # nach dem Filtern noch echte Treffer übrig haben
        parse_limit = max(args.limit or 20, 50)
        items = parser.parse_search(r.text, limit=parse_limit)
    except ParseError as e:
        _err(f"Parse-Fehler: {e}", code=4, url=url)
    items = _apply_filters(
        items,
        haendler=(merchant_obj.get("name") if merchant_obj else None),
        min_preis=args.min_price,
        max_preis=args.max_price,
        min_temperatur=args.min_temperature,
        nur_aktiv=args.only_active,
        nur_mit_code=args.only_with_code,
    )
    if args.limit:
        items = items[: args.limit]
    payload = {
        "quelle": "https://www.mydealz.de",
        "url": url,
        "filter": _build_filters_dict(args),
        "hinweis": (
            "Händler-/Kategorie-Filter werden lokal auf den "
            "Server-Treffern angewendet, da mydealz' numerische IDs "
            "instabil sind."
            if (merchant_obj or category_obj) and not (args.merchant_id or args.category_id)
            else None
        ),
        "anzahl": len(items),
        "deals": items,
    }
    _emit(payload, args.json)
    return 0


# ---------- show ----------

def cmd_show(args: argparse.Namespace) -> int:
    try:
        tid = parser.normalize_thread_id(args.deal)
    except ValueError as e:
        _err(str(e), code=1)
    url = url_builder.deal_url(tid)
    if args.render == "playwright":
        try:
            from . import detail_render  # noqa: WPS433
        except ImportError:
            _err(
                "Playwright nicht installiert. 'pip install mydealz-cli[playwright]' "
                "und 'playwright install chromium'.",
                code=2,
                kind="playwright_missing",
            )
        try:
            ang = detail_render.render_detail(url, tid)
        except Exception as e:  # noqa: BLE001
            _err(f"Playwright-Render fehlgeschlagen: {e}", code=3)
        _emit({"quelle": "https://www.mydealz.de", "deal": ang}, args.json)
        return 0
    # Default: requests, og:* Fallback
    http = HttpClient()
    try:
        r = http.get(url)
    except HTTPError as e:
        _err(f"HTTP-Fehler: {e}", code=3, url=url)
    if r.status >= 400:
        _err(f"HTTP {r.status} beim Laden des Deals", code=3, status=r.status, url=url)
    try:
        ang = parser.parse_detail_from_html(r.text, tid)
    except ParseError as e:
        _err(f"Parse-Fehler: {e}", code=4, url=url)
    if not ang.get("url"):
        ang["url"] = r.url
    _emit({"quelle": "https://www.mydealz.de", "deal": ang}, args.json)
    return 0


# ---------- watch ----------

def cmd_watch(args: argparse.Namespace) -> int:
    # Pflicht: --query (oder --q)
    if not args.q:
        _err("--query ist erforderlich", code=1)
    state_path = watch.state_path()
    state = watch.load_state(state_path)
    filters = _build_filters_dict(args)

    merchant_obj = None
    if args.merchant:
        merchant_obj = url_builder.resolve_merchant(args.merchant)
        if merchant_obj is None:
            _err(
                f"Unbekannter Händler: {args.merchant!r}",
                code=1,
            )

    category_obj = None
    if args.category:
        category_obj = url_builder.resolve_category(args.category)
        if category_obj is None:
            _err(
                f"Unbekannte Kategorie: {args.category!r}",
                code=1,
            )

    url = url_builder.build_search_url(
        query=args.q,
        deal_type=args.type,
        order=args.order,
        page=args.page,
        min_price=args.min_price,
        max_price=args.max_price,
        merchant_id=args.merchant_id,
        category_id=args.category_id,
        hide_expired=not args.include_expired,
        only_active=args.only_active,
    )
    http = HttpClient()
    try:
        r = http.get(url)
    except HTTPError as e:
        _err(f"HTTP-Fehler: {e}", code=3, url=url)
    if r.status >= 400:
        _err(f"HTTP {r.status} beim Laden der Suche", code=3, status=r.status, url=url)
    try:
        parse_limit = max(args.limit or 50, 100)
        items = parser.parse_search(r.text, limit=parse_limit)
    except ParseError as e:
        _err(f"Parse-Fehler: {e}", code=4, url=url)
    items = _apply_filters(
        items,
        haendler=(merchant_obj.get("name") if merchant_obj else None),
        min_preis=args.min_price,
        max_preis=args.max_price,
        min_temperatur=args.min_temperature,
        nur_aktiv=args.only_active,
        nur_mit_code=args.only_with_code,
    )
    if args.limit:
        items = items[: args.limit]
    new_items, current_ids = watch.diff_for_query(
        state, query=args.q, items=items, extra_filters=filters,
    )
    state_path_written = watch.save_state(
        watch.update_state(state, query=args.q, ids=current_ids, extra_filters=filters),
        state_path,
    )
    payload = {
        "quelle": "https://www.mydealz.de",
        "url": url,
        "filter": filters,
        "hinweis": None,
        "anzahl_neu": len(new_items),
        "anzahl_aktuell": len(current_ids),
        "neue_deals": new_items,
        "state_datei": state_path_written,
    }
    if args.dry_run:
        # Kein State schreiben, nur melden, was neu wäre
        payload["hinweis"] = "Dry-Run: State wurde nicht aktualisiert."
    _emit(payload, args.json)
    return 0


# ---------- Argparse ----------

def _add_search_filters(s: argparse.ArgumentParser) -> None:
    f = s.add_argument_group("Such-Filter")
    f.add_argument("--query", dest="q", default=None, help="Stichwort")
    f.add_argument(
        "--type",
        choices=["deal", "coupon", "voucher", "freebie", "groupdeal"],
        default=None,
        help="Deal-Typ (default: alle)",
    )
    f.add_argument(
        "--order",
        choices=list(url_builder.ORDERS.keys()),
        default=None,
        help="Sortierung",
    )
    f.add_argument("--page", type=int, default=1, help="Seitenzahl (default 1)")
    f.add_argument("--min-price", type=float, default=None, help="Min. Preis in €")
    f.add_argument("--max-price", type=float, default=None, help="Max. Preis in €")
    f.add_argument(
        "--merchant",
        default=None,
        help="Händler-Kurzname (z.B. amazon, ebay, mediamarkt)",
    )
    f.add_argument("--merchant-id", type=int, default=None, help="Händler-ID (numerisch)")
    f.add_argument(
        "--category",
        default=None,
        help="Kategorie-Slug (z.B. elektronik, computer, games)",
    )
    f.add_argument("--category-id", type=int, default=None, help="Kategorie-ID (numerisch)")
    f.add_argument(
        "--only-active", action="store_true",
        help="Nur aktive (laufende, nicht abgelaufene) Deals",
    )
    f.add_argument(
        "--only-with-code", action="store_true",
        help="Nur Deals mit Gutscheincode",
    )
    f.add_argument(
        "--include-expired", action="store_true",
        help="Abgelaufene Deals einschließen (Default: ausgeblendet)",
    )
    f.add_argument(
        "--min-temperature", type=float, default=None,
        help="Nur Deals mit Temperatur >= N (Hotness)",
    )
    f.add_argument("--limit", type=int, default=20, help="Max. Anzahl Treffer (Default 20)")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mydealz",
        description="mydealz – Agent-CLI für mydealz.de (Suche, Details, lokales Keyword-Watch).",
    )
    p.add_argument("--version", action="version", version=f"mydealz {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="SUBCOMMAND")
    s = sub.add_parser("search", help="Deals/Gutscheine suchen")
    s.add_argument("--json", action="store_true")
    _add_search_filters(s)
    s.set_defaults(func=cmd_search)
    sh = sub.add_parser("show", help="Deal-Details anzeigen")
    sh.add_argument("deal", help="Thread-ID (z.B. 2853300) oder URL")
    sh.add_argument(
        "--render",
        choices=["auto", "playwright"],
        default="auto",
        help="Render-Methode (auto: requests+og:*, playwright: headless)",
    )
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)
    w = sub.add_parser("watch", help="Stichwort beobachten, neue Deals seit letztem Lauf")
    w.add_argument("--json", action="store_true")
    w.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur melden, was neu wäre, State nicht aktualisieren",
    )
    _add_search_filters(w)
    w.set_defaults(func=cmd_watch)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser_ = _build_parser()
    args = parser_.parse_args(argv)
    if not getattr(args, "func", None):
        parser_.print_help(sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())