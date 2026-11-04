# Anforderungen: mydealz-cli

Stand: 2026-11-04. Grundlage sind der Tool-Brief, das bestehende README,
die Live-Erkundung in `scratch/live/NOTIZEN.md` und die UX-Spec in
`docs/UX.md`.

## Zweck

`mydealz` durchsucht öffentliche Deals und Gutscheine auf mydealz.de,
liest Deal-Details und merkt sich lokal neue Treffer je Stichwort. Das
Tool ist für Menschen im Terminal und für Agenten in Pipes gleichermaßen
bedienbar. Alle Zugriffe sind lesende GETs; es gibt keinen Login.

## Nachfrage

Belegt durch die vorhandenen Projektquellen (keine erfundenen externen
Quellen):

| Quelle | Datum | Beleg |
|---|---|---|
| Tool-Brief `scratch/BRIEF.md` | 2026-11-04 | NACHRÜSTUNG eines bestehenden Tools; drei UX-Sitzungen (Suche, Detail, Watch) sind vorgegeben. |
| Bestehendes `README.md` | 2026-11-04 | Zielgruppe Agenten/LLM-Pipelines, Wunsch nach Suche, Details und lokalem Keyword-Watch. |
| `docs/UX.md` und `scratch/live/NOTIZEN.md` | 2026-11-04 | Live lesend erkundete Such-, Detail- und Watch-Routen; Fixtures liegen unter `tests/fixtures/ux/`. |

Die Nachfrage ist damit im Projekt belegt. Externe Marktplätze
(Smithery/Glama/mcp.so, Reddit, GitHub-Requests) wurden in dieser Runde
nicht neu recherchiert.

## Nutzer-Aufgaben (UX-Sitzungen)

1. **Installation und Suche:** `pipx install …`, danach
   `mydealz search airpods --max-price 150`.
2. **Deal-Details lesen:** `mydealz show 2853300`.
3. **Neue Deals beobachten:** `mydealz watch "switch 2"`, erneut
   aufrufen oder `--dry-run` verwenden.

## Funktionale Anforderungen

| ID | Anforderung |
|---|---|
| F1 | `search` nimmt das Stichwort positional (`search [STICHWORT ...]`); `--query/-q` bleibt als Alternative erhalten. |
| F2 | `search` unterstützt Typ, Sortierung, Seite, Preisgrenzen, Händler, Kategorie, Temperatur, Limit sowie die Filter „nur aktiv“ und „nur mit Code“. |
| F3 | Alle Filter werden clientseitig über die vollständige Trefferliste erzwungen, auch wenn die Server-Suche mehr liefert. |
| F4 | `show` nimmt eine Thread-ID oder Deal-URL positional. Ohne Playwright ist die Ausgabe ein beabsichtigter `<title>`/`og:*`-Stub mit Hinweis. |
| F5 | `watch` nimmt das Stichwort positional, speichert gesehene Thread-IDs lokal (Modus 0600) und meldet beim nächsten Lauf nur neue Treffer. |
| F6 | `watch --dry-run` zeigt das Delta, ohne den State zu aktualisieren. |
| F7 | Die Basis-URL ist über `MYDEALZ_BASE_URL` überschreibbar; Default ist `https://www.mydealz.de`. Damit sind Fake-Server-Tests möglich. |
| F8 | Es gibt keine schreibenden Aktionen und keinen Login. Es gibt weder `[j/N]` noch `--confirm`/`--yes`. |
| F9 | Im TTY ist die Ausgabe lesbar; mit `--json` oder in einer Pipe ist sie genau ein JSON-Objekt. |
| F10 | Fehler nennen den nächsten Schritt und erzeugen nie einen Traceback, auch nicht bei Strg+C/EOF. |

## Nicht-funktionale Anforderungen

| ID | Anforderung |
|---|---|
| N1 | Python >= 3.10; nur `argparse` sowie `requests`/`httpx` (und `beautifulsoup4`, wo nötig). |
| N2 | Keine Secrets und keine echten Personendaten in Repo, Fixtures oder Logs. |
| N3 | Tests erreichen nie echte Server; der Watch-State liegt außerhalb des Repos. |
| N4 | Höflicher User-Agent und Standard-Rate-Limit (1 Request/s, per `MDZ_MIN_INTERVAL_MS` änderbar). |
| N5 | Bestehende Befehle, Flags und Exit-Codes bleiben erhalten; neue Flags sind additiv. |

## Akzeptanzkriterien

| UX-Sitzung | Akzeptanztest |
|---|---|
| Installation und Suche | `tests/acceptance/test_ux_sessions.py::test_search_session` |
| Deal-Details lesen | `tests/acceptance/test_ux_sessions.py::test_show_session` |
| Neue Deals beobachten | `tests/acceptance/test_ux_sessions.py::test_watch_session` und `::test_watch_dry_run_keeps_state` |

Die Tests laufen das Tool als Subprozess gegen
`tests/harness/fake_server.py` mit den Routen aus `docs/UX.md` und
`MYDEALZ_BASE_URL`. Sie dürfen in R2 rot sein, müssen aber die spätere
Schnittstelle exakt prüfen.

## Offene Punkte (nicht Teil von R2)

- `mydealz show <ID>` antwortet live mit HTTP 410; die kanonische
  Slug-URL funktioniert. Eine Auflösung über `share-deal/<ID>` ist als
  späterer Code-Schritt vorgesehen.
- Die Detailseite ist JS-only; volle Details brauchen optional Playwright.
- Händler-/Kategorie-Slugs und `--category-id` filtern lokal, weil
  mydealz die numerischen IDs nicht stabil bzw. `group-id` ignoriert.
- `watch` nennt im Docstring `MYDEALZ_WATCH_STATE`; die tatsächliche
  Anbindung ist im Interface beschrieben und wird im Code nachgezogen.

## Abgrenzung

Keine Anmeldung mit echten Konten, keine echten Buchungen, Nachrichten,
Einreichungen, Votes oder Käufe. Live-Zugriffe sind ausschließlich
lesende GETs auf öffentliche Seiten.
