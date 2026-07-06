"""Flask backend over the SQLite Java index -- so search/slice can be wired
into other tools (editor plugins, a local LLM's tool-use, a chat UI, ...).

Usage:
    python server.py --db index.sqlite [--port 5000]

Endpoints:
    GET /api/search?q=<term>&limit=30
    GET /api/search?q=<term>&code=true&context=5   -- + package/class/method/snippet/callers per hit
    GET /api/slice?seed=<name-or-fqn>&depth=2
    GET /api/type/<fqn>
    GET /health
"""

import argparse
import os
import sqlite3

from flask import Flask, jsonify, request

from javaindex.search import search as run_search
from javaindex.search import search_with_code
from javaindex.slice import build_slice

app = Flask(__name__)
app.config["DB_PATH"] = os.environ.get("JAVAINDEX_DB", "index.sqlite")


def _db_path():
    return app.config["DB_PATH"]


@app.get("/health")
def health():
    exists = os.path.exists(_db_path())
    return jsonify({"ok": exists, "db": _db_path()})


@app.get("/api/search")
def api_search():
    term = request.args.get("q", "")
    limit = request.args.get("limit", 30, type=int)
    if not term.strip():
        return jsonify({"error": "missing ?q="}), 400

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


@app.get("/api/type/<path:fqn>")
def api_type(fqn):
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    trow = cur.execute(
        "SELECT id, name, fqn, kind, superclass_fqn, start_line FROM types WHERE fqn=?", (fqn,)
    ).fetchone()
    if not trow:
        conn.close()
        return jsonify({"error": "not found"}), 404

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
    return jsonify(
        {
            "fqn": trow["fqn"],
            "name": trow["name"],
            "kind": trow["kind"],
            "path": path_row[0] if path_row else None,
            "superclass_fqn": trow["superclass_fqn"],
            "implements": implements,
            "fields": fields,
            "methods": methods,
        }
    )


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
