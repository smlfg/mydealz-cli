"""URL-Bau für mydealz.de-Suchen.

Suchanfragen müssen den Pfad ``/search`` benutzen – die
Startseite ``/`` ignoriert ``q`` (sie ist reine SSR-Startseite
und liefert sonst Apple TV, Rasierer etc.).

Unterstützte Query-Parameter:

* ``q`` – Stichwort (Volltext).
* ``type`` – ``deal`` (Default), ``voucher`` (nur Gutscheine),
  ``coupon`` (US-Name, identisch zu voucher), ``freebie``,
  ``groupdeal``.
* ``sortBy`` – mydealz-Sortierschlüssel (``new``, ``temp``,
  ``discussion``, ``lowest_price``, ``highest_price``). Das früher
  genutzte ``order`` ignoriert der Server.
* ``hide-expired`` – ``1`` / ``0`` (wird zusätzlich clientseitig
  erzwungen, weil der Server den Parameter ignoriert).
* ``page`` – Pagination, Default 1.
* ``min-price`` / ``max-price`` – in Euro, ganzzahlig.
* ``merchant-id`` – mydealz-Interne Händler-ID.

``group-id`` in der Such-URL wird von mydealz ignoriert; Kategorie-IDs
filtert das CLI clientseitig über ``kategorie.id`` in den Treffern.

Hinweis: früher wurde die Startseite (``/``) als Such-URL
verwendet. Das war falsch – mydealz ignoriert dort den
``q``-Parameter und liefert das allgemeine Feed.
"""

from __future__ import annotations

import os
import unicodedata
from typing import Optional
from urllib.parse import urlsplit

BASE = "https://www.mydealz.de"
BASE_URL_ENV = "MYDEALZ_BASE_URL"


def base_url() -> str:
    """Basis-URL aus ``MYDEALZ_BASE_URL`` oder der Standard-Host.

    Nur absolute ``http``/``https``-URLs ohne Query/Fragment sind erlaubt.
    Ein abschließender Schrägstrich wird entfernt, damit beim Bauen kein
    doppelter Slash entsteht.
    """
    raw = (os.environ.get(BASE_URL_ENV) or "").strip()
    if not raw:
        return BASE
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(
            f"Ungültige {BASE_URL_ENV}={raw!r}: erwartet wird eine absolute "
            "http(s)-URL wie https://www.mydealz.de. "
            f"Nächster Schritt: {BASE_URL_ENV} korrigieren oder entfernen."
        )
    if parts.query or parts.fragment:
        raise ValueError(
            f"Ungültige {BASE_URL_ENV}={raw!r}: Query/Fragment sind nicht erlaubt. "
            f"Nächster Schritt: {BASE_URL_ENV} korrigieren oder entfernen."
        )
    return raw.rstrip("/")


# Bekannte mydealz-Händler-Kurznamen → Anzeige-Namen.
# Die numerischen IDs bei mydealz ändern sich, sind themen-spezifisch
# und können nicht zuverlässig hartkodiert werden. Wer einen bestimmten
# Händler filtern will, übergibt entweder dessen Profil-URL
# (``--merchant https://www.mydealz.de/profile/<slug>``) oder die
# numerische ID direkt (``--merchant-id N``). Wir liefern den Namen
# hier nur, damit die Anzeige lesbar bleibt.
MERCHANTS: dict[str, dict] = {
    "amazon": {"slug": "amazon-de", "name": "Amazon"},
    "ebay": {"slug": "ebay-de", "name": "eBay"},
    "mediamarkt": {"slug": "mediamarkt-de", "name": "MediaMarkt"},
    "saturn": {"slug": "saturn-de", "name": "Saturn"},
    "otto": {"slug": "otto-de", "name": "Otto"},
    "lidl": {"slug": "lidl-de", "name": "Lidl"},
    "aldi": {"slug": "aldi-de", "name": "Aldi"},
    "rewe": {"slug": "rewe-de", "name": "Rewe"},
    "dm": {"slug": "dm-de", "name": "dm"},
    "mueller": {"slug": "mueller-de", "name": "Müller"},
    "kaufland": {"slug": "kaufland-de", "name": "Kaufland"},
    "idealo": {"slug": "idealo-de", "name": "idealo"},
    "coolblue": {"slug": "coolblue-de", "name": "Coolblue"},
    "notebooksbilliger": {"slug": "notebooksbilliger-de", "name": "notebooksbilliger"},
    "alternate": {"slug": "alternate-de", "name": "Alternate"},
    "proshop": {"slug": "proshop-de", "name": "Proshop"},
    "thalia": {"slug": "thalia-de", "name": "Thalia"},
}


