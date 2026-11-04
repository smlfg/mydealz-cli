# UX-Gate-Bericht

- Datum: 2026-11-04
- Tool: `mydealz`
- Repo: `smlfg/mydealz-cli`
- Typ: `cli`, read-only (kein Login, keine schreibenden Aktionen)

## Läufe

| Befehl | Exit-Code |
|---|---|
| `python3 tests/harness/ux_check.py . --report scratch/ux_check.md` | 0 |
| `python3 tests/harness/ux_session.py . --report scratch/ux_session.md` | 0 |

Zusätzlich: `scratch/venv/bin/pytest -q` → 100 passed, Exit 0.

## ux_check.py (UX00–UX09)

- Modus: voll
- Ergebnis: PASS

| ID | Ergebnis | Befund |
|---|---|---|
| UX00 | PASS | 4 Request(s) am Fake-Server, keine Fremdverbindung |
| UX01 | PASS | docs/UX.md: 3 Sitzungen, 0 formsteps |
| UX02 | PASS | keine Credential-Env-Variablen gefunden |
| UX03 | PASS | --help, --version und 3 Unterkommandos mit Exit 0 |
| UX04 | PASS | 3 Unterkommandos ohne Pflicht-Option statt positional |
| UX05 | PASS | 3 Sitzungen ohne JSON/Traceback im TTY |
| UX06 | PASS | Schnellstart: 4 Tool-Befehle, Installation passt |
| UX07 | PASS | keine ux-formsteps, keine schreibende Aktion |
| UX08 | PASS | keine ux-formsteps, keine schreibende Aktion |
| UX09 | SKIP | keine schreibende Sitzung |

## ux_session.py

- Ergebnis: PASS

| Sitzung | Lauf | Ergebnis | Befund |
|---|---|---|---|
| Installation und Deals nach Stichwort suchen | 1 | PASS | OK |
| Deal-Details lesen | 1 | PASS | OK |
| Neue Deals seit dem letzten Lauf beobachten | 1 | PASS | OK |

## Hinweise

- UX09 und die schreibenden Prüfungen (UX07/UX08) entfallen erwartungsgemäß,
  weil das Tool ausschließlich lesende GET-Requests ausführt.
- Die drei UX-Sitzungen laufen gegen den lokalen Fake-Server über
  `MYDEALZ_BASE_URL`; es werden keine echten Server erreicht.
