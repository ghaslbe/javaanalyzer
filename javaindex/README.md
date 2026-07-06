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

Bei großen Repos (mehrere 10.000+ Dateien, insbesondere über ein
Netzlaufwerk) läuft der Build eine Weile. Solange die Ausgabe in einem
echten Terminal landet, zeigt eine sich selbst überschreibende Zeile den
Fortschritt (Scannen/Parsen/Call-Graph-Auflösung/Resource-Indexierung) an,
statt das Terminal mit tausenden Zeilen zuzuspammen. Bei Umleitung in eine
Datei (`> log.txt`) wird diese Zeile automatisch weggelassen, da `\r` dort
ohnehin nur Datenmüll erzeugen würde -- die normalen Zusammenfassungszeilen
(`found ... files`, `indexed ...`) bleiben davon unberührt.

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
- `GET /api/search?q=<term>&code=true&context=5` -- zusätzlich Package/Klasse/Methode + Code-Snippet je Treffer und je Aufrufer (Rückgabe von `search_with_code()`, siehe oben)
- `GET /api/slice?seed=<name-oder-fqn>&depth=2`
- `GET /api/type/<fqn>` -- Felder/Methoden/Hierarchie einer einzelnen Klasse
- `GET /health`

Damit lässt sich die Suche in andere Tools (Editor-Plugin, Chat-UI, lokales
LLM als Tool-Call) einbinden, ohne die SQLite-Datei direkt anzufassen.

### Als Tool für ein lokales LLM (z.B. Gemma über Ollama)

Der Sinn von `code=true`: ein kleines lokales Modell muss die Dateien nicht
selbst öffnen/durchsuchen -- ein Tool-Call auf `/api/search?q=...&code=true`
liefert direkt alles, was für eine kurze Ersteinschätzung nötig ist (wo
steht es, was macht die Zeile, wer ruft die Methode noch auf). Das Modell
muss dann nur noch zusammenfassen, nicht mehr selbst im Repo suchen.

Beispiel-Tool-Definition (Ollama/OpenAI-kompatibles Function-Calling):

```json
{
  "name": "search_java_code",
  "description": "Durchsucht den indexierten Java-Code nach einem Begriff (Klassen-/Methodennamen, aber auch Text in Properties/XML/Kommentaren) und liefert Fundstellen inkl. Code-Kontext und Aufrufern.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Suchbegriff, z.B. ein Klassenname oder fachlicher Begriff"}
    },
    "required": ["query"]
  }
}
```

Die Tool-Implementierung ruft dann `GET /api/search?q=<query>&code=true&context=5`
auf und gibt das JSON ans Modell zurück. Ein sinnvoller System-Prompt für den
Einstieg:

> Du bekommst Suchtreffer aus einer Java-Codebasis (Package, Klasse, Methode,
> Code-Ausschnitt, sowie wer die Methode aufruft). Fasse in wenigen Sätzen
> zusammen: wo der Begriff vorkommt, was der Code an der Stelle tut, und was
> eine Änderung dort vermutlich beeinflussen würde (basierend auf den
> Aufrufern). Wenn nichts gefunden wurde, sag das klar.

Für sehr kleine Modelle (4B-Klasse) `context` niedrig halten (2-3) und
`limit` klein (5-10), damit der Prompt nicht zu groß wird -- die Callers
werden pro Treffer mitgeliefert und können bei vielen Aufrufern schnell
wachsen.

## Bekannte Grenzen

- Kein echtes Overload-Resolving (erste Methode mit passendem Namen gewinnt).
- Keine Block-Scoping-Genauigkeit bei lokalen Variablen (flach pro Methode).
- Felder, die über eine nicht auflösbare Zwischen-Kette erreicht werden
  (`a.b().feld.methode()`), brechen die Auflösung ab statt zu raten.
- `javalang` versteht kein sehr neues Java (records, sealed classes,
  pattern matching, text blocks) -- solche Dateien werden beim Build
  übersprungen und als Fehler ausgegeben, tauchen aber nicht im Index auf.
- Wird dieselbe Klasse (gleiches Package + Name) in mehreren Dateien deklariert
  (z.B. Duplikate/generierter Code über mehrere Module hinweg), werden beide
  vollständig indexiert und sind durchsuchbar -- aber Hierarchie-/Slice-Suche
  per FQN (`slice.py`, `/api/type/<fqn>`) trifft dann eine von beiden, nicht
  garantiert die "richtige". `build.py` gibt beim Build eine Warnung mit den
  betroffenen Dateipfaden aus.