# Bekannte Kategorie-Slugs (Top-Level). Wie bei Händlern sind die
# numerischen IDs nicht stabil; die Slugs aber schon.
CATEGORIES: dict[str, dict] = {
    "elektronik": {"slug": "elektronik", "name": "Elektronik", "id": 2},
    "computer": {"slug": "computer", "name": "Computer", "id": 34},
    "games": {"slug": "games", "name": "Games"},
    "kultur-freizeit": {"slug": "kultur-freizeit", "name": "Kultur & Freizeit", "id": 1290},
    "haushalt": {"slug": "haushalt", "name": "Haushalt", "id": 8},
    "mode": {"slug": "mode", "name": "Mode", "id": 1},
    "beauty": {"slug": "beauty", "name": "Beauty", "id": 14},
    "sport": {"slug": "sport", "name": "Sport", "id": 132},
    "auto-moto": {"slug": "auto-moto", "name": "Auto & Motorrad"},
    "reisen": {"slug": "reisen", "name": "Reisen", "id": 7},
    "finanzen": {"slug": "finanzen", "name": "Finanzen"},
    "wohnen": {"slug": "wohnen", "name": "Wohnen", "id": 4},
    "lebensmittel": {"slug": "lebensmittel", "name": "Lebensmittel", "id": 118},
    "handy-telekom": {"slug": "handy-telekom", "name": "Handy & Telekom", "id": 1258},
}


# mydealz sortiert über ``sortBy``; die Schlüssel stammen aus der
# Suchseite (``sortBy[].key``). ``order`` wird vom Server ignoriert.
ORDERS: dict[str, str] = {
    "newest": "new",
    "hot": "temp",
    "trending": "temp",
    "discussed": "discussion",
    "price-low": "lowest_price",
    "price-high": "highest_price",
}


DEAL_TYPES: dict[str, str] = {
    "deal": "deal",
    "coupon": "voucher",
    "voucher": "voucher",
    "freebie": "freebie",
    "groupdeal": "groupdeal",
}


def _fold(value: str) -> str:
    """Kleinschreibung + deutsche Umlaute/ß für stabile Vergleiche."""
    s = (value or "").strip().lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(src, dst)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def resolve_merchant(name: str) -> Optional[dict]:
    """Liefert Händler-Mapping oder ``None``.

    Akzeptiert den Kurznamen (``"amazon"``), den Anzeigenamen
    (``"Müller"``) oder die volle URL
    (``https://www.mydealz.de/profile/amazon-de``). Liefert NUR
    ``{slug, name}`` — die numerische ID ist nicht stabil und
    wird vom Aufrufer per ``--merchant-id`` zusätzlich gesetzt.
    """
    s = (name or "").strip().lower()
    if not s:
        return None
    # URL
    if "/" in s:
        import re
        m = re.search(r"/(?:profile|merchant)/([a-z0-9-]+)", s)
        if m:
            slug = m.group(1)
            for v in MERCHANTS.values():
                if v["slug"] == slug:
                    return {"slug": slug, "name": v["name"]}
            return {"slug": slug, "name": slug}
    # Direkter Kurzname
    if s in MERCHANTS:
        return dict(MERCHANTS[s])
    return None


