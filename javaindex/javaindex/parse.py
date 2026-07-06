"""Parse a single .java file into plain-data facts using javalang.

No symbol resolution happens here -- this module only extracts what is
written in the source (names as written, not FQNs). Cross-file resolution
happens later in registry.py / resolver.py once every file has been parsed.
"""

from dataclasses import dataclass, field
from typing import Optional

import javalang


def _type_name(type_node):
    """Best-effort simple/qualified name of a javalang Type node."""
    if type_node is None:
        return None
    name = getattr(type_node, "name", None)
    sub = getattr(type_node, "sub_type", None)
    if sub is not None:
        return f"{name}.{_type_name(sub)}"
    return name


def _modifiers(node):
    return sorted(getattr(node, "modifiers", None) or [])


@dataclass
class ParsedParam:
    name: str
    type_name: Optional[str]


@dataclass
class ParsedMethod:
    name: str
    params: list
    return_type_name: Optional[str]
    modifiers: list
    start_line: Optional[int]
    node: object  # original javalang node, kept for call-graph pass


@dataclass
class ParsedField:
    name: str
    type_name: Optional[str]
    modifiers: list


@dataclass
class ParsedType:
    name: str
    kind: str  # class | interface | enum
    extends_name: Optional[str]
    implements_names: list
    modifiers: list
    start_line: Optional[int]
    fields: list = field(default_factory=list)
    methods: list = field(default_factory=list)
    nested: list = field(default_factory=list)
    outer: "ParsedType" = None


@dataclass
class ParsedFile:
    path: str
    package: Optional[str]
    imports: list  # list of (dotted_path, is_static, is_wildcard)
    types: list  # top-level ParsedType list
    source_lines: list = field(default_factory=list)


def _collect_body(body, outer=None):
    """Split a class/interface/enum body into fields, methods, nested types."""
    fields_out = []
    methods_out = []
    nested_out = []
    for member in body:
        if isinstance(member, javalang.tree.FieldDeclaration):
            type_name = _type_name(member.type)
            mods = _modifiers(member)
            for decl in member.declarators:
                fields_out.append(ParsedField(decl.name, type_name, mods))
        elif isinstance(member, javalang.tree.ConstructorDeclaration):
            params = [ParsedParam(p.name, _type_name(p.type)) for p in member.parameters]
            line = member.position.line if member.position else None
            methods_out.append(ParsedMethod("<init>", params, None, _modifiers(member), line, member))
        elif isinstance(member, javalang.tree.MethodDeclaration):
            params = [ParsedParam(p.name, _type_name(p.type)) for p in member.parameters]
            line = member.position.line if member.position else None
            methods_out.append(
                ParsedMethod(member.name, params, _type_name(member.return_type), _modifiers(member), line, member)
            )
        elif isinstance(
            member,
            (
                javalang.tree.ClassDeclaration,
                javalang.tree.InterfaceDeclaration,
                javalang.tree.EnumDeclaration,
                javalang.tree.AnnotationDeclaration,
            ),
        ):
            nested_out.append(_parse_type_decl(member, outer=outer))
    return fields_out, methods_out, nested_out


def _parse_type_decl(node, outer=None):
    if isinstance(node, javalang.tree.AnnotationDeclaration):
        # @interface Foo -- no extends/implements, and its body is
        # AnnotationMethod nodes we don't otherwise handle; still register
        # the type itself so it doesn't blow up as an unhandled "class"
        kind = "annotation"
        extends_name = None
        implements_names = []
    elif isinstance(node, javalang.tree.InterfaceDeclaration):
        kind = "interface"
        extends_name = None
        implements_names = [_type_name(t) for t in (node.extends or [])]
    elif isinstance(node, javalang.tree.EnumDeclaration):
        kind = "enum"
        extends_name = None
        implements_names = [_type_name(t) for t in (node.implements or [])]
    else:
        kind = "class"
        extends_name = _type_name(node.extends) if node.extends else None
        implements_names = [_type_name(t) for t in (node.implements or [])]

    line = node.position.line if node.position else None
    ptype = ParsedType(
        name=node.name,
        kind=kind,
        extends_name=extends_name,
        implements_names=implements_names,
        modifiers=_modifiers(node),
        start_line=line,
        outer=outer,
    )
    body = getattr(node, "body", None) or []
    fields_out, methods_out, nested_out = _collect_body(body, outer=ptype)
    ptype.fields = fields_out
    ptype.methods = methods_out
    ptype.nested = nested_out
    return ptype


def parse_file(path):
    """Parse one .java file. Returns (ParsedFile, None) or (None, error)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError as exc:
        return None, f"could not read file: {exc}"
    try:
        tree = javalang.parse.parse(src)
        package = tree.package.name if tree.package else None
        imports = [(imp.path, bool(imp.static), bool(imp.wildcard)) for imp in tree.imports]
        types = [_parse_type_decl(t) for t in tree.types]
    except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError) as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 -- one bad file must never abort a 100k-file build
        return None, f"unexpected parser error: {exc!r}"

    return ParsedFile(path=path, package=package, imports=imports, types=types, source_lines=src.splitlines()), None


def iter_all_types(parsed_types):
    """Flatten a ParsedType forest (incl. nested types) into a flat list."""
    out = []
    for t in parsed_types:
        out.append(t)
        out.extend(iter_all_types(t.nested))
    return out
