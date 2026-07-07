"""Flask backend over the SQLite Java index -- so search/slice can be wired
into other tools (editor plugins, a local LLM's tool-use, a chat UI, ...).

Usage:
    python server.py --db index.sqlite [--port 5000]

Endpoints:
    GET /                                            -- browsable search UI (HTML)
    GET /type/<fqn>                                  -- class detail page (HTML)
    GET /fragment/callers?method=<fqn>#<sig>          -- lazy-loaded caller drill-down (HTML fragment)
    GET /api/search?q=<term>&limit=30
    GET /api/search?q=<term>&code=true&context=5   -- + package/class/method/snippet/callers per hit (flat, 1 level)
    GET /api/search?q=<term>&nested=true&depth=3&context=3 -- same, but 'used_by' recursively nested N levels deep
    GET /api/slice?seed=<name-or-fqn>&depth=2
    GET /api/type/<fqn>
    GET /health
"""

import argparse
import os
import sqlite3

from flask import Flask, jsonify, render_template_string, request

from javaindex.search import _callers_with_location, _occurrence
from javaindex.search import search as run_search
from javaindex.search import search_nested, search_with_code
from javaindex.slice import build_slice
from javaindex.webui import CALLERS_FRAGMENT, SEARCH_PAGE, TYPE_PAGE, method_key

app = Flask(__name__)
app.config["DB_PATH"] = os.environ.get("JAVAINDEX_DB", "index.sqlite")


def _db_path():
    return app.config["DB_PATH"]


@app.get("/health")
def health():
    exists = os.path.exists(_db_path())
    return jsonify({"ok": exists, "db": _db_path()})


@app.get("/")
def search_page():
    q = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)
    context = request.args.get("context", 3, type=int)
    results = search_with_code(_db_path(), q, context=context, limit=limit) if q else []
    return render_template_string(SEARCH_PAGE, q=q, results=results, method_key=method_key)


@app.get("/type/<path:fqn>")
def type_page(fqn):
    info = _type_detail(fqn)
    if info is None:
        return f"<p>Keine Klasse mit FQN '{fqn}' gefunden. <a href='/'>Zur Suche</a></p>", 404
    return render_template_string(TYPE_PAGE, info=info)


@app.get("/fragment/callers")
def fragment_callers():
    """Lazy-loaded next level of the call-graph drill-down: who calls the
    given method. Returns an HTML fragment, not JSON -- meant to be inserted
    directly into the page by the small JS in webui.SCRIPT."""
    key = request.args.get("method", "")
    context = request.args.get("context", 3, type=int)
    if "#" not in key:
        return render_template_string(CALLERS_FRAGMENT, callers=[], method_key=method_key)

    owner_fqn, signature = key.split("#", 1)
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute(
        "SELECT m.id FROM methods m JOIN types t ON t.id = m.type_id WHERE t.fqn=? AND m.signature=? LIMIT 1",
        (owner_fqn, signature),
    ).fetchone()
    if not row:
        conn.close()
        return render_template_string(CALLERS_FRAGMENT, callers=[], method_key=method_key)

    callers = [
        _occurrence(cur, c["path"], c["fqn"], c["signature"], c["line"], context)
        for c in _callers_with_location(cur, row["id"])
    ]
    conn.close()
    return render_template_string(CALLERS_FRAGMENT, callers=callers, method_key=method_key)


@app.get("/api/search")
def api_search():
    term = request.args.get("q", "")
    limit = request.args.get("limit", 30, type=int)
    if not term.strip():
        return jsonify({"error": "missing ?q="}), 400

    if request.args.get("nested", "").lower() in ("1", "true", "yes"):
        # same idea as code=true, but 'used_by' is a recursive tree
        # ({occurrence, used_by}) instead of a flat one-level list -- the
        # same drill-down the HTML UI does lazily on click, pre-computed
        # here as one JSON document.
        context = request.args.get("context", 3, type=int)
        depth = request.args.get("depth", 3, type=int)
        results = search_nested(_db_path(), term, context=context, limit=limit, depth=depth)
        return jsonify({"query": term, "depth": depth, "results": results})

    if request.args.get("code", "").lower() in ("1", "true", "yes"):
        # richer shape for handing to an LLM tool-call: package/class/method
        # + a code snippet per hit, plus the same for every caller of the
        # enclosing method -- enough context for a first-pass explanation
        # without having to fetch/open the files separately.
        context = request.args.get("context", 5, type=int)
        results = search_with_code(_db_path(), term, context=context, limit=limit)
        return jsonify({"query": term, "results": results})

    results = run_search(_db_path(), term, limit=limit)
    return jsonify({"query": term, "results": results})


@app.get("/api/slice")
def api_slice():
    seed = request.args.get("seed", "")
    depth = request.args.get("depth", 2, type=int)
    if not seed.strip():
        return jsonify({"error": "missing ?seed="}), 400
    result = build_slice(_db_path(), seed, depth=depth)
    if "candidates" in result:
        return jsonify({"error": "ambiguous or unknown seed", "candidates": result["candidates"]}), 404
    return jsonify(result)


def _type_detail(fqn):
    """Shared by /api/type and the HTML /type page. None if not found.

    Duplicate FQNs (see build.py) mean this can match more than one type --
    like everywhere else, we just take the first and accept the imprecision.
    """
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    trow = cur.execute(
        "SELECT id, name, fqn, kind, superclass_fqn, start_line FROM types WHERE fqn=? LIMIT 1", (fqn,)
    ).fetchone()
    if not trow:
        conn.close()
        return None

    path_row = cur.execute(
        "SELECT f.path FROM types t JOIN files f ON f.id = t.file_id WHERE t.id=?", (trow["id"],)
    ).fetchone()
    implements = [
        r[0] for r in cur.execute("SELECT interface_fqn FROM type_implements WHERE type_id=?", (trow["id"],))
    ]
    fields = [
        dict(name=r["name"], type=r["field_type_fqn"] or r["field_type_name"])
        for r in cur.execute("SELECT name, field_type_name, field_type_fqn FROM fields WHERE type_id=?", (trow["id"],))
    ]
    methods = [
        dict(name=r["name"], signature=r["signature"], return_type=r["return_type_name"], line=r["start_line"])
        for r in cur.execute(
            "SELECT name, signature, return_type_name, start_line FROM methods WHERE type_id=?", (trow["id"],)
        )
    ]
    conn.close()
    return {
        "fqn": trow["fqn"],
        "name": trow["name"],
        "kind": trow["kind"],
        "path": path_row[0] if path_row else None,
        "superclass_fqn": trow["superclass_fqn"],
        "implements": implements,
        "fields": fields,
        "methods": methods,
    }


@app.get("/api/type/<path:fqn>")
def api_type(fqn):
    info = _type_detail(fqn)
    if info is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(info)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("JAVAINDEX_DB", "index.sqlite"))
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    app.config["DB_PATH"] = args.db
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