def resolve_category(name: str) -> Optional[dict]:
    s = (name or "").strip().lower()
    if not s:
        return None
    folded = _fold(s)
    if folded in CATEGORIES:
        return dict(CATEGORIES[folded])
    for key, value in CATEGORIES.items():
        if _fold(value["name"]) == folded or _fold(value["slug"]) == folded:
            return dict(value)
    # URL /group/<slug> oder /gruppe/<slug>
    import re
    m = re.search(r"/grupp?e?/([a-z0-9-]+)", s)
    if m:
        slug = m.group(1)
        for v in CATEGORIES.values():
            if v["slug"] == slug:
                return {"slug": slug, "name": v["name"]}
        return {"slug": slug, "name": slug}
    return None


def resolve_category_id(category_id: int) -> Optional[dict]:
    """Liefert die bekannte Kategorie zu einer mydealz-Gruppen-ID."""
    try:
        wanted = int(category_id)
    except (TypeError, ValueError):
        return None
    for value in CATEGORIES.values():
        cid = value.get("id")
        if cid is not None and int(cid) == wanted:
            return dict(value)
    return None


def _normalize_order(value: str) -> str:
    """Akzeptiert sowohl Klarnamen als auch die URL-Variante."""
    v = (value or "").strip().lower()
    return ORDERS.get(v, v)


def _normalize_type(value: str) -> str:
    v = (value or "").strip().lower()
    return DEAL_TYPES.get(v, v)


def build_search_url(
    *,
    query: Optional[str] = None,
    deal_type: Optional[str] = None,
    order: Optional[str] = None,
    page: int = 1,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    merchant_id: Optional[int] = None,
    category_id: Optional[int] = None,
    hide_expired: bool = True,
    only_active: bool = False,
    min_temperature: Optional[float] = None,
) -> str:
    """Baut die URL für eine Suche (``/search``) oder den Hot-Feed (``/``)."""
    params: list[tuple[str, str]] = []
    if query:
        params.append(("q", query))
    if deal_type:
        params.append(("type", _normalize_type(deal_type)))
    if order:
        params.append(("sortBy", _normalize_order(order)))
    if page and page > 1:
        params.append(("page", str(page)))
    if min_price is not None:
        params.append(("min-price", str(int(min_price))))
    if max_price is not None:
        params.append(("max-price", str(int(max_price))))
    if merchant_id is not None:
        params.append(("merchant-id", str(merchant_id)))
    if hide_expired:
        params.append(("hide-expired", "1"))
    if only_active:
        # nur laufende (nicht bald-endende)
        params.append(("hide-upcoming", "1"))
    # min-temperature wird clientseitig angewendet (kein URL-Support).
    from urllib.parse import urlencode
    # Stichwort und Filter (type, order, …) müssen über /search laufen;
    # auf / ignoriert mydealz q sowie type/order/page/Preisfilter.
    has_search_path = bool(query) or bool(deal_type) or bool(order) or (
        page and page > 1
    ) or min_price is not None or max_price is not None or (
        merchant_id is not None
    ) or category_id is not None or only_active
    qs = urlencode(params)
    base = base_url()
    if has_search_path:
        return f"{base}/search?{qs}"
    return f"{base}/?{qs}" if qs else base


def deal_url(thread_id: str) -> str:
    """Baut die kanonische Deal-URL aus einer numerischen Thread-ID."""
    return f"{base_url()}/deals/{thread_id}"


def share_url(thread_id: str) -> str:
    """ID-Route, die per Redirect auf die kanonische Slug-URL führt."""
    return f"{base_url()}/share-deal/{thread_id}"


def search_url_for(query: str) -> str:
    """Hilfs-URL: nur Stichwort."""
    from urllib.parse import quote_plus
    return f"{base_url()}/search?q={quote_plus(query)}"