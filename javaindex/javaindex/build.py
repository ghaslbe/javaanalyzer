"""Build (or rebuild) the SQLite index for a Java source tree.

Usage:
    python -m javaindex.build /path/to/repo --db index.sqlite

Re-run this any time the source changes -- there is no incremental update,
the database is simply dropped and rebuilt from scratch each time.
"""

import argparse
import glob
import os
import sys
import time

from .parse import parse_file, iter_all_types
from .registry import build_registry
from .resolver import resolve_hierarchy, build_scope, resolve_method_body
from .schema import init_db


def _method_signature(method):
    params = ",".join(p.type_name or "?" for p in method.params)
    return f"{method.name}({params})"


def build_index(repo_root, db_path, verbose=True):
    java_files = sorted(glob.glob(os.path.join(repo_root, "**", "*.java"), recursive=True))
    if verbose:
        print(f"found {len(java_files)} .java files under {repo_root}")

    parsed_files = []
    errors = []
    for path in java_files:
        pf, err = parse_file(path)
        if err:
            errors.append((path, err))
        else:
            parsed_files.append(pf)
    if errors and verbose:
        print(f"skipped {len(errors)} file(s) that failed to parse:")
        for path, err in errors[:20]:
            print(f"  {path}: {err.splitlines()[0] if err else err}")

    registry = build_registry(parsed_files)
    resolve_hierarchy(registry)

    conn = init_db(db_path)
    cur = conn.cursor()

    file_id_by_path = {}
    for pf in parsed_files:
        cur.execute("INSERT INTO files(path, package) VALUES (?, ?)", (pf.path, pf.package))
        file_id_by_path[pf.path] = cur.lastrowid

    type_id_by_fqn = {}
    method_id_by_obj = {}

    # pass 1: types, fields, methods, method_params, type_implements
    for pf in parsed_files:
        file_id = file_id_by_path[pf.path]
        for t in iter_all_types(pf.types):
            outer_id = type_id_by_fqn.get(t.outer.fqn) if t.outer else None
            cur.execute(
                """INSERT INTO types
                   (file_id, name, fqn, kind, outer_type_id, superclass_name, superclass_fqn, modifiers, start_line)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    file_id,
                    t.name,
                    t.fqn,
                    t.kind,
                    outer_id,
                    t.extends_name,
                    t.superclass_fqn,
                    ",".join(t.modifiers),
                    t.start_line,
                ),
            )
            type_id_by_fqn[t.fqn] = cur.lastrowid

    # second sub-pass once every type has a row (outer_type_id above only works because
    # iter_all_types visits outers before nested -- implements/fields/methods need the
    # full type_id_by_fqn map so they can be done right after, per type)
    for pf in parsed_files:
        for t in iter_all_types(pf.types):
            type_id = type_id_by_fqn[t.fqn]

            for iname, ifqn in zip(t.implements_names, t.implements_fqns):
                cur.execute(
                    "INSERT INTO type_implements(type_id, interface_name, interface_fqn) VALUES (?, ?, ?)",
                    (type_id, iname, ifqn),
                )

            for f in t.fields:
                fqn, _ = registry.resolve(f.type_name, file_path=t.file_path, current_type_fqn=t.fqn)
                cur.execute(
                    "INSERT INTO fields(type_id, name, field_type_name, field_type_fqn, modifiers) VALUES (?, ?, ?, ?, ?)",
                    (type_id, f.name, f.type_name, fqn, ",".join(f.modifiers)),
                )
                if fqn:
                    cur.execute(
                        "INSERT INTO type_refs(type_id, method_id, referenced_fqn, kind) VALUES (?, NULL, ?, 'field_type')",
                        (type_id, fqn),
                    )

            for m in t.methods:
                cur.execute(
                    """INSERT INTO methods(type_id, name, signature, return_type_name, modifiers, start_line)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (type_id, m.name, _method_signature(m), m.return_type_name, ",".join(m.modifiers), m.start_line),
                )
                method_id = cur.lastrowid
                method_id_by_obj[id(m)] = method_id

                for i, p in enumerate(m.params):
                    cur.execute(
                        "INSERT INTO method_params(method_id, position, name, param_type_name) VALUES (?, ?, ?, ?)",
                        (method_id, i, p.name, p.type_name),
                    )
                    pfqn, _ = registry.resolve(p.type_name, file_path=t.file_path, current_type_fqn=t.fqn)
                    if pfqn:
                        cur.execute(
                            "INSERT INTO type_refs(type_id, method_id, referenced_fqn, kind) VALUES (?, ?, ?, 'param_type')",
                            (type_id, method_id, pfqn),
                        )

                if m.return_type_name:
                    rfqn, _ = registry.resolve(m.return_type_name, file_path=t.file_path, current_type_fqn=t.fqn)
                    if rfqn:
                        cur.execute(
                            "INSERT INTO type_refs(type_id, method_id, referenced_fqn, kind) VALUES (?, ?, ?, 'return_type')",
                            (type_id, method_id, rfqn),
                        )

    # pass 2: call graph + instantiations, now that every method has a row id
    total_calls = 0
    resolved_calls = 0
    for pf in parsed_files:
        for t in iter_all_types(pf.types):
            type_id = type_id_by_fqn[t.fqn]
            for m in t.methods:
                caller_id = method_id_by_obj[id(m)]
                scope = build_scope(t, m, registry)
                calls, instantiations = resolve_method_body(t, m, registry, scope)
                for c in calls:
                    total_calls += 1
                    callee_method_id = method_id_by_obj.get(id(c["callee_method"])) if c["callee_method"] else None
                    resolved = 1 if callee_method_id is not None else 0
                    resolved_calls += resolved
                    cur.execute(
                        """INSERT INTO calls(caller_method_id, callee_name, callee_type_fqn, callee_method_id, resolved, line)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (caller_id, c["callee_name"], c["callee_type_fqn"], callee_method_id, resolved, c["line"]),
                    )
                for inst in instantiations:
                    cur.execute(
                        "INSERT INTO type_refs(type_id, method_id, referenced_fqn, kind) VALUES (?, ?, ?, 'instantiation')",
                        (type_id, caller_id, inst["referenced_fqn"]),
                    )

    # full-text search index: one row per type, one row per method
    for fqn, type_id in type_id_by_fqn.items():
        info = registry.by_fqn[fqn]
        cur.execute(
            "INSERT INTO search(fqn, name, kind, path, ref_id, ref_kind) VALUES (?, ?, ?, ?, ?, 'type')",
            (fqn, info.simple_name, info.kind, info.path, type_id),
        )
    for pf in parsed_files:
        for t in iter_all_types(pf.types):
            type_id = type_id_by_fqn[t.fqn]
            for m in t.methods:
                method_id = method_id_by_obj[id(m)]
                cur.execute(
                    "INSERT INTO search(fqn, name, kind, path, ref_id, ref_kind) VALUES (?, ?, 'method', ?, ?, 'method')",
                    (f"{t.fqn}#{_method_signature(m)}", m.name, t.file_path, method_id),
                )

    conn.commit()

    if verbose:
        print(f"indexed {len(type_id_by_fqn)} types, {len(method_id_by_obj)} methods")
        print(f"calls: {total_calls} total, {resolved_calls} resolved within the repo ({total_calls - resolved_calls} external/unresolved)")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="Root directory of the Java source tree to index")
    parser.add_argument("--db", default="index.sqlite", help="Path to the SQLite database to (re)create")
    args = parser.parse_args()

    start = time.time()
    build_index(args.repo, args.db)
    print(f"done in {time.time() - start:.1f}s -> {args.db}")


if __name__ == "__main__":
    sys.exit(main())
