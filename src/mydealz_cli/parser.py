"""HTML-Parser für mydealz.de.

Die Startseite rendert Threads serverseitig in ``<article
id="thread_<ID>">``-Containern. Jeder Artikel enthält die
strukturierten Daten als JSON in ``data-vue3``-Attributen
(``ThreadMainListItemNormalizer``). Wir parsen ausschließlich
über diese stabile Quelle – nicht über CSS-Klassen der gerenderten
Karten, die Vue3 clientseitig austauscht.

Die Detailseite ``/deals/<slug>-<id>`` ist JS-only. Optional kann
ein Playwright-Headless-Browser nachgerüstet werden; in der
Default-Installation liefert ``parse_detail_from_html`` einen
einfachen Stub, und das CLI meldet einen klaren Hinweis.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional

from bs4 import BeautifulSoup

from .http_client import ParseError

_BASE = "https://www.mydealz.de"
_NORMALIZER_RE = re.compile(
    r'\{"name":"ThreadMainListItemNormalizer","props":\{"thread":(\{.*?\})\}\}'
)


def _text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ") or "").strip()


def _eur_to_float(s: Any) -> Optional[float]:
    """Akzeptiert ``12,99`` oder ``12.99`` oder ``12``."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    raw = str(s).strip().replace("€", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _timestamp_to_iso(ts: Any) -> Optional[str]:
    """Unix-Sekunden → ISO-8601 (UTC)."""
    if ts is None or ts == 0:
        return None
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _temp_level_to_threshold(level: Any) -> Optional[float]:
    """Liefert eine grobe Untergrenze in °C für ein mydealz-Level.

    mydealz.de kennt Hot1/Hot2/Hot3/Cold/Lukewarm. Diese Zuordnung
    ist eine Annäherung, kein amtlicher Wert.
    """
    if not level:
        return None
    table = {
        "Hot3": 400.0,
        "Hot2": 200.0,
        "Hot1": 50.0,
        "Lukewarm": 0.0,
        "Cold": -10.0,
    }
    return table.get(str(level))


def _coerce_thread_dict(t: dict) -> dict:
    """Normalisiert ein Thread-Dict aus ``data-vue3``."""
    merchant = t.get("merchant") or {}
    main_group = t.get("mainGroup") or {}
    user = t.get("user") or {}
    price = _eur_to_float(t.get("price"))
    next_best = _eur_to_float(t.get("nextBestPrice"))
    return {
        "id": str(t.get("threadId")),
        "url": t.get("shareableLink") or f"{_BASE}/deals/{t.get('threadId')}",
        "canonical_url": t.get("shareableLink") or f"{_BASE}/deals/{t.get('threadId')}",
        "titel": (t.get("title") or "").strip() or None,
        "haendler": {
            "name": merchant.get("merchantName"),
            "slug": merchant.get("merchantUrlName"),
            "id": merchant.get("merchantId"),
            "domain": t.get("linkHost") or None,
            "externer_link": t.get("link") or None,
        },
        "kategorie": {
            "name": main_group.get("threadGroupName"),
            "slug": main_group.get("threadGroupUrlName"),
            "id": main_group.get("threadGroupId"),
        },
        "preis_eur": price,
        "vorher_eur": next_best,
        "ersparnis_eur": (
            round(next_best - price, 2) if (price is not None and next_best is not None) else None
        ),
        "ersparnis_prozent": (
            round((next_best - price) / next_best * 100, 1)
            if (price is not None and next_best not in (None, 0))
            else None
        ),
        "gutschein_code": (t.get("voucherCode") or "").strip() or None,
        "gutschein_versteckt": bool(t.get("isVoucherCodeHidden")),
        "temperatur": _eur_to_float(t.get("temperature")),
        "temperatur_level": t.get("temperatureLevel"),
        "ist_heiss": bool(t.get("isHot")),
        "ist_superheiss": bool(t.get("isSuperHot")),
        "kommentare": int(t.get("commentCount") or 0),
        "veroeffentlicht_am": _timestamp_to_iso(t.get("publishedAt")),
        "aktualisiert_am": _timestamp_to_iso(t.get("updatedAt")),
        "ist_aktiv": (
            t.get("status") == "Activated"
            and not t.get("isExpired")
            and not t.get("deletedAt")
        ),
        "ist_bald_endigend": bool(t.get("isExpiringSoon")),
        "ist_exklusiv": bool(t.get("isExclusive")),
        "ist_top_deal": bool(t.get("isTopDeal") or t.get("isCategoryTopDeal")),
        "ist_community_favorite": bool(t.get("isCommunityFavorite")),
        "ist_nsfg": bool(t.get("nsfw")),
        "ersteller": {
            "name": user.get("username"),
            "id": user.get("userId"),
            "titel": user.get("title"),
        },
    }


