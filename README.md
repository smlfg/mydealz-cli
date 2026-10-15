mydealz – Agent-CLI für mydealz.de
==================================

Lesezugriff-Only. Kein Login, keine POSTs, keine Messages.

* Deals/Gutscheine nach Stichwort suchen
* Filtern nach Kategorie, Händler, Preis (min/max), Temperatur, nur aktive,
  nur Gutscheine mit Code, Sortieren (neu / heiß / diskutiert / Preis)
* Deal-Details anzeigen (Public-HTML; Detail-Seite ist JS-only – mit Playwright
  nachrüstbar)
* Lokales Keyword-Watch: neue Deals seit letztem Lauf, ohne Login

Die Ausgabe ist JSON (pretty-printed), eine Zeile pro Aufruf – ideal für
LLM-Agenten.

Installation
------------

    python -m venv .venv
    source .venv/bin/activate
    pip install .

    # optional, für gerenderte Deal-Details:
    pip install ".[playwright]"
    playwright install chromium

Konservativer User-Agent (`mydealz-cli/0.1.0 (+Repo-URL)`) und
Default-Rate-Limit 1 Request/s (konfigurierbar via
`MDZ_MIN_INTERVAL_MS`).

CLI
---

    mydealz --version
    mydealz --help

Subbefehle:

    search   Deals/Gutscheine suchen
    show     Deal-Details anzeigen (Thread-ID oder URL)
    watch    Stichwort beobachten – neue Deals seit letztem Lauf

Beispiele
---------

Stichwort suchen, 5 neueste:

    mydealz search --query "kindle" --order newest --limit 5

Nur Amazon-Deals unter 50 €, sortiert nach heiß:

    mydealz search --merchant amazon --max-price 50 --order hot

Nur Kategorie Elektronik, nur aktive, mit Gutscheincode:

    mydealz search --category elektronik --only-active --only-with-code

Preisspanne 200–500 € inkl. Händler-ID und Kategorie-ID:

    mydealz search --query "monitor" --min-price 200 --max-price 500 \
        --merchant-id 77 --category-id 43

Gutscheine (Vouchers), niedrigster Preis zuerst:

    mydealz search --type coupon --order price-low --limit 10

Detail zu einer Thread-ID:

    mydealz show 2853300
    mydealz show https://www.mydealz.de/deals/...-2853300

Detail mit Playwright-Rendering (braucht `pip install ".[playwright]"`):

    mydealz show 2853300 --render playwright

Lokales Watch (neue Deals seit letztem Lauf):

    mydealz watch --query "kindle" --order newest --limit 50
    # später erneut aufrufen → es kommen nur neue Thread-IDs

    mydealz watch --query "kindle" --dry-run   # State nicht aktualisieren

JSON-Form
---------

Jeder Aufruf gibt genau ein JSON-Objekt auf stdout aus, Fehler auf stderr
(ebenfalls JSON, mit `"error"`). Beispiel `search`:

    {
      "quelle": "https://www.mydealz.de",
      "url": "https://www.mydealz.de/?q=kindle&hide-expired=1",
      "filter": { "q": "kindle", "order": "newest", ... },
      "hinweis": null,
      "anzahl": 12,
      "deals": [
        {
          "id": "2853300",
          "url": "https://www.mydealz.de/deals/...-2853300",
          "titel": "...",
          "haendler": { "name": "Amazon", "slug": "amazon-de", "id": 3, ... },
          "kategorie": { "name": "Kultur & Freizeit", "slug": "...", "id": ... },
          "preis_eur": 0.0,
          "vorher_eur": 9.99,
          "ersparnis_eur": 9.99,
          "ersparnis_prozent": 100.0,
          "gutschein_code": "LESEN15",
          "gutschein_versteckt": false,
          "temperatur": 624.0,
          "temperatur_level": "Hot2",
          "ist_heiss": true,
          "ist_aktiv": true,
          "kommentare": 137,
          "veroeffentlicht_am": "2026-10-13T07:14:00Z",
          "ersteller": { "name": "...", "id": ... }
        }
      ]
    }

