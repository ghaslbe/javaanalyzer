"""Full-text search over the index (class/method names, FQNs).

Usable as a library (search()) from the Flask backend, or as a CLI:
    python -m javaindex.search index.sqlite "Funnel"
"""

import argparse
import sqlite3


def _tokens(term):
    return term.replace('"', "").split()


def _match_query(term):
    term = term.strip()
    if not term:
        return None
    return " ".join(f"{tok}*" for tok in _tokens(term))


def _callers_of(cur, method_id, limit=20):
    """Who calls this method, resolved within our own index."""
    rows = cur.execute(
        """SELECT DISTINCT t.fqn, m.signature
           FROM calls c
           JOIN methods m ON m.id = c.caller_method_id
           JOIN types t ON t.id = m.type_id
           WHERE c.callee_method_id = ?
           LIMIT ?""",
        (method_id, limit),
    ).fetchall()
    return [f"{fqn}#{signature}" for fqn, signature in rows]


def _enclosing_method(cur, file_id, line):
    """Best-guess method containing a given line: the closest method
    declared at or before it in the same file (no end_line is tracked, so
    this assumes methods don't overlap -- true for normal formatting)."""
    return cur.execute(
        """SELECT m.id, t.fqn, m.signature
           FROM methods m JOIN types t ON t.id = m.type_id
           WHERE t.file_id = ? AND m.start_line IS NOT NULL AND m.start_line <= ?
           ORDER BY m.start_line DESC LIMIT 1""",
        (file_id, line),
    ).fetchone()


def _matching_lines(path, tokens, limit=15):
    tokens_lower = [t.lower() for t in tokens]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    hits = []
    for i, line in enumerate(lines, start=1):
        low = line.lower()
        if any(tok in low for tok in tokens_lower):
            hits.append({"line": i, "text": line.strip()})
            if len(hits) >= limit:
                break
    return hits


def search(db_path, term, limit=30):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    match = _match_query(term)
    if not match:
        return []

    rows = cur.execute(
        """SELECT fqn, name, kind, path, ref_id, ref_kind, rank
           FROM search WHERE search MATCH ? ORDER BY rank LIMIT ?""",
        (match, limit),
    ).fetchall()

    results = []
    for row in rows:
        item = {
            "kind": row["ref_kind"],
            "name": row["name"],
            "fqn": row["fqn"],
            "path": row["path"],
        }
        if row["ref_kind"] == "type":
            trow = cur.execute(
                "SELECT kind, superclass_fqn, start_line FROM types WHERE id=?", (row["ref_id"],)
            ).fetchone()
            if trow:
                item["type_kind"] = trow[0]
                item["superclass_fqn"] = trow[1]
                item["line"] = trow[2]
        elif row["ref_kind"] == "method":
            mrow = cur.execute(
                """SELECT m.signature, m.return_type_name, m.start_line, t.fqn
                   FROM methods m JOIN types t ON t.id = m.type_id WHERE m.id=?""",
                (row["ref_id"],),
            ).fetchone()
            if mrow:
                item["signature"] = mrow[0]
                item["return_type"] = mrow[1]
                item["line"] = mrow[2]
                item["owner_fqn"] = mrow[3]
                item["used_by"] = _callers_of(cur, row["ref_id"])
        else:  # file: a raw-text hit (local var, string literal, comment, ...)
            item["classes"] = [
                r[0] for r in cur.execute("SELECT fqn FROM types WHERE file_id=?", (row["ref_id"],))
            ]
            item["matches"] = _matching_lines(row["path"], _tokens(term))
            for m in item["matches"]:
                enclosing = _enclosing_method(cur, row["ref_id"], m["line"])
                if enclosing:
                    method_id, owner_fqn, signature = enclosing
                    m["in_method"] = f"{owner_fqn}#{signature}"
                    m["used_by"] = _callers_of(cur, method_id)
        results.append(item)
    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="Path to the SQLite index")
    parser.add_argument("term", help="Search term (class/method name, prefix-matched)")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    for item in search(args.db, args.term, args.limit):
        if item["kind"] == "type":
            print(f"[{item.get('type_kind', 'type')}] {item['fqn']}  ({item['path']}:{item.get('line')})")
        elif item["kind"] == "method":
            print(f"[method] {item['owner_fqn']}#{item['signature']}  ({item['path']}:{item.get('line')})")
            used_by = item.get("used_by") or []
            if used_by:
                print(f"    genutzt von: {', '.join(used_by)}")
            else:
                print("    genutzt von: (kein Aufrufer im indexierten Repo gefunden)")
        else:
            classes = ", ".join(item.get("classes", [])) or "(keine Klasse -- z.B. Kommentar/Import-Bereich)"
            print(f"[text] {item['path']}")
            print(f"    Klassen: {classes}")
            for m in item.get("matches", []):
                print(f"    {m['line']}: {m['text']}")
                if m.get("in_method"):
                    print(f"        in Methode: {m['in_method']}")
                    if m.get("used_by"):
                        print(f"        genutzt von: {', '.join(m['used_by'])}")


if __name__ == "__main__":
    main()
