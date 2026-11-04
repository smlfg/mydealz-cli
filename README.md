mydealz – Agent-CLI für mydealz.de
==================================

## Schnellstart

```bash
pipx install git+https://github.com/smlfg/mydealz-cli
mydealz search airpods --max-price 150
mydealz show 2853300
mydealz watch "switch 2"
mydealz watch "switch 2" --dry-run
```

Der erste Befehl installiert das Tool und legt `mydealz` in den PATH. Die
Suche nimmt das Stichwort positional; `--max-price` begrenzt den Preis.
`show` liest die Detailseite zu einer Thread-ID oder URL. `watch` merkt
sich die gesehenen Treffer lokal: der erste Lauf meldet alle Deals als
neu, der zweite nur das Delta, `--dry-run` zeigt das Delta ohne den State
zu ändern.

Im Terminal ist die Ausgabe lesbar (z.B. `[1] 129,62 € (statt 137,99 €) |
Apple AirPods 5 … | OTTO | 685° | ID 2854689`); mit `--json` oder in einer
Pipe bleibt die vollständige JSON-Ausgabe erhalten (Agenten-Vertrag).

Lesezugriff-Only. Kein Login, keine POSTs, keine Messages. Deshalb gibt es
weder `[j/N]` noch `--confirm`/`--yes`; es existiert keine schreibende
Aktion.

* Deals/Gutscheine nach Stichwort suchen
* Filtern nach Kategorie, Händler, Preis (min/max), Temperatur, nur aktive,
  nur Gutscheine mit Code, Sortieren (neu / heiß / diskutiert / Preis)
* Deal-Details anzeigen (Public-HTML; Detail-Seite ist JS-only – mit Playwright
  nachrüstbar)
* Lokales Keyword-Watch: neue Deals seit letztem Lauf, ohne Login

Im Terminal ist die Ausgabe für Menschen lesbar; in einer Pipe oder mit
`--json` kommt genau ein JSON-Objekt pro Aufruf – ideal für LLM-Agenten.

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

    mydealz search kindle --order newest --limit 5

Nur Amazon-Deals unter 50 €, sortiert nach heiß:

    mydealz search --merchant amazon --max-price 50 --order hot

Nur Kategorie Elektronik, nur aktive, mit Gutscheincode:

    mydealz search --category elektronik --only-active --only-with-code

Preisspanne 200–500 € inkl. Händler-ID und Kategorie-ID:

    mydealz search monitor --min-price 200 --max-price 500 \
        --merchant-id 77 --category-id 43

Gutscheine (Vouchers), niedrigster Preis zuerst:

    mydealz search --type coupon --order price-low --limit 10

Detail zu einer Thread-ID:

    mydealz show 2853300
    mydealz show https://www.mydealz.de/deals/...-2853300

Detail mit Playwright-Rendering (braucht `pip install ".[playwright]"`):

    mydealz show 2853300 --render playwright

Lokales Watch (neue Deals seit letztem Lauf):

    mydealz watch kindle --order newest --limit 50
    # später erneut aufrufen → es kommen nur neue Thread-IDs

    mydealz watch kindle --dry-run   # State nicht aktualisieren

JSON-Form
---------

Mit `--json` oder wenn stdout kein TTY ist, gibt jeder Aufruf genau ein
JSON-Objekt auf stdout aus; Fehler gehen auf stderr (ebenfalls JSON, mit
`"error"`). Im Terminal bleibt die Ausgabe lesbar. Beispiel `search`:

    {
      "quelle": "https://www.mydealz.de",
      "url": "https://www.mydealz.de/search?q=kindle&hide-expired=1",
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
    130 Abbruch (Strg+C/EOF)

Umgebung
--------

    MYDEALZ_BASE_URL       Basis-URL, Default https://www.mydealz.de
                           (für Fake-Server-Tests)
    MDZ_MIN_INTERVAL_MS    Mindestabstand zwischen Requests, Default 1000
    XDG_CONFIG_HOME        Basis für den Watch-State
    MYDEALZ_WATCH_STATE    vollständiger Pfad zur Watch-State-Datei

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
    --category-id N             direkte Kategorie-ID (clientseitig; mydealz ignoriert group-id in /search)
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
Akzeptanztests laufen das CLI als Subprozess mit Network-Sandbox
(`tests/harness/sitecustomize.py`); Verbindungen zu
echten Hosts werden blockiert.

Test in einem frischen venv (CI-Setup):

    python -m venv .venv
    .venv/bin/pip install .
    .venv/bin/pip install pytest
    .venv/bin/pytest -q

Sicherheit / Privatsphäre
-------------------------

* Keine personenbezogenen Daten werden erfunden oder im Repo abgelegt.
* Sessions gibt es nicht – das Tool hat keinen Login.
* Kein Tracking, keine externen Skripte außer den `requests`-Calls gegen
  mydealz.de mit ehrlichem User-Agent.
* Lokale Watch-State-Datei wird mit Modus `0600` geschrieben
  (`$XDG_CONFIG_HOME/mydealz-cli/watch.json`).

Lizenz
------

MIT © 2026 smlfg
