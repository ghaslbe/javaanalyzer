# codeanalyse

Werkzeug, um eine große, unbekannte Java-Codebasis schnell zu verstehen:
per Klassenname oder Text durchsuchen, sehen wie die Klassen zusammenhängen
(Vererbung + Call-Graph), und den relevanten Ausschnitt als Bundle für ein
lokales LLM exportieren.

Der eigentliche Code liegt in [`javaindex/`](javaindex/README.md) -- dort
stehen Setup, Nutzung (`build`/`search`/`slice`/Flask-Backend) und bekannte
Grenzen im Detail.
