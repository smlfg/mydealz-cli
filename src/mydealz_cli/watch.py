"""Lokales Keyword-Watch: speichert gesehene Thread-IDs und meldet neue.

Anders als das offizielle mydealz-Alert-System (``/alerts`` verlangt
Login) ist dieser Watch rein lokal: ein ``watch``-Aufruf schreibt die
IDs der Treffer in eine State-Datei. Der nächste ``watch``-Aufruf
vergleicht gegen diesen Stand und liefert nur die Deltas.

Konfiguration über ``MYDEALZ_WATCH_STATE`` (Default
``$XDG_CONFIG_HOME/mydealz-cli/watch.json``). Datei wird mit Modus
0600 geschrieben, ähnlich wie bei wg-gesucht-cli.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional


def state_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "mydealz-cli", "watch.json")


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass


def load_state(path: Optional[str] = None) -> dict:
    path = path or state_path()
    if not os.path.exists(path):
        return {"version": 1, "watches": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "watches": {}}
    if not isinstance(data, dict) or data.get("version") != 1:
        return {"version": 1, "watches": {}}
    data.setdefault("watches", {})
    return data


def save_state(state: dict, path: Optional[str] = None) -> str:
    path = path or state_path()
    _ensure_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def diff_for_query(
    state: dict,
    *,
    query: str,
    items: list[dict],
    extra_filters: Optional[dict] = None,
) -> tuple[list[dict], list[str]]:
    """Vergleicht ``items`` mit dem letzten Stand für ``query``.

    Liefert (``neu``, ``ids``) – die neuen Deals und alle aktuellen IDs.
    ``extra_filters`` ist ein freiwilliger Marker, damit ein User
    sehen kann, mit welchen Filtern der Stand gespeichert wurde.
    """
    current_ids = [i["id"] for i in items if i.get("id")]
    key = _query_key(query, extra_filters)
    seen = state["watches"].get(key, {}).get("ids", [])
    new_ids = [i for i in current_ids if i not in seen]
    new_items = [i for i in items if i.get("id") in new_ids]
    return new_items, current_ids


def update_state(
    state: dict,
    *,
    query: str,
    ids: list[str],
    extra_filters: Optional[dict] = None,
) -> None:
    key = _query_key(query, extra_filters)
    state["watches"][key] = {
        "ids": ids,
        "saved_at": int(time.time()),
        "filters": extra_filters or {},
    }


def _query_key(query: str, extra: Optional[dict]) -> str:
    """Baut einen stabilen Schlüssel aus Query + Filtern."""
    if extra:
        # Sortierte, deterministische JSON-Repräsentation
        suffix = json.dumps(extra, sort_keys=True, ensure_ascii=False)
        return f"{query}|{suffix}"
    return query