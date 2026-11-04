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


def _argv_wants_json() -> bool:
    """True, wenn --json explizit auf der Kommandozeile steht."""
    return "--json" in sys.argv


def _stdout_is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _stderr_is_tty() -> bool:
    try:
        return sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _human_out() -> bool:
    """Lesbare Ausgabe nur an einem Terminal und ohne --json."""
    return _stdout_is_tty() and not _argv_wants_json()


def _human_err() -> bool:
    """Lesbare Fehler nur an einem Terminal und ohne --json."""
    return _stderr_is_tty() and not _argv_wants_json()


def _emit(payload: Any, as_json: bool) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _err(msg: str, *, code: int, **extra: Any) -> NoReturn:
    if _human_err():
        sys.stderr.write(f"mydealz: Fehler: {msg}\n")
        sys.exit(code)
    payload = {"error": msg, **extra}
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(code)


class _CliArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        if _human_err():
            # Terminal: normale argparse-Usage statt JSON.
            super().error(message)
        _err(message, code=1)


# ---------- menschliche (lesbare) Ausgabe ----------

def _should_be_human(json_flag: bool) -> bool:
    """Lesbar nur am Terminal und ohne --json; Piped bleibt JSON."""
    return not json_flag and _stdout_is_tty()


def _fmt_eur(v: Any) -> Optional[str]:
    if v is None:
        return None
    if v == 0:
        return "Gratis"
    s = f"{v:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return s + " €"


