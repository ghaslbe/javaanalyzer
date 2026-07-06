# javaindex

Indexiert eine Java-Codebasis in eine SQLite-Datenbank, damit man sie per
Klassenname/Text durchsuchen und gezielt den "relevanten Ausschnitt"
(Vererbung + Call-Graph-Nachbarschaft) als Bundle exportieren kann -- fertig
zum Einspeisen in ein lokales LLM.

## Warum das so gebaut ist

Kein Java, kein Compiler, keine weiteren Tool-Installationen -- nur Python
(pip erlaubt) auf einer Windows-Maschine mit JRE, aber ohne `javac`. Es gibt
also keine echte Compiler-Symboltabelle. Stattdessen parst
[`javalang`](https://github.com/c2nc/javalang) (pure Python, keine
Compilation nötig) jede Datei zu einem AST, und ein eigener Resolver
(`javaindex/registry.py`, `javaindex/resolver.py`) löst Typnamen und
Methodenaufrufe *best effort* auf:

- Vererbung/Interfaces über Imports, gleiches Package, Wildcard-Imports
- Feld-/Parameter-/lokale Variablentypen als Grundlage für `x.methode()`
- verkettete Aufrufe (`new Foo().bar().baz()`) durch Weiterverfolgen des
  Rückgabetyps
- `this.feld.methode()`, `super.methode()`, `super(...)`, `this(...)`

Was sich nicht auflösen lässt (JDK-/Library-Klassen ohne eigenen Quellcode,
mehrdeutige Overloads, Zugriffe nach einer nicht aufgelösten Kette) wird als
"unresolved" gespeichert -- weiterhin per Namen suchbar, nur ohne
aufgelöstes Ziel. Das muss nicht perfekt sein, es soll nur beim Verstehen
helfen.

## Setup (Windows/PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

(macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`)

## Index bauen

```bash
python -m javaindex.build /pfad/zum/java/repo --db index.sqlite
```

Baut die Datenbank **komplett neu** (drop + recreate). Es gibt keinen
inkrementellen Modus -- wenn sich der Code ändert, einfach denselben Befehl
erneut laufen lassen, um den Index auf den aktuellen Stand zu bringen.

Neben `.java` werden auch `.properties`, `.xml`, `.yml`/`.yaml` per Volltext
mitindexiert (nicht geparst, nur roher Text) -- damit auch ausgelagerte
Texte/URLs (Config, Connection-Strings, Log-Formate, ...) über die Suche
gefunden werden, nicht nur Code.

## Suchen

```bash
python -m javaindex.search index.sqlite "FunnelDynamic"
python -m javaindex.search index.sqlite "utm"
```

Findet Klassen und Methoden per Präfix-Volltextsuche (FTS5) über Name/FQN --
und zusätzlich per Volltext über den kompletten Dateiinhalt, damit auch
Treffer in lokalen Variablen, String-Literalen oder Kommentaren gefunden
werden (fachliche Begriffe wie `utm` tauchen oft nur dort auf, nicht als
Klassen-/Methodenname). Ein solcher Datei-Treffer zeigt den Dateipfad, die
darin enthaltenen Klassen (FQN) und die passenden Zeilen mit Zeilennummer.

Jeder Treffer zeigt zusätzlich, wer die betroffene Methode aufruft
(`genutzt von: ...`, aus dem Call-Graph): bei einem direkten Methodentreffer
für diese Methode, bei einem Text-Treffer für die Methode, in der die
passende Zeile liegt (per nächstgelegener `start_line` geschätzt, da keine
exakten Methodenenden getrackt werden -- funktioniert bei normal
formatiertem Code zuverlässig).

### Mit Code-Kontext

```bash
python -m javaindex.search index.sqlite "utm" --code --context 5
```

Zeigt zu jedem Treffer Package, Klasse, Methode und den Quellcode +/-
`--context` Zeilen davor/dahinter -- und darunter, für jede Klasse/Methode,
die die betroffene Methode aufruft, denselben Ausschnitt an deren Aufrufstelle.
Damit lässt sich allein aus der Suchausgabe nachvollziehen, wie eine Fundstelle
mit anderen Klassen zusammenhängt, ohne die Dateien einzeln zu öffnen.

## Slice fürs LLM

```bash
python -m javaindex.slice index.sqlite StartController --depth 2 --out slice.txt
```

Läuft per BFS über Vererbung, verschachtelte Klassen und den Call-Graph
(Aufrufer *und* Aufgerufene) `--depth` Hops von der Seed-Klasse aus, druckt
eine Beziehungs-Übersicht und schreibt den gebündelten Quellcode aller
betroffenen Dateien nach `slice.txt`.

`StartController` kann ein exakter FQN, ein einfacher Klassenname oder ein
Teilstring sein; bei Mehrdeutigkeit werden Kandidaten aufgelistet.

## Flask-Backend

```bash
python server.py --db index.sqlite --port 5000
```

- `GET /api/search?q=<term>&limit=30`
- `GET /api/slice?seed=<name-oder-fqn>&depth=2`
- `GET /api/type/<fqn>` -- Felder/Methoden/Hierarchie einer einzelnen Klasse
- `GET /health`

Damit lässt sich die Suche in andere Tools (Editor-Plugin, Chat-UI, lokales
LLM als Tool-Call) einbinden, ohne die SQLite-Datei direkt anzufassen.

## Bekannte Grenzen

- Kein echtes Overload-Resolving (erste Methode mit passendem Namen gewinnt).
- Keine Block-Scoping-Genauigkeit bei lokalen Variablen (flach pro Methode).
- Felder, die über eine nicht auflösbare Zwischen-Kette erreicht werden
  (`a.b().feld.methode()`), brechen die Auflösung ab statt zu raten.
- `javalang` versteht kein sehr neues Java (records, sealed classes,
  pattern matching, text blocks) -- solche Dateien werden beim Build
  übersprungen und als Fehler ausgegeben, tauchen aber nicht im Index auf.
