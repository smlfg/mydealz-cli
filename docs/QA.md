# Pflicht-QA: mydealz-cli

- Datum: 2026-11-04
- Version: `mydealz 0.1.0`
- Commit: `648a34f34a1dea0e771e830a532c7b500f970b8f` (`direct_url.json` der pipx-Installation)
- Prüfart: eigene QA-Iteration nach `find -> file` (ursprünglich ohne Code-Änderungen); FAIL-Fixes und Live-Nachprüfung siehe Abschnitt „Nachprüfung (S6)“.
- Umgebung: frische `pipx`-Installation aus `git+https://github.com/smlfg/mydealz-cli@main`, Aufruf ausschließlich über `PATH=$PWD/scratch/pipx/bin:$PATH`, Pseudo-Terminal via `script -qec`.
- Live-Zugriffe: ausschließlich lesende GETs auf öffentliche mydealz.de-Seiten; kein Login, keine POSTs, keine schreibenden Aktionen.
- Fake-Server: `tests/harness/fake_server.py` mit den Routen aus `docs/UX.md`.

## Ergebnis

| # | Prüfung | Befehl | Erwartet | Ergebnis | Beleg (gekürzt) |
|---:|---|---|---|---|---|
| 1 | Frische pipx-Installation | `pipx install git+https://github.com/smlfg/mydealz-cli` | Paket + `mydealz` im PATH | OK | `installed package mydealz-cli 0.1.0`; `which mydealz` zeigt `scratch/pipx/bin/mydealz` |
| 2 | Version | `mydealz --version` | Exit 0, Version | OK | `mydealz 0.1.0`, Exit 0 |
| 3 | Haupt-Hilfe | `mydealz --help` | Exit 0, nennt `search`/`show`/`watch` | OK | Usage + drei Subbefehle, Exit 0 |
| 4 | Sub-Hilfen | `mydealz search/show/watch --help` | jeweils Exit 0 | OK | drei Läufe, Exit 0 |
| 5 | Schnellstart Suche (live, TTY) | `mydealz search airpods --max-price 150` | lesbare Treffer, Exit 0 | OK | `13 Treffer · …`, Exit 0 |
| 6 | Schnellstart Detail (live, TTY) | `mydealz show 2853300` | Detailseite lesen, Exit 0 | OK (nach Fix 3e6cc40) | `/deals/2853300` → 410, `/share-deal/2853300` → kanonische Slug-URL, Exit 0 |
| 7 | Detail per vollständiger Slug-URL (live, TTY) | `mydealz show <kanonische /deals/…-2853300-URL>` | URL wird verwendet, Exit 0 | OK (nach Fix 3e6cc40) | URL unverändert geladen, ID `2853300`, Exit 0 |
| 8 | Schnellstart Watch, erster Lauf (live, TTY) | `mydealz watch "switch 2"` | Treffer als neu, Exit 0 | OK | `20 neue Deal(s) … (gemerkt: 20)`, Exit 0 |
| 9 | Schnellstart Watch, zweiter Lauf (live, TTY) | `mydealz watch "switch 2"` | `0 neue`, Exit 0 | OK | `0 neue Deal(s) … (gemerkt: 20)`, Exit 0 |
| 10 | Schnellstart Watch, Dry-Run (live, TTY) | `mydealz watch "switch 2" --dry-run` | Delta, State unverändert | OK | gleicher SHA-256 vor/nach, Modus `600`, Hinweis Dry-Run |
| 11 | Fake-Server Suche | `MYDEALZ_BASE_URL=<fake> mydealz search airpods --max-price 150` | 3 Fixture-Treffer | OK | `3 Treffer · http://127.0.0.1:…/search?q=airpods…` |
| 12 | Fake-Server Detail | `MYDEALZ_BASE_URL=<fake> mydealz show 2853300` | Stub mit Hinweis | OK | `Schachnovelle …`, `Hinweis: Diese Seite ist JS-only…` |
| 13 | Fake-Server Watch | `MYDEALZ_BASE_URL=<fake> mydealz watch "switch 2"` (2×) | 3 neu, dann 0 neu | OK | `3 neue …` / `0 neue …` |
| 14 | Fake-Server Watch Dry-Run | `MYDEALZ_BASE_URL=<fake> mydealz watch "switch 2" --dry-run` | 0 neu, State unverändert | OK | `0 neue …`, `Hinweis: Dry-Run…` |
| 15 | Filter `--max-price` über alle Treffer | `mydealz search airpods --max-price 150 --json` | kein Preis > 150 | OK | 13/13 Treffer ≤ 150 € |
| 16 | Filter `--min-price` über alle Treffer | `mydealz search monitor --min-price 100 --json` | kein Preis < 100 | OK | 20/20 Treffer ≥ 100 € |
| 17 | Filter `--only-active` über alle Treffer | `mydealz search airpods --only-active --json` | alle `ist_aktiv=true` | OK | 11/11 aktiv |
| 18 | Filter `--only-with-code` über alle Treffer | `mydealz search airpods --only-with-code --json` | alle mit Code | OK | 6/6 mit `gutschein_code` |
| 19 | Filter `--min-temperature` über alle Treffer | `mydealz search monitor --min-temperature 500 --json` | alle ≥ 500 | OK | 5/5 ≥ 500 |
| 20 | Filter `--merchant` über alle Treffer | `mydealz search --merchant amazon --limit 30 --json` | nur Amazon | OK | 2/2 Amazon |
| 21 | Filter `--merchant-id` über alle Treffer | `mydealz search --merchant-id 3 --limit 10 --json` | nur Händler-ID 3 | OK | 10/10 Amazon, ID 3 |
| 22 | Filter `--category` über alle Treffer | `mydealz search airpods --category elektronik --json` | nur Elektronik | OK (nach Fix cc7496c) | 7/7 Elektronik |
| 23 | Filter `--category-id` | `mydealz search airpods --category-id 1 --json` | Treffer der Kategorie 1 | OK (nach Fix cc7496c) | ID 1 → Mode: 0 Treffer; ID 2 → Elektronik: 7/7; live-`kategorie.id` bleibt null, Filter läuft über Slug |
| 24 | Filter `--order` | `mydealz search monitor --order price-low/price-high/newest --json` | unterschiedliche Reihenfolge | OK (nach Fix 913b86a) | `sortBy` statt `order`; erste IDs: `2833472` / `2860631` / `2864679` |
| 25 | Filter `--type coupon` | `mydealz search monitor --type coupon --json` | nur Gutscheine | OK (nach Fix cc7496c) | 5/5 Treffer mit `gutschein_code` bzw. Typ `Voucher` |
| 26 | Filter `--include-expired` | `mydealz search airpods --include-expired --json` | mehr/andere Treffer als Default | OK (nach Fix cc7496c) | Default 11 aktive, mit `--include-expired` 20 Treffer (9 abgelaufen) |
| 27 | Pagination | `mydealz search monitor --page 2 --limit 10 --json` | andere Treffer als Seite 1 | OK | 10 andere IDs (u. a. `2858538`) |
| 28 | Limit | `mydealz search monitor --limit 5 --json` | genau 5 Treffer | OK | `anzahl: 5` |
| 29 | Positional mit mehreren Wörtern | `mydealz search apple airpods --limit 3 --json` | `q=apple+airpods` | OK | URL `…?q=apple+airpods…`, plausible AirPods-Treffer |
| 30 | Umlaut-Suche | `mydealz search "kühlschrank" --json` | plausible Kühlschrank-Treffer | OK | `q=k%C3%BChlschrank`, Kategorie Home & Living |
| 31 | Händler-Name mit Umlaut | `mydealz search --merchant "Müller" --limit 3 --json` | Händler wird aufgelöst | OK (nach Fix 7eec27f) | `Müller` → `mueller-de`, Exit 0 (ohne passende Treffer: `anzahl: 0`) |
| 32 | Leere Trefferliste | `MYDEALZ_BASE_URL=<lokaler Leer-Server> mydealz search airpods --json` | 0 Treffer, valides JSON | OK | `0 Treffer · …`, `"anzahl": 0`, `"deals": []` |
| 33 | Live-Suche ohne echten Treffer | `mydealz search "zzzzqxvjkqwxzvjkqwxzv" --json` | 0 Treffer *oder* plausible Quelle | OK (Hinweis) | mydealz liefert 4 Fallback-Treffer; Quelle verhält sich so, kein Tool-Fehler |
| 34 | Netzfehler im TTY | `MYDEALZ_BASE_URL=http://127.0.0.1:9 mydealz search airpods` | Meldung + nächster Schritt, Exit 3 | OK | `Netzwerkfehler … Nächster Schritt: Internetverbindung prüfen…`, Exit 3 |
| 35 | Netzfehler in Pipe | wie #34, stdout Pipe | JSON-Fehler, Exit 3 | OK | valides JSON mit `"error"`, Exit 3 |
| 36 | Ungültige Basis-URL | `MYDEALZ_BASE_URL=nicht-gueltig mydealz search airpods` | saubere Meldung, Exit 1 | OK | `Ungültige MYDEALZ_BASE_URL… Nächster Schritt: … korrigieren…`, kein Traceback |
| 37 | Fehler nennen nächsten Schritt | `mydealz show nichtnumerisch`; `mydealz search --unbekannt` | nächster Schritt genannt | OK (nach Fix f38ede3) | beide Meldungen enden mit `Nächster Schritt: …`, Exit 1 |
| 38 | Kein Subbefehl im TTY | `mydealz` | Usage + Beispiele, Exit ≠ 0 | OK | Usage + `Beispiele: mydealz search airpods …`, Exit 2 |
| 39 | Kein Subbefehl in Pipe | `mydealz` (Pipe) | JSON-Fehler, Exit 1 | OK | `{"error": "Kein Subbefehl angegeben …"}`, Exit 1 |
| 40 | `watch` ohne Stichwort | `mydealz watch` | Meldung + nächster Schritt, Exit 1 | OK | `Stichwort fehlt. Nutzbar als: mydealz watch "switch 2" …`, Exit 1 |
| 41 | Playwright fehlt | `mydealz show 2853300 --render playwright` | Hinweis auf Installation, Exit 2 | OK | `Playwright nicht installiert. 'pip install mydealz-cli[playwright]' …`, Exit 2 |
| 42 | TTY lesbar, `--json` rein | `script -qec "mydealz search … --json"` | Text im TTY, JSON mit `--json` | OK | TTY-Ausgabe `13 Treffer · …`; `--json` parst als genau ein Objekt |
| 43 | `--json` valide | alle Live-/Fehler-Aufrufe mit `--json` | genau ein JSON-Objekt | OK | `json.loads` für Suche, Watch und Fehler erfolgreich |
| 44 | Keine Tracebacks | alle Läufe inkl. Netz-/Env-/Argparse-Fehler | keine Tracebacks | OK | in allen Pseudo-Terminal-Logs keine Traceback-Zeilen |
| 45 | Nur lesende GETs | Quellcode + Fake-Server-Protokoll | keine POST/PUT/DELETE | OK | `rg` findet keine schreibenden HTTP-Aufrufe; Fake-Server nur GET |
| 46 | Login | `mydealz login` | kein Login nötig | OK (entfällt) | `credential_env` leer; `login` ist unbekannt (Exit 2, kein Traceback) |
| 47 | Testsuite | `scratch/venv/bin/pytest -q` | grün | OK | `110 passed` |