def _extract_thread_from_vue3(raw: str) -> Optional[dict]:
    """Sucht in einem ``data-vue3``-String nach dem Thread-JSON."""
    m = _NORMALIZER_RE.search(raw)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def parse_search(
    html: str,
    *,
    limit: int = 20,
) -> list[dict]:
    """Parst die Liste der Deals aus dem SSR-HTML der Startseite."""
    soup = BeautifulSoup(html, "lxml")
    articles = soup.find_all("article", id=re.compile(r"^thread_\d+"))
    if not articles:
        # Eventuell hat mydealz das Markup geändert – das ist hart.
        # Wir geben eine leere Liste zurück und der Aufrufer entscheidet.
        return []
    results: list[dict] = []
    for art in articles:
        thread_id = (art.get("id") or "").replace("thread_", "")
        if not thread_id:
            continue
        normalizer = art.find(attrs={"data-vue3": re.compile(r"ThreadMainListItemNormalizer")})
        if not normalizer:
            continue
        raw = normalizer.get("data-vue3", "")
        t = _extract_thread_from_vue3(raw)
        if not t:
            continue
        # Bevorzuge die im HTML verlinkte Titel-URL (Slug-Variante)
        title_link = art.select_one(".thread-title a")
        if title_link and title_link.get("href"):
            d = _coerce_thread_dict(t)
            d["url"] = title_link["href"]
            results.append(d)
        else:
            results.append(_coerce_thread_dict(t))
        if len(results) >= limit:
            break
    return results


def parse_search_with_meta(html: str, *, limit: int = 20) -> dict:
    """Wie ``parse_search``, gibt aber zusätzlich eine Meta-Sektion zurück."""
    items = parse_search(html, limit=limit)
    return {
        "items": items,
        "count": len(items),
    }


def _extract_initial_state_json(html: str) -> Optional[dict]:
    """Liest ``window.__INITIAL_STATE__`` aus eingebettetem Script."""
    marker = "window.__INITIAL_STATE__"
    idx = html.find(marker)
    if idx < 0:
        return None
    start = html.find("{", idx)
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    quote = ""
    for i, ch in enumerate(html[start:], start):
        if in_str:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_thread_detail_dict(thread: dict, thread_id: str) -> dict:
    """Normalisiert ``threadDetail`` aus ``__INITIAL_STATE__``."""
    if not thread or str(thread.get("threadId")) != str(thread_id):
        raise ParseError(f"threadDetail für Thread {thread_id} nicht gefunden.")
    t = dict(thread)
    if not t.get("mainGroup") and t.get("groups"):
        default = next((g for g in t["groups"] if g.get("isDefault")), t["groups"][0])
        t["mainGroup"] = default
    ang = _coerce_thread_dict(t)
    desc = t.get("descriptionPurified") or t.get("description")
    if desc:
        if isinstance(desc, str) and "<" in desc:
            ang["beschreibung_text"] = _text(BeautifulSoup(desc, "lxml"))
        else:
            ang["beschreibung_text"] = str(desc).strip() or None
    return ang


def parse_detail_from_playwright_html(html: str, thread_id: str) -> dict:
    """Parst eine (gerenderte) Detail-Seite über ``__INITIAL_STATE__.threadDetail``."""
    state = _extract_initial_state_json(html)
    if not state:
        raise ParseError(
            "Kein window.__INITIAL_STATE__ auf der Detail-Seite gefunden. "
            "Seite evtl. nicht vollständig gerendert."
        )
    return parse_thread_detail_dict(state.get("threadDetail") or {}, thread_id)


def parse_detail_from_html(html: str, thread_id: str) -> dict:
    """Versucht, eine Detail-Seite zu parsen.

    Da ``/deals/<slug>-<id>`` JS-rendered ist, liefern wir einen
    Stub mit den ``<meta>``- und ``<title>``-Informationen, falls
    vorhanden. Andernfalls wird ``ParseError`` ausgelöst, sobald
    Playwright installiert und ein echtes Rendering verfügbar ist.
    """
    soup = BeautifulSoup(html, "lxml")
    canonical = soup.find("link", rel="canonical")
    url = canonical.get("href") if canonical and canonical.get("href") else None
    title_node = soup.find("meta", attrs={"property": "og:title"})
    title = title_node.get("content") if title_node else None
    if not title:
        t = soup.find("title")
        title = t.get_text(" ", strip=True) if t else None
    desc_node = soup.find("meta", attrs={"property": "og:description"})
    description = desc_node.get("content") if desc_node else None
    if not url and not title:
        raise ParseError(
            "Detail-Seite nicht parsebar ohne JS-Rendering. "
            "Installiere 'playwright' und nutze --render=playwright, "
            "oder verwende 'search' für die Listenansicht."
        )
    return {
        "id": thread_id,
        "url": url,
        "titel": title,
        "beschreibung_text": description,
        "hinweis": (
            "Diese Seite ist JS-only. Beschreibung ist aus <meta og:*>/<title> "
            "extrahiert – für Inhalt/Temperatur/Kommentare bitte Playwright "
            "verwenden oder 'search' benutzen."
        ),
    }


def normalize_thread_id(s: str) -> str:
    """Akzeptiert ``2853300``, ``/deals/...-2853300`` oder URL."""
    s = (s or "").strip()
    if not s:
        raise ValueError("leere Thread-ID")
    if s.isdigit():
        return s
    # URL oder Pfad
    if "://" in s:
        from urllib.parse import urlparse
        path = urlparse(s).path
    else:
        path = s
    # Letzte Zahl im Pfad
    m = re.search(r"(\d{4,})", path or "")
    if m:
        return m.group(1)
    raise ValueError(f"konnte keine Thread-ID aus {s!r} ableiten")