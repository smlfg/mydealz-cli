# Schnittstelle: mydealz

Vertrag für das Console-Script `mydealz` (Repo `smlfg/mydealz-cli`). Das
Tool ist read-only: es liest öffentliche Seiten und schreibt nur den
lokalen Watch-State. Es gibt keinen Login und keine schreibenden
Website-Aktionen.

## Installation und Aufruf

```bash
pipx install git+https://github.com/smlfg/mydealz-cli
mydealz --help
mydealz --version
```

- Console-Script: `mydealz`
- Python: >= 3.10
- Kein Login, kein `whoami`, kein `logout`, keine Session-Datei.
- Es gibt keine schreibenden Aktionen. Deshalb gibt es weder `[j/N]`
  noch `--confirm`/`--yes`.

## Gemeinsames Ausgabeformat

- Im Terminal (stdout ist ein TTY) und ohne `--json`: lesbare,
  zeilenorientierte Ausgabe für Menschen.
- Mit `--json` oder wenn stdout kein TTY ist (Pipe, Agent): genau ein
  JSON-Objekt auf stdout.
- Fehler gehen auf stderr. Im TTY als lesbare Zeile mit nächstem Schritt,
  sonst als JSON-Objekt mit `"error"`.
- Es werden keine Tracebacks ausgegeben, auch nicht bei Strg+C oder EOF.

## Befehle

### `mydealz search [STICHWORT ...]`

Sucht Deals/Gutscheine. Das Stichwort ist positional; `--query/-q` bleibt
als Alternative erhalten. Mehrere positional Wörter werden mit Leerzeichen
verbunden. Ohne Stichwort wird der allgemeine Feed geladen.

Flags:

| Flag | Bedeutung |
|---|---|
| `--query`, `-q TEXT` | Stichwort (Alternative zu positional) |
| `--type {deal,coupon,voucher,freebie,groupdeal}` | Deal-Typ |
| `--order {newest,hot,trending,discussed,price-low,price-high}` | Sortierung |
| `--page N` | Seitenzahl, Default 1 |
| `--min-price EUR`, `--max-price EUR` | Preisspanne, clientseitig erzwungen |
| `--merchant KURZNAME` | Händler-Kurzname, z. B. `amazon` |
| `--merchant-id N` | mydealz-Händler-ID |
| `--category SLUG` | Kategorie-Slug, z. B. `elektronik` |
| `--category-id N` | Kategorie-ID, clientseitig gefiltert |
| `--only-active` | nur laufende Deals |
| `--only-with-code` | nur Deals mit Gutscheincode |
| `--include-expired` | abgelaufene Deals einschließen |
| `--min-temperature N` | nur Deals ab Temperatur N, clientseitig |
| `--limit N` | max. Treffer, Default 20 |
| `--json` | JSON-Ausgabe erzwingen |

Ausgabe (JSON): `quelle`, `url`, `filter`, `hinweis`, `anzahl`, `deals`.
Jeder Deal enthält u. a. `id`, `url`, `titel`, `haendler`, `kategorie`,
`preis_eur`, `vorher_eur`, `temperatur`, `gutschein_code`, `ist_aktiv`.

### `mydealz show <ID|URL>`

Liest die Detailseite zu einer Thread-ID oder vollständigen Deal-URL.
Positional, keine Pflicht-Option. Ohne Playwright liefert das Tool bewusst
nur `<title>`/`og:*` und setzt `hinweis` auf den JS-only-Hinweis.

Flags:

| Flag | Bedeutung |
|---|---|
| `DEAL` | Thread-ID (z. B. `2853300`) oder Deal-URL |
| `--render {auto,playwright}` | Render-Methode, Default `auto` |
| `--json` | JSON-Ausgabe erzwingen |

Ausgabe (JSON): `quelle`, `deal` mit `id`, `url`, `titel`,
`beschreibung_text`, `hinweis`.

### `mydealz watch [STICHWORT ...]`

Beobachtet ein Stichwort lokal. Der erste Lauf meldet alle Treffer als
neu, der nächste nur das Delta. Das Stichwort ist positional; `--query/-q`
bleibt als Alternative erhalten. Ohne Stichwort endet der Befehl mit
Exit 1 und nennt den nächsten Schritt.

Flags: alle Such-Filter von `search`, zusätzlich:

| Flag | Bedeutung |
|---|---|
| `--dry-run` | Delta anzeigen, State nicht aktualisieren |
| `--json` | JSON-Ausgabe erzwingen |

Ausgabe (JSON): wie `search`, zusätzlich `anzahl_neu`, `anzahl_aktuell`,
`neue_deals`, `state_datei`.

### `mydealz --version`, `mydealz --help`

Beide enden mit Exit 0. `--help` nennt `search`, `show` und `watch`.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | Erfolg |
| `1` | Falsche Eingabe (unbekannter Händler/Kategorie, kaputte ID, fehlendes Stichwort, Argumentfehler in Pipe/`--json`, Aufruf ohne Subbefehl in Pipe) |
| `2` | Fehlende Voraussetzung (z. B. Playwright nicht installiert); im TTY auch Usage-Fehler von argparse und Aufruf ohne Subbefehl |
| `3` | HTTP-/Netzwerkfehler |
| `4` | Parse-Fehler (unerwartetes Markup) |
| `130` | Abbruch durch Strg+C/EOF |

Die bestehenden Codes werden beibehalten. „Unbekannt“ ist nie Erfolg.

## Umgebungsvariablen

| Variable | Bedeutung |
|---|---|
| `MYDEALZ_BASE_URL` | Basis-URL für alle Requests; Default `https://www.mydealz.de`. Für Fake-Server-Tests gedacht. |
| `MDZ_MIN_INTERVAL_MS` | Mindestabstand zwischen Requests in ms; Default `1000`. Tests setzen `0`. |
| `XDG_CONFIG_HOME` | Basis für den Watch-State; Default `$HOME/.config`. |
| `MYDEALZ_WATCH_STATE` | Optionaler vollständiger Pfad zur Watch-State-Datei; überschreibt den XDG-Pfad. |

Ungültige Werte (z. B. kein parsebarer Zahlenwert) führen zu einem
sauberen Fehler ohne Traceback.

## Lokaler Zustand

Das Tool hat keine Login-Session. `watch` speichert ausschließlich lokal:

```text
$XDG_CONFIG_HOME/mydealz-cli/watch.json    (Modus 0600)
```

Mit `MYDEALZ_WATCH_STATE` kann der Pfad vollständig überschrieben werden.
Der State enthält je Stichwort und Filterkombination die gesehenen
Thread-IDs sowie `saved_at`; `--dry-run` schreibt nichts.

## Abgrenzung

- Keine schreibenden Requests, keine Kommentare, Votes, Einreichungen
  oder Käufe.
- Kein Login und keine Zugangsdaten.
- `show` akzeptiert ID oder URL, keinen Deal-Namen.
- Händler-/Kategorie-Slugs und `--category-id` werden lokal auf den
  Server-Treffern angewendet; die Such-URL enthält nur die von mydealz
  unterstützten Parameter.