## Zählung

- **OK: 47**
- **FAIL: 0**
- **Gesamt: 47**

## Nachprüfung (S6)

Alle neun FAILs wurden im Code behoben und live erneut geprüft; die
betroffenen Zeilen stehen oben auf „OK (nach Fix …)“. Commits:

| FAIL | Commit | Fix |
|---:|---|---|
| 1, 2 | `3e6cc40` | Slug-URL wird verwendet; `/deals/<ID>`-410 fällt auf `/share-deal/<ID>` zurück |
| 3, 4, 6, 7 | `cc7496c` | Kategorie-Slug/-ID, Gutschein-Typ und Ablauf lokal erzwungen |
| 5 | `913b86a` | Sortierung über `sortBy` statt wirkungslosem `order` |
| 8 | `7eec27f` | Händler-Umlaute/Anzeigenamen werden aufgelöst |
| 9 | `f38ede3` | ID- und Optionsfehler nennen den nächsten Schritt |

Gate-Nachlauf: `pytest -q` → `110 passed`;
`tests/harness/ux_check.py .` → Exit 0 (PASS);
`tests/harness/ux_session.py .` → Exit 0 (PASS).

Erneute Live-Nachprüfung am 2026-11-09 (nur lesende GETs): `show 2853300`
und Slug-URL → Exit 0; `--category elektronik` → 8/8 Elektronik;
`--category-id 1` → 0 (Mode), `--category-id 2` → 8/8 Elektronik;
`--order price-low/price-high/newest` → unterschiedliche Reihenfolge;
`--type coupon` → 6/6 mit Gutscheincode; `--include-expired` → 20 statt 12
Treffer; `--merchant "Müller"` → Exit 0; ID-/Optionsfehler → Exit 1 mit
`Nächster Schritt`. `pytest -q` → `110 passed`; `ux_check.py .` und
`ux_session.py .` → jeweils Exit 0 (PASS). Logs: `scratch/qa/s6c_*`.

## Beobachtungen (kein FAIL)

- `mydealz search "zzzz…"` liefert live 4 unpassende Fallback-Treffer. Das ist das Verhalten der mydealz-Suche, nicht des CLI; die Behandlung einer echten leeren Liste wurde gegen einen lokalen Leer-Server geprüft (0 Treffer, valides JSON).
- Händler-/Kategorie-Slugs werden lokal gefiltert. Kategorien laufen seit dem Fix über den Slug, weil live `kategorie.id = null` ist.
- Die Detailseite ist bewusst nur ein `<title>`/`og:*`-Stub ohne Playwright. Der Stub funktioniert gegen den Fake-Server; live lädt der Fallback über `/share-deal/<ID>` die kanonische Seite.

## Nicht durchgeführt

- Keine schreibenden Aktionen, kein Login und keine echten Konten (read-only Tool).
- Keine GitHub-Issues angelegt; die ehemaligen FAILs aus `scratch/QA-FAILS.md` sind mit den Commits aus „Nachprüfung (S6)“ behoben.
