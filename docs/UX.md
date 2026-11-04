# UX-Spec: mydealz

mydealz durchsucht öffentliche Deals und Gutscheine auf mydealz.de, zeigt
Deal-Details und merkt sich lokal die bereits gesehenen Treffer je
Stichwort. Das Tool ist read-only: kein Login, keine POSTs, keine
Bestätigungsfrage und keine schreibenden Aktionen.

Alle Befehle sind so abtippbar, wie ein Mensch sie im Terminal eingibt.
Die Basis-URL ist für Tests über `MYDEALZ_BASE_URL` überschreibbar; im
Normalbetrieb bleibt es bei `https://www.mydealz.de`.

## Meta

```ux-meta
{"tool": "mydealz",
 "install": "pipx install git+https://github.com/smlfg/mydealz-cli",
 "base_url_env": "MYDEALZ_BASE_URL",
 "credential_env": []}
```

`credential_env` ist leer, weil das Tool keinen Login braucht. Deshalb
gibt es auch kein `login`-Unterkommando.

## Sitzungen

### Installation und Deals nach Stichwort suchen

Der Befehl wird per `pipx` installiert und liegt danach im PATH. Der
Suchbegriff steht positional; `--max-price` begrenzt den Preis. Die
Ausgabe im Terminal zeigt Preise, Händler, Temperatur und Deal-ID, damit
ein Mensch ohne Nachschlagen weiterarbeiten kann.

```ux-session
$ pipx install git+https://github.com/smlfg/mydealz-cli
$ mydealz search airpods --max-price 150
<~ \d+ Treffer · .*/search\?q=airpods&max-price=150&hide-expired=1
<~ \[1\] 129,62 € .*OTTO.*ID 2854689
! exit 0
```

### Deal-Details lesen

Die Detailseite ist ohne Playwright nur ein Stub aus `<title>` und
`og:*`-Metadaten. Das ist beabsichtigt und wird im Terminal als Hinweis
ausgegeben. Die ID steht positional; eine vollständige Deal-URL wird
ebenfalls akzeptiert.

```ux-session
$ mydealz show 2853300
<~ Schachnovelle
< ID: 2853300
<~ Deal-URL: https://www\.mydealz\.de/deals/.*-2853300
<~ Hinweis: Diese Seite ist JS-only
! exit 0
```

### Neue Deals seit dem letzten Lauf beobachten

`watch` speichert die gesehenen Thread-IDs lokal und meldet beim nächsten
Lauf nur neue Treffer. Der erste Lauf meldet alle Treffer als neu, der
zweite Lauf `0 neue`. `--dry-run` zeigt das Delta, ohne den State zu
aktualisieren.

```ux-session
$ mydealz watch "switch 2"
<~ \d+ neue Deal\(s\) für 'switch 2' \(gemerkt: \d+\)
<~ \[1\].*ID 2864775
! exit 0
$ mydealz watch "switch 2" --dry-run
< 0 neue Deal(s) für 'switch 2' (gemerkt: 3)
< Hinweis: Dry-Run: State wurde nicht aktualisiert.
! exit 0
```

## Lesende Routen

Alle Requests sind öffentliche GETs. Es gibt keinen Login-POST und keine
schreibenden Requests. Die Antwortdateien liegen relativ zum Repo und
wurden aus Live-Antworten gekürzt sowie von Nutzerdaten befreit.

```ux-routes
[{"method":"GET","path":"/search","query_contains":"q=airpods","response":"tests/fixtures/ux/search_airpods.html","status":200,"content_type":"text/html; charset=utf-8"},
 {"method":"GET","path":"/deals/2853300","response":"tests/fixtures/ux/deal_2853300.html","status":200,"content_type":"text/html; charset=utf-8"},
 {"method":"GET","path":"/search","query_contains":"q=switch+2","response":"tests/fixtures/ux/search_switch2.html","status":200,"content_type":"text/html; charset=utf-8"}]
```

## Formularschritte der schreibenden Aktion

Es gibt keine schreibende Aktion. mydealz-cli liest nur; deshalb ist der
Abschnitt `ux-formsteps` leer und es gibt weder `[j/N]` noch
`--confirm`/`--yes`. Für den Watch-State wird ausschließlich lokal
geschrieben (`$XDG_CONFIG_HOME/mydealz-cli/watch.json`, Modus 0600).