def _fmt_temp(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        return f"{int(round(float(v)))}°"
    except (TypeError, ValueError):
        return None


def _haendler_kurz(i: dict) -> str:
    h = i.get("haendler") or {}
    return (
        h.get("name")
        or h.get("slug")
        or h.get("domain")
        or "—"
    )


def _deal_line(i: dict, idx: int) -> str:
    head = f"[{idx}]"
    preis = _fmt_eur(i.get("preis_eur"))
    if preis:
        if i.get("vorher_eur"):
            head += f" {preis} (statt {_fmt_eur(i['vorher_eur'])})"
        else:
            head += f" {preis}"
    parts = [head, i.get("titel") or "(ohne Titel)", _haendler_kurz(i)]
    temp = _fmt_temp(i.get("temperatur"))
    if temp:
        parts.append(temp)
    if i.get("gutschein_code"):
        parts.append(f"Code {i['gutschein_code']}")
    parts.append(f"ID {i.get('id')}")
    return " | ".join(parts)


def _print_search_human(payload: dict) -> None:
    sys.stdout.write(f"{payload['anzahl']} Treffer · {payload['url']}\n")
    for idx, deal in enumerate(payload["deals"], start=1):
        sys.stdout.write(f" {_deal_line(deal, idx)}\n")
    if payload.get("hinweis"):
        sys.stdout.write(f"Hinweis: {payload['hinweis']}\n")
    sys.stdout.flush()


def _print_show_human(deal: dict) -> None:
    sys.stdout.write(f"{deal.get('titel') or '(ohne Titel)'}\n")
    rows: list[tuple[str, str]] = []
    preis = _fmt_eur(deal.get("preis_eur"))
    if preis:
        if deal.get("vorher_eur"):
            preis += f" (statt {_fmt_eur(deal['vorher_eur'])})"
        rows.append(("Preis", preis))
    if deal.get("id"):
        rows.append(("ID", str(deal["id"])))
    if deal.get("url"):
        rows.append(("Deal-URL", str(deal["url"])))
    for key, label in (("beschreibung_text", "Beschreibung"), ("hinweis", "Hinweis")):
        if deal.get(key):
            rows.append((label, str(deal[key])))
    for label, value in rows:
        sys.stdout.write(f"{label}: {value}\n")
    sys.stdout.flush()


def _print_watch_human(payload: dict) -> None:
    n = payload["anzahl_neu"]
    filt = payload.get("filter") or {}
    q = filt.get("q") or "(ohne Stichwort)"
    sys.stdout.write(
        f"{n} neue Deal(s) für {q!r} "
        f"(gemerkt: {payload['anzahl_aktuell']})\n"
    )
    for idx, deal in enumerate(payload["neue_deals"], start=1):
        sys.stdout.write(f" {_deal_line(deal, idx)}\n")
    if payload.get("hinweis"):
        sys.stdout.write(f"Hinweis: {payload['hinweis']}\n")
    if payload.get("state_datei"):
        sys.stdout.write(f"State-Datei: {payload['state_datei']}\n")
    sys.stdout.flush()


# ---------- Filter / gemeinsame Logik ----------

def _apply_filters(
    items: list[dict],
    *,
    haendler: Optional[str],
    kategorie_id: Optional[int] = None,
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
    if kategorie_id is not None:
        out = [
            i for i in out
            if (i.get("kategorie") or {}).get("id") == kategorie_id
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

def _resolve_query(args: argparse.Namespace) -> None:
    """STICHWORT-Positional als Kurzform für --query (Flag gewinnt)."""
    pos = getattr(args, "stichwort", None)
    if pos and not args.q:
        args.q = " ".join(pos) if isinstance(pos, list) else pos


def cmd_search(args: argparse.Namespace) -> int:
    _resolve_query(args)
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

    # Slug-Filter (Händler/Kategorie) und --category-id wirken lokal;
    # mydealz ignoriert group-id in der Such-URL.
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
        _err(
            f"Netzwerkfehler beim Laden der Suche: {e}. "
            "Nächster Schritt: Internetverbindung prüfen oder später erneut versuchen.",
            code=3,
            url=url,
        )
    if r.status >= 400:
        _err(
            f"HTTP {r.status} beim Laden der Suche. "
            "Nächster Schritt: Filter prüfen oder später erneut versuchen.",
            code=3,
            status=r.status,
            url=url,
        )
    try:
        # großzügig parsen, damit Client-Filter nach dem Filtern noch Treffer liefern
        needs_local_filter = (
            (merchant_obj and not args.merchant_id)
            or (category_obj and not args.category_id)
            or args.category_id is not None
        )
        parse_limit = max(args.limit or 20, 100 if needs_local_filter else 50)
        items = parser.parse_search(r.text, limit=parse_limit)
    except ParseError as e:
        _err(
            f"Parse-Fehler: {e}. "
            "Nächster Schritt: mydealz search erneut versuchen oder Markup-Änderung melden.",
            code=4,
            url=url,
        )
    items = _apply_filters(
        items,
        haendler=(merchant_obj.get("name") if merchant_obj else None),
        kategorie_id=args.category_id,
        min_preis=args.min_price,
        max_preis=args.max_price,
        min_temperatur=args.min_temperature,
        nur_aktiv=args.only_active,
        nur_mit_code=args.only_with_code,
    )
    if args.limit:
        items = items[: args.limit]
    slug_filter = (merchant_obj or category_obj) and not (
        args.merchant_id or args.category_id
    )
    hinweis = None
    if slug_filter:
        hinweis = (
            "Händler-/Kategorie-Filter werden lokal auf den "
            "Server-Treffern angewendet, da mydealz' numerische IDs "
            "instabil sind."
        )
    elif args.category_id is not None:
        hinweis = (
            "Kategorie-ID-Filter wird lokal auf den Server-Treffern "
            "angewendet; mydealz ignoriert group-id in der Such-URL."
        )
    payload = {
        "quelle": url_builder.base_url(),
        "url": url,
        "filter": _build_filters_dict(args),
        "hinweis": hinweis,
        "anzahl": len(items),
        "deals": items,
    }
    if _should_be_human(args.json):
        _print_search_human(payload)
    else:
        _emit(payload, args.json)
    return 0


# ---------- show ----------

def _explicit_deal_url(raw: str) -> Optional[str]:
    """Liefert eine vom Nutzer angegebene URL unverändert zurück."""
    s = (raw or "").strip()
    if not s or s.isdigit():
        return None
    if "://" in s:
        return s
    if s.startswith("/"):
        return url_builder.base_url() + s
    return None


def cmd_show(args: argparse.Namespace) -> int:
    try:
        tid = parser.normalize_thread_id(args.deal)
    except ValueError as e:
        _err(str(e), code=1)
    explicit_url = _explicit_deal_url(args.deal)
    url = explicit_url or url_builder.deal_url(tid)
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
        if _should_be_human(args.json):
            _print_show_human(ang)
        else:
            _emit({"quelle": url_builder.base_url(), "deal": ang}, args.json)
        return 0
    # Default: requests, og:* Fallback
    http = HttpClient()
    try:
        r = http.get(url)
    except HTTPError as e:
        _err(
            f"Netzwerkfehler beim Laden des Deals: {e}. "
            "Nächster Schritt: Internetverbindung prüfen oder später erneut versuchen.",
            code=3,
            url=url,
        )
    # mydealz liefert bei /deals/<ID> ohne Slug inzwischen HTTP 410.
    # Die ID-Route /share-deal/<ID> leitet auf die kanonische URL weiter.
    if explicit_url is None and r.status in (404, 410):
        try:
            alt = http.get(url_builder.share_url(tid))
        except HTTPError:
            alt = None
        if alt is not None and alt.status < 400:
            r = alt
            url = url_builder.share_url(tid)
    if r.status >= 400:
        _err(
            f"HTTP {r.status} beim Laden des Deals. "
            "Nächster Schritt: ID/URL prüfen oder den Deal per search suchen.",
            code=3,
            status=r.status,
            url=url,
        )
    try:
        ang = parser.parse_detail_from_html(r.text, tid)
    except ParseError as e:
        _err(
            f"Parse-Fehler: {e} "
            "Nächster Schritt: mydealz search <stichwort> nutzen oder "
            "Playwright installieren (--render playwright).",
            code=4,
            url=url,
        )
    if not ang.get("url"):
        ang["url"] = r.url
    if _should_be_human(args.json):
        _print_show_human(ang)
    else:
        _emit({"quelle": url_builder.base_url(), "deal": ang}, args.json)
    return 0


# ---------- watch ----------

def cmd_watch(args: argparse.Namespace) -> int:
    _resolve_query(args)
    # Pflicht: --query (oder --q)
    if not args.q:
        _err(
            "Stichwort fehlt. Nutzbar als: mydealz watch \"switch 2\" "
            "oder mydealz watch --query \"switch 2\".",
            code=1,
        )
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
        _err(
            f"Netzwerkfehler beim Laden der Suche: {e}. "
            "Nächster Schritt: Internetverbindung prüfen oder später erneut versuchen.",
            code=3,
            url=url,
        )
    if r.status >= 400:
        _err(
            f"HTTP {r.status} beim Laden der Suche. "
            "Nächster Schritt: Filter prüfen oder später erneut versuchen.",
            code=3,
            status=r.status,
            url=url,
        )
    try:
        parse_limit = max(args.limit or 50, 100)
        items = parser.parse_search(r.text, limit=parse_limit)
    except ParseError as e:
        _err(
            f"Parse-Fehler: {e}. "
            "Nächster Schritt: mydealz watch erneut versuchen oder Markup-Änderung melden.",
            code=4,
            url=url,
        )
    items = _apply_filters(
        items,
        haendler=(merchant_obj.get("name") if merchant_obj else None),
        kategorie_id=args.category_id,
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
    if args.dry_run:
        state_path_written = state_path
        hinweis = "Dry-Run: State wurde nicht aktualisiert."
    else:
        watch.update_state(state, query=args.q, ids=current_ids, extra_filters=filters)
        state_path_written = watch.save_state(state, state_path)
        hinweis = None
    payload = {
        "quelle": url_builder.base_url(),
        "url": url,
        "filter": filters,
        "hinweis": hinweis,
        "anzahl_neu": len(new_items),
        "anzahl_aktuell": len(current_ids),
        "neue_deals": new_items,
        "state_datei": state_path_written,
    }
    if _should_be_human(args.json):
        _print_watch_human(payload)
        return 0
    _emit(payload, args.json)
    return 0


# ---------- Argparse ----------

def _add_search_filters(s: argparse.ArgumentParser) -> None:
    s.add_argument(
        "stichwort",
        nargs="*",
        metavar="STICHWORT",
        default=None,
        help="Suchbegriff (Kurzform für --query), z.B. mydealz search airpods",
    )
    f = s.add_argument_group("Such-Filter")
    f.add_argument("--query", dest="q", default=None,
                   help="Stichwort (alternativ: STICHWORT direkt angeben)")
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


def _build_parser() -> _CliArgumentParser:
    p = _CliArgumentParser(
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
    try:
        args = parser_.parse_args(argv)
    except (KeyboardInterrupt, EOFError):
        if _human_err():
            sys.stderr.write("\nAbgebrochen.\n")
            return 130
        _err("Abgebrochen (KeyboardInterrupt/EOF)", code=130)
    # Kein Subbefehl:
    if not getattr(args, "func", None):
        if _human_err():
            parser_.print_usage(sys.stderr)
            sys.stderr.write(
                "mydealz: Fehler: Kein Subbefehl angegeben. "
                "Beispiele: mydealz search airpods | mydealz show <id> "
                "| mydealz watch \"switch 2\"\n"
            )
            return 2
        _err("Kein Subbefehl angegeben (search, show, watch).", code=1)
    try:
        return args.func(args)
    except (KeyboardInterrupt, EOFError):
        if _human_err():
            sys.stderr.write("\nAbgebrochen.\n")
            return 130
        _err("Abgebrochen (KeyboardInterrupt/EOF)", code=130)
    except ValueError as e:
        _err(str(e), code=1)
    except Exception as e:  # noqa: BLE001 – nie Tracebacks nach außen
        _err(
            f"Unerwarteter Fehler: {e}. "
            "Nächster Schritt: Aufruf mit --help prüfen oder Fehler melden.",
            code=3,
        )


if __name__ == "__main__":
    sys.exit(main())