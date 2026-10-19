"""URL-Bau für mydealz.de-Suchen.

Suchanfragen müssen den Pfad ``/search`` benutzen – die
Startseite ``/`` ignoriert ``q`` (sie ist reine SSR-Startseite
und liefert sonst Apple TV, Rasierer etc.).

Unterstützte Query-Parameter:

* ``q`` – Stichwort (Volltext).
* ``type`` – ``deal`` (Default), ``voucher`` (nur Gutscheine),
  ``coupon`` (US-Name, identisch zu voucher), ``freebie``,
  ``groupdeal``.
* ``order`` – ``newest``, ``hot`` (Standard), ``trending``,
  ``most-discussed``, ``price-low``, ``price-high``.
* ``hide-expired`` – ``1`` / ``0``.
* ``page`` – Pagination, Default 1.
* ``min-price`` / ``max-price`` – in Euro, ganzzahlig.
* ``merchant-id`` – mydealz-Interne Händler-ID.
* ``group-id`` – mydealz-Interne Kategorie-ID.

Hinweis: früher wurde die Startseite (``/``) als Such-URL
verwendet. Das war falsch – mydealz ignoriert dort den
``q``-Parameter und liefert das allgemeine Feed.
"""

from __future__ import annotations

from typing import Iterable, Optional

BASE = "https://www.mydealz.de"


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
    "elektronik": {"slug": "elektronik", "name": "Elektronik"},
    "computer": {"slug": "computer", "name": "Computer"},
    "games": {"slug": "games", "name": "Games"},
    "kultur-freizeit": {"slug": "kultur-freizeit", "name": "Kultur & Freizeit"},
    "haushalt": {"slug": "haushalt", "name": "Haushalt"},
    "mode": {"slug": "mode", "name": "Mode"},
    "beauty": {"slug": "beauty", "name": "Beauty"},
    "sport": {"slug": "sport", "name": "Sport"},
    "auto-moto": {"slug": "auto-moto", "name": "Auto & Motorrad"},
    "reisen": {"slug": "reisen", "name": "Reisen"},
    "finanzen": {"slug": "finanzen", "name": "Finanzen"},
    "wohnen": {"slug": "wohnen", "name": "Wohnen"},
    "lebensmittel": {"slug": "lebensmittel", "name": "Lebensmittel"},
    "handy-telekom": {"slug": "handy-telekom", "name": "Handy & Telekom"},
}


ORDERS: dict[str, str] = {
    "newest": "newest",
    "hot": "hot",
    "trending": "trending",
    "discussed": "most-discussed",
    "price-low": "price-low",
    "price-high": "price-high",
}


DEAL_TYPES: dict[str, str] = {
    "deal": "deal",
    "coupon": "voucher",
    "voucher": "voucher",
    "freebie": "freebie",
    "groupdeal": "groupdeal",
}


def resolve_merchant(name: str) -> Optional[dict]:
    """Liefert Händler-Mapping oder ``None``.

    Akzeptiert den Kurznamen (``"amazon"``) oder die volle URL
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
    if s in CATEGORIES:
        return dict(CATEGORIES[s])
    # URL /group/<slug>
    import re
    m = re.search(r"/group/([a-z0-9-]+)", s)
    if m:
        slug = m.group(1)
        for v in CATEGORIES.values():
            if v["slug"] == slug:
                return {"slug": slug, "name": v["name"]}
        return {"slug": slug, "name": slug}
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
        params.append(("order", _normalize_order(order)))
    if page and page > 1:
        params.append(("page", str(page)))
    if min_price is not None:
        params.append(("min-price", str(int(min_price))))
    if max_price is not None:
        params.append(("max-price", str(int(max_price))))
    if merchant_id is not None:
        params.append(("merchant-id", str(merchant_id)))
    if category_id is not None:
        params.append(("group-id", str(category_id)))
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
    if has_search_path:
        return f"{BASE}/search?{qs}"
    return f"{BASE}/?{qs}" if qs else BASE


def deal_url(thread_id: str) -> str:
    """Baut die kanonische Deal-URL aus einer numerischen Thread-ID."""
    return f"{BASE}/deals/{thread_id}"


def search_url_for(query: str) -> str:
    """Hilfs-URL: nur Stichwort."""
    from urllib.parse import quote_plus
    return f"{BASE}/search?q={quote_plus(query)}"