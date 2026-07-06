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


def _callers_with_location(cur, method_id, limit=20):
    """Like _callers_of, but keeps the call site (file/line) so we can show
    a code snippet of the calling code too."""
    rows = cur.execute(
        """SELECT DISTINCT t.fqn, m.signature, c.line, f.path
           FROM calls c
           JOIN methods m ON m.id = c.caller_method_id
           JOIN types t ON t.id = m.type_id
           JOIN files f ON f.id = t.file_id
           WHERE c.callee_method_id = ?
           LIMIT ?""",
        (method_id, limit),
    ).fetchall()
    return [{"fqn": fqn, "signature": sig, "path": path, "line": line} for fqn, sig, line, path in rows]


def _package_of(cur, path):
    row = cur.execute("SELECT package FROM files WHERE path=?", (path,)).fetchone()
    return row[0] if row else None


def _read_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    except OSError:
        return []


def _snippet(path, line, context=5):
    """+/- `context` lines of raw source around `line` (1-indexed)."""
    if not line:
        return []
    lines = _read_lines(path)
    if not lines:
        return []
    start = max(1, line - context)
    end = min(len(lines), line + context)
    return [{"line": n, "text": lines[n - 1].rstrip("\n")} for n in range(start, end + 1)]


def _occurrence(cur, path, class_fqn, method_signature, line, context):
    """Package + class + method + a code snippet around one line -- the
    unit the user actually wants to read to understand 'how does this hang
    together'."""
    return {
        "package": _package_of(cur, path),
        "class": class_fqn,
        "method": method_signature,
        "path": path,
        "line": line,
        "code": _snippet(path, line, context),
    }


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


def search_with_code(db_path, term, context=5, limit=30):
    """Like search(), but for every hit (and every caller of the enclosing
    method) returns package/class/method plus a +/- `context` line code
    snippet -- enough to see how pieces hang together without opening the
    files by hand."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    match = _match_query(term)
    if not match:
        conn.close()
        return []

    rows = cur.execute(
        """SELECT fqn, name, kind, path, ref_id, ref_kind, rank
           FROM search WHERE search MATCH ? ORDER BY rank LIMIT ?""",
        (match, limit),
    ).fetchall()

    results = []
    for row in rows:
        if row["ref_kind"] == "type":
            trow = cur.execute("SELECT start_line FROM types WHERE id=?", (row["ref_id"],)).fetchone()
            line = trow[0] if trow else None
            occurrence = _occurrence(cur, row["path"], row["fqn"], None, line, context)
            results.append({"kind": "type", "occurrence": occurrence, "used_by": []})

        elif row["ref_kind"] == "method":
            signature, line, owner_fqn = cur.execute(
                "SELECT m.signature, m.start_line, t.fqn FROM methods m JOIN types t ON t.id = m.type_id WHERE m.id=?",
                (row["ref_id"],),
            ).fetchone()
            occurrence = _occurrence(cur, row["path"], owner_fqn, signature, line, context)
            used_by = [
                _occurrence(cur, c["path"], c["fqn"], c["signature"], c["line"], context)
                for c in _callers_with_location(cur, row["ref_id"])
            ]
            results.append({"kind": "method", "occurrence": occurrence, "used_by": used_by})

        else:  # file: a raw-text hit -- find the enclosing method (if any) per matching line
            for hit in _matching_lines(row["path"], _tokens(term)):
                enclosing = _enclosing_method(cur, row["ref_id"], hit["line"])
                if enclosing:
                    method_id, owner_fqn, signature = enclosing
                    occurrence = _occurrence(cur, row["path"], owner_fqn, signature, hit["line"], context)
                    used_by = [
                        _occurrence(cur, c["path"], c["fqn"], c["signature"], c["line"], context)
                        for c in _callers_with_location(cur, method_id)
                    ]
                else:
                    occurrence = _occurrence(cur, row["path"], None, None, hit["line"], context)
                    used_by = []
                results.append({"kind": "text", "occurrence": occurrence, "used_by": used_by})

    conn.close()
    return results


def _format_occurrence(occ, indent=""):
    lines = []
    where = f"{occ['class']}#{occ['method']}" if occ["method"] else (occ["class"] or "?")
    lines.append(f"{indent}{where}")
    lines.append(f"{indent}Package: {occ['package']}")
    lines.append(f"{indent}Datei:   {occ['path']}:{occ['line']}")
    for row in occ["code"]:
        marker = ">" if row["line"] == occ["line"] else " "
        lines.append(f"{indent}  {marker} {row['line']:>5}  {row['text']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="Path to the SQLite index")
    parser.add_argument("term", help="Search term (class/method name, prefix-matched)")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--code", action="store_true", help="Show package/class/method + code snippets (+/- --context lines)"
    )
    parser.add_argument("--context", type=int, default=5, help="Lines of context around each hit (default: 5)")
    args = parser.parse_args()

    if args.code:
        for result in search_with_code(args.db, args.term, context=args.context, limit=args.limit):
            print(f"=== [{result['kind']}] ===")
            print(_format_occurrence(result["occurrence"]))
            if result["used_by"]:
                print(f"\n--- genutzt von {len(result['used_by'])} Aufrufer(n) ---")
                for caller in result["used_by"]:
                    print()
                    print(_format_occurrence(caller, indent="  "))
            print()
        return

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
