"""Build (or rebuild) the SQLite index for a Java source tree.

Usage:
    python -m javaindex.build /path/to/repo --db index.sqlite

Re-run this any time the source changes -- there is no incremental update,
the database is simply dropped and rebuilt from scratch each time.
"""

import argparse
import os
import sys
import time

from .parse import parse_file, iter_all_types
from .registry import build_registry
from .resolver import resolve_hierarchy, build_scope, resolve_method_body
from .schema import init_db

# text/URLs are often externalized here instead of living in .java sources --
# no parsing, just raw full-text indexing so search still finds them
RESOURCE_EXTENSIONS = (".properties", ".xml", ".yml", ".yaml")

_PROGRESS_MIN_INTERVAL = 0.15  # seconds -- don't hammer the terminal on fast loops
_last_progress_at = [0.0]


def _progress(msg, force=False):
    """Overwrite the current terminal line -- avoids scrolling the terminal
    to death over a 100k-file run. No-op when stdout isn't a live terminal
    (redirected to a file/CI log), where \\r would just leave junk."""
    if not sys.stdout.isatty():
        return
    now = time.time()
    if not force and (now - _last_progress_at[0]) < _PROGRESS_MIN_INTERVAL:
        return
    _last_progress_at[0] = now
    width = 100
    sys.stdout.write("\r" + msg[:width].ljust(width))
    sys.stdout.flush()


def _progress_done():
    if sys.stdout.isatty():
        sys.stdout.write("\r" + " " * 100 + "\r")
        sys.stdout.flush()


def _method_signature(method):
    params = ",".join(p.type_name or "?" for p in method.params)
    return f"{method.name}({params})"


def _scan_files(repo_root, verbose):
    """Single directory walk for both .java and resource files -- avoids
    doing five separate recursive globs over a possibly slow/networked tree."""
    java_files = []
    resource_files = []
    seen = 0
    for dirpath, _dirnames, filenames in os.walk(repo_root):
        for name in filenames:
            seen += 1
            if verbose:
                _progress(f"scanning: {seen} files seen ({len(java_files)} .java, {len(resource_files)} resource)")
            lower = name.lower()
            if lower.endswith(".java"):
                java_files.append(os.path.join(dirpath, name))
            elif lower.endswith(RESOURCE_EXTENSIONS):
                resource_files.append(os.path.join(dirpath, name))
    if verbose:
        _progress_done()
    return sorted(java_files), sorted(resource_files)


def build_index(repo_root, db_path, verbose=True):
    java_files, resource_files = _scan_files(repo_root, verbose)
    if verbose:
        print(f"found {len(java_files)} .java files under {repo_root}")
        print(f"found {len(resource_files)} resource file(s) ({', '.join(RESOURCE_EXTENSIONS)}) under {repo_root}")

    parsed_files = []
    errors = []
    total = len(java_files)
    for i, path in enumerate(java_files, start=1):
        if verbose:
            _progress(f"parsing {i}/{total}: {os.path.basename(path)}")
        pf, err = parse_file(path)
        if pf is None:
            errors.append((path, err or "unknown error"))
        else:
            parsed_files.append(pf)
    if verbose:
        _progress_done()
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
    total_methods = len(method_id_by_obj)
    methods_done = 0
    for pf in parsed_files:
        for t in iter_all_types(pf.types):
            type_id = type_id_by_fqn[t.fqn]
            for m in t.methods:
                methods_done += 1
                if verbose:
                    _progress(f"resolving calls: {methods_done}/{total_methods} methods ({t.name}#{m.name})")
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
    if verbose:
        _progress_done()

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

    # also index full file content -- catches local var names, string
    # literals, comments, anything class/method names alone would miss
    for pf in parsed_files:
        file_id = file_id_by_path[pf.path]
        cur.execute(
            "INSERT INTO search(fqn, name, kind, path, ref_id, ref_kind, content) VALUES (?, ?, 'file', ?, ?, 'file', ?)",
            (pf.path, os.path.basename(pf.path), pf.path, file_id, "\n".join(pf.source_lines)),
        )

    # resource files (properties/xml/yaml, ...) aren't Java and aren't parsed,
    # but a text/URL externalized there should still turn up in search
    resource_count = 0
    for i, path in enumerate(resource_files, start=1):
        if verbose:
            _progress(f"indexing resources {i}/{len(resource_files)}: {os.path.basename(path)}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue
        cur.execute("INSERT INTO files(path, package) VALUES (?, NULL)", (path,))
        file_id = cur.lastrowid
        cur.execute(
            "INSERT INTO search(fqn, name, kind, path, ref_id, ref_kind, content) VALUES (?, ?, 'resource', ?, ?, 'file', ?)",
            (path, os.path.basename(path), path, file_id, content),
        )
        resource_count += 1
    if verbose:
        _progress_done()

    conn.commit()

    if verbose:
        print(f"indexed {len(type_id_by_fqn)} types, {len(method_id_by_obj)} methods, {resource_count} resource file(s)")
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
