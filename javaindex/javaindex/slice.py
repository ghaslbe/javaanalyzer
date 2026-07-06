"""Given a seed class, walk the call graph / type hierarchy N hops out and
bundle the relevant source files into one blob -- sized to hand to a local
LLM together with a short relationship summary.

CLI:
    python -m javaindex.slice index.sqlite FunnelDynamicController --depth 2 --out slice.txt
"""

import argparse
import sqlite3


def resolve_seed(cur, seed):
    """Returns (type_id, candidates). Exactly one of them is truthy."""
    row = cur.execute("SELECT id FROM types WHERE fqn=?", (seed,)).fetchone()
    if row:
        return row[0], None

    rows = cur.execute("SELECT id, fqn FROM types WHERE name=?", (seed,)).fetchall()
    if len(rows) == 1:
        return rows[0][0], None
    if len(rows) > 1:
        return None, [r[1] for r in rows]

    rows = cur.execute("SELECT id, fqn FROM types WHERE fqn LIKE ?", (f"%{seed}%",)).fetchall()
    if len(rows) == 1:
        return rows[0][0], None
    return None, [r[1] for r in rows][:20]


def _methods_of(cur, type_id):
    return [r[0] for r in cur.execute("SELECT id FROM methods WHERE type_id=?", (type_id,))]


def _neighbors(cur, type_id):
    """One hop of (related_type_id, relation, detail) from type_id."""
    neighbors = []
    fqn, superclass_fqn, outer_type_id = cur.execute(
        "SELECT fqn, superclass_fqn, outer_type_id FROM types WHERE id=?", (type_id,)
    ).fetchone()

    if outer_type_id:
        (outer_fqn,) = cur.execute("SELECT fqn FROM types WHERE id=?", (outer_type_id,)).fetchone()
        neighbors.append((outer_type_id, "nested_in", outer_fqn))
    for nested_id, nested_fqn in cur.execute("SELECT id, fqn FROM types WHERE outer_type_id=?", (type_id,)):
        neighbors.append((nested_id, "contains_nested", nested_fqn))

    if superclass_fqn:
        row = cur.execute("SELECT id FROM types WHERE fqn=?", (superclass_fqn,)).fetchone()
        if row:
            neighbors.append((row[0], "extends", superclass_fqn))

    for sub_id, sub_fqn in cur.execute("SELECT id, fqn FROM types WHERE superclass_fqn=?", (fqn,)):
        neighbors.append((sub_id, "extended_by", sub_fqn))

    for (iface_fqn,) in cur.execute(
        "SELECT interface_fqn FROM type_implements WHERE type_id=? AND interface_fqn IS NOT NULL", (type_id,)
    ):
        row = cur.execute("SELECT id FROM types WHERE fqn=?", (iface_fqn,)).fetchone()
        if row:
            neighbors.append((row[0], "implements", iface_fqn))

    for impl_id, impl_fqn in cur.execute(
        """SELECT t.id, t.fqn FROM type_implements ti JOIN types t ON t.id = ti.type_id
           WHERE ti.interface_fqn=?""",
        (fqn,),
    ):
        neighbors.append((impl_id, "implemented_by", impl_fqn))

    method_ids = _methods_of(cur, type_id)
    if method_ids:
        placeholders = ",".join("?" * len(method_ids))

        for callee_method_id, callee_name in cur.execute(
            f"""SELECT callee_method_id, callee_name FROM calls
                WHERE caller_method_id IN ({placeholders}) AND callee_method_id IS NOT NULL""",
            method_ids,
        ):
            callee_type_id, callee_type_fqn = cur.execute(
                "SELECT t.id, t.fqn FROM methods m JOIN types t ON t.id = m.type_id WHERE m.id=?",
                (callee_method_id,),
            ).fetchone()
            if callee_type_id != type_id:
                neighbors.append((callee_type_id, "calls", f"{callee_type_fqn}.{callee_name}"))

        for (caller_method_id,) in cur.execute(
            f"SELECT DISTINCT caller_method_id FROM calls WHERE callee_method_id IN ({placeholders})",
            method_ids,
        ):
            caller_type_id, caller_type_fqn = cur.execute(
                "SELECT t.id, t.fqn FROM methods m JOIN types t ON t.id = m.type_id WHERE m.id=?",
                (caller_method_id,),
            ).fetchone()
            if caller_type_id != type_id:
                neighbors.append((caller_type_id, "called_by", caller_type_fqn))

    return neighbors


def collect_neighborhood(cur, seed_id, depth):
    """BFS over hierarchy + call graph. Returns (type_ids, edges, id_to_fqn)."""
    visited = {seed_id}
    edges = []  # (from_id, relation, to_id, detail)
    frontier = [seed_id]
    for _ in range(depth):
        next_frontier = []
        for tid in frontier:
            for nid, relation, detail in _neighbors(cur, tid):
                edges.append((tid, relation, nid, detail))
                if nid not in visited:
                    visited.add(nid)
                    next_frontier.append(nid)
        frontier = next_frontier
        if not frontier:
            break

    id_to_fqn = {}
    for tid in visited:
        (fqn,) = cur.execute("SELECT fqn FROM types WHERE id=?", (tid,)).fetchone()
        id_to_fqn[tid] = fqn
    return visited, edges, id_to_fqn


def render_summary(seed_id, edges, id_to_fqn):
    lines = [f"Seed: {id_to_fqn[seed_id]}", ""]
    seen = set()
    for from_id, relation, to_id, detail in edges:
        key = (from_id, relation, to_id, detail)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{id_to_fqn[from_id]} --{relation}--> {id_to_fqn.get(to_id, detail)}")
    return "\n".join(lines)


def render_bundle(cur, type_ids):
    file_ids = set()
    for tid in type_ids:
        (file_id,) = cur.execute("SELECT file_id FROM types WHERE id=?", (tid,)).fetchone()
        file_ids.add(file_id)

    parts = []
    for file_id in sorted(file_ids):
        (path,) = cur.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:
            content = f"<could not read file: {exc}>"
        parts.append(f"===== {path} =====\n{content}")
    return "\n\n".join(parts)


def build_slice(db_path, seed, depth=2):
    """Returns dict with summary/bundle text, or {'candidates': [...]} if the
    seed is ambiguous / not found."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    seed_id, candidates = resolve_seed(cur, seed)
    if seed_id is None:
        conn.close()
        return {"candidates": candidates or []}

    type_ids, edges, id_to_fqn = collect_neighborhood(cur, seed_id, depth)
    summary = render_summary(seed_id, edges, id_to_fqn)
    bundle = render_bundle(cur, type_ids)
    conn.close()
    return {"seed": id_to_fqn[seed_id], "types": sorted(id_to_fqn.values()), "summary": summary, "bundle": bundle}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="Path to the SQLite index")
    parser.add_argument("seed", help="Class name or FQN to start from")
    parser.add_argument("--depth", type=int, default=2, help="How many hops to follow (default: 2)")
    parser.add_argument("--out", help="Write the bundled source here (summary goes to stdout either way)")
    args = parser.parse_args()

    result = build_slice(args.db, args.seed, args.depth)
    if "candidates" in result:
        if result["candidates"]:
            print(f"'{args.seed}' is ambiguous, candidates:")
            for c in result["candidates"]:
                print(f"  {c}")
        else:
            print(f"no match for '{args.seed}'")
        return

    print(result["summary"])
    print(f"\n{len(result['types'])} type(s) in this slice")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(result["bundle"])
        print(f"bundle written to {args.out}")
    else:
        print("\n--- bundle ---\n")
        print(result["bundle"])


if __name__ == "__main__":
    main()
