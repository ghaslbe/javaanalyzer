"""Full-text search over the index (class/method names, FQNs).

Usable as a library (search()) from the Flask backend, or as a CLI:
    python -m javaindex.search index.sqlite "Funnel"
"""

import argparse
import sqlite3


def _match_query(term):
    term = term.strip()
    if not term:
        return None
    return " ".join(f"{tok}*" for tok in term.replace('"', "").split())


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
        else:
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
        else:
            print(f"[method] {item['owner_fqn']}#{item['signature']}  ({item['path']}:{item.get('line')})")


if __name__ == "__main__":
    main()