`watch` liefert zusätzlich `neue_deals`, `anzahl_neu`, `anzahl_aktuell`,
`state_datei` (Pfad, Modus 0600).

Exit-Codes
----------

    0  Erfolg
    1  Falsche Eingabe (unbekannter Händler/Kategorie, kaputte ID, …)
    2  Voraussetzung fehlt (z. B. Playwright nicht installiert)
    3  HTTP-/Netzwerkfehler
    4  Parse-Fehler (unerwartetes Markup)

Filter
------

Such-Filter (alle optional, kombinierbar):

    --query / -q TEXT          Volltext-Stichwort
    --type {deal,coupon,voucher,freebie,groupdeal}
    --order {newest,hot,trending,discussed,price-low,price-high}
    --page N                    Pagination (Default 1)
    --min-price / --max-price   Preisspanne in €
    --merchant KURZNAME         z. B. amazon, ebay, mediamarkt
    --merchant-id N             direkte mydealz-Händler-ID
    --category SLUG             z. B. elektronik, computer, games
    --category-id N             direkte Kategorie-ID
    --only-active               nur laufende, nicht abgelaufene Deals
    --only-with-code            nur Deals mit Gutscheincode
    --include-expired           abgelaufene Deals einschließen
    --min-temperature N         nur Deals mit Temperatur >= N (Hotness)
    --limit N                   max. Anzahl Treffer (Default 20)

Hinweise zum HTML-Parsing
-------------------------

Die Startseite rendert Threads serverseitig in
`<article id="thread_<ID>">`-Containern mit eingebetteten `data-vue3`-JSONs
(`ThreadMainListItemNormalizer`). Wir parsen ausschließlich über diese
stabile Quelle, nicht über CSS-Klassen der Vue3-Karten.

Die Detail-Seite `/deals/<slug>-<id>` ist JS-only. Ohne Playwright liefert
`show` nur `<title>` und `og:*`-Metadaten und einen `hinweis`-Hinweis
im JSON; das ist Absicht, nicht ein Fehler.

Tests
-----

    pip install ".[dev]"
    pytest -q

Die Tests sind netz-frei: HTML-Fixtures unter `tests/fixtures/`. Die
Fixtures sind gekürzt und synthetisch: Nur das Markup, das der Parser liest
(`article#thread_<id>`, `data-vue3`-JSON, `.thread-title a`), echte
Usernamen sind durch `user_1`, `user_2`, … ersetzt, Gutscheincodes durch
`CODE_1`, …. Die
Akzeptanztests laufen das CLI als Subprozess mit Network-Sandbox
(`agent-learnings/tests/harness/sitecustomize.py`); Verbindungen zu
echten Hosts werden blockiert.

Test in einem frischen venv (CI-Setup):

    python -m venv /tmp/mdz-venv
    /tmp/mdz-venv/bin/pip install .
    /tmp/mdz-venv/bin/pip install pytest
    /tmp/mdz-venv/bin/pytest -q

Sicherheit / Privatsphäre
-------------------------

* Keine personenbezogenen Daten werden erfunden oder im Repo abgelegt.
  `python3 scripts/pii_guard.py` prüft alle getrackten Dateien auf
  E-Mail-Adressen, Matrikelnummern und mydealz-Usernamen, die nicht in
  `.pii-allowlist` stehen; `pytest` führt den Guard mit aus. Neue Fixtures
  nur mit Platzhaltern (`user_N`) einchecken.
* Sessions gibt es nicht – das Tool hat keinen Login.
* Kein Tracking, keine externen Skripte außer den `requests`-Calls gegen
  mydealz.de mit ehrlichem User-Agent.
* Lokale Watch-State-Datei wird mit Modus `0600` geschrieben
  (`$XDG_CONFIG_HOME/mydealz-cli/watch.json`).

Lizenz
------

MIT © 2026 smlfg
