"""Cross-file symbol registry: best-effort simple-name -> FQN resolution.

There is no compiler and no classpath here, so this is deliberately a set of
heuristics tried in order of confidence:

1. nested/inner type of the current type (or one of its outer types)
2. an explicit import in the current file
3. a type in the same package
4. a type reachable through a wildcard (`import foo.bar.*`) import
5. last resort: if the simple name is unique across the *whole* indexed
   repo, use that one match (flagged as a guess)

Anything else (JDK/library types, or ambiguous names) stays unresolved --
that's fine, we only need to understand *our own* code well.
"""

from dataclasses import dataclass, field

from .parse import iter_all_types


@dataclass
class TypeInfo:
    fqn: str
    simple_name: str
    kind: str
    package: str
    path: str
    outer_fqn: str
    parsed: object  # the ParsedType


@dataclass
class FileInfo:
    package: str
    imports: dict  # simple_name -> fqn (explicit imports)
    wildcard_packages: list  # list of package prefixes from `import x.y.*`
    source_lines: list


class Registry:
    def __init__(self):
        self.by_fqn = {}  # fqn -> TypeInfo -- last one wins on a duplicate FQN
        self.by_simple = {}  # simple_name -> [fqn, ...]
        self.files = {}  # path -> FileInfo
        self.duplicate_fqns = []  # (fqn, first_path, duplicate_path) -- same FQN declared more than once

    def _assign_fqn(self, ptype, package, path, outer_fqn=None):
        fqn = f"{outer_fqn}.{ptype.name}" if outer_fqn else (f"{package}.{ptype.name}" if package else ptype.name)
        ptype.fqn = fqn
        ptype.file_path = path  # set unconditionally -- resolve_hierarchy() also sets this for the
        # by_fqn "winner", but every type (incl. FQN duplicates that lose the by_fqn slot) needs it
        existing = self.by_fqn.get(fqn)
        if existing is not None:
            self.duplicate_fqns.append((fqn, existing.path, path))
        info = TypeInfo(fqn=fqn, simple_name=ptype.name, kind=ptype.kind, package=package, path=path, outer_fqn=outer_fqn, parsed=ptype)
        self.by_fqn[fqn] = info
        self.by_simple.setdefault(ptype.name, []).append(fqn)
        for nested in ptype.nested:
            self._assign_fqn(nested, package, path, outer_fqn=fqn)

    def add_file(self, parsed_file):
        explicit = {}
        wildcards = []
        for path, is_static, is_wildcard in parsed_file.imports:
            if is_wildcard:
                # `import static Foo.*` -> ignore (member imports, not types)
                if not is_static:
                    wildcards.append(path)
                continue
            simple = path.rsplit(".", 1)[-1]
            if not is_static:
                explicit[simple] = path
        self.files[parsed_file.path] = FileInfo(
            package=parsed_file.package,
            imports=explicit,
            wildcard_packages=wildcards,
            source_lines=parsed_file.source_lines,
        )
        for top in parsed_file.types:
            self._assign_fqn(top, parsed_file.package, parsed_file.path)

    def all_type_infos(self):
        return list(self.by_fqn.values())

    def resolve(self, name, *, file_path=None, current_type_fqn=None):
        """Resolve a simple/qualified type name as written in source to a FQN.

        Returns (fqn_or_none, confidence) where confidence is one of:
        'nested', 'import', 'same_package', 'wildcard', 'unique_guess', None
        """
        if not name:
            return None, None

        # a qualified reference like Outer.Inner or a.b.C -- try the first
        # segment for resolution, keep the rest as a suffix.
        head = name.split(".", 1)[0]
        suffix = name[len(head):]  # '' or '.Rest'

        # (a) nested type of current type or any of its outer types
        outer_fqn = current_type_fqn
        while outer_fqn:
            candidate = f"{outer_fqn}.{head}"
            if candidate in self.by_fqn:
                return candidate + suffix, "nested"
            info = self.by_fqn.get(outer_fqn)
            outer_fqn = info.outer_fqn if info else None

        finfo = self.files.get(file_path) if file_path else None

        # (b) explicit import
        if finfo and head in finfo.imports:
            return finfo.imports[head] + suffix, "import"

        # (c) same package
        if finfo and finfo.package:
            candidate = f"{finfo.package}.{head}"
            if candidate in self.by_fqn:
                return candidate + suffix, "same_package"

        # (d) wildcard imports
        if finfo:
            matches = [f"{pkg}.{head}" for pkg in finfo.wildcard_packages if f"{pkg}.{head}" in self.by_fqn]
            if len(matches) == 1:
                return matches[0] + suffix, "wildcard"

        # (e) globally unique simple name
        candidates = self.by_simple.get(head)
        if candidates and len(candidates) == 1:
            return candidates[0] + suffix, "unique_guess"

        return None, None


def build_registry(parsed_files):
    registry = Registry()
    for pf in parsed_files:
        registry.add_file(pf)
    return registry
