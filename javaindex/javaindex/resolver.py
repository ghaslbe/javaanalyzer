"""Best-effort call-graph resolution.

No type checker is available, so this walks the source-level heuristics:
declared types of fields/params/locals give us a receiver type for
`x.method()`, and we chase `.foo().bar()` chains by re-resolving the return
type of whatever we matched at each step. Whatever we can't pin down (calls
on JDK/library types with unknown internals, ambiguous overloads, calls
after a mid-chain field access) is stored as an unresolved call -- still
searchable by name, just without a resolved target.
"""

import re

import javalang

from .parse import _type_name

# javalang has a quirk where `this.field.method()` loses its qualifier
# entirely (splits into an unlinked MemberReference + a bare MethodInvocation)
# while `obj.field.method()` is fine (single node, qualifier="obj.field").
# We patch that up by peeking at the raw source text right before the call.
_QUALIFIER_TAIL_RE = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*)\.\s*$")

_CALL_NODE_TYPES = (
    javalang.tree.MethodInvocation,
    javalang.tree.ClassCreator,
    javalang.tree.SuperMethodInvocation,
    javalang.tree.SuperConstructorInvocation,
    javalang.tree.ExplicitConstructorInvocation,
)


def _filter_any(root, types):
    """javalang's Node.filter() only accepts a single type, not a tuple --
    so fan out over each type and merge."""
    for t in types:
        for path, node in root.filter(t):
            yield path, node


def resolve_hierarchy(registry):
    """Set file_path / superclass_fqn / implements_fqns on every parsed type."""
    for info in registry.all_type_infos():
        t = info.parsed
        t.file_path = info.path
        if t.extends_name:
            fqn, _ = registry.resolve(t.extends_name, file_path=info.path, current_type_fqn=info.fqn)
            t.superclass_fqn = fqn
        else:
            t.superclass_fqn = None
        implements_fqns = []
        for iname in t.implements_names:
            ifqn, _ = registry.resolve(iname, file_path=info.path, current_type_fqn=info.fqn)
            implements_fqns.append(ifqn or iname)
        t.implements_fqns = implements_fqns


def _chained_away_ids(root):
    """Node ids that only appear as a *continuation* inside another node's
    `.selectors` -- these are walked as part of their chain head, not on
    their own."""
    away = set()
    for _, node in _filter_any(root, _CALL_NODE_TYPES + (javalang.tree.MemberReference,)):
        for sel in getattr(node, "selectors", None) or []:
            away.add(id(sel))
    return away


def build_scope(ptype, method, registry):
    """name -> declared type name, for params/locals/fields (incl. supertype
    chain within the index, and outer types for nested classes)."""
    scope = {}

    def add_fields_of(t, seen):
        if t is None or t.fqn in seen:
            return
        seen.add(t.fqn)
        for f in t.fields:
            scope.setdefault(f.name, f.type_name)
        sup_fqn = getattr(t, "superclass_fqn", None)
        if sup_fqn:
            sup_info = registry.by_fqn.get(sup_fqn)
            if sup_info:
                add_fields_of(sup_info.parsed, seen)

    chain = []
    t = ptype
    while t is not None:
        chain.append(t)
        t = t.outer
    for t in reversed(chain):
        add_fields_of(t, set())

    for p in method.params:
        scope[p.name] = p.type_name

    for _, decl in method.node.filter(javalang.tree.VariableDeclaration):
        type_name = _type_name(decl.type)
        for d in decl.declarators:
            scope[d.name] = type_name

    return scope


def _find_method(registry, type_fqn, member_name, seen=None):
    if not type_fqn:
        return None, None
    seen = seen if seen is not None else set()
    if type_fqn in seen:
        return None, None
    seen.add(type_fqn)
    info = registry.by_fqn.get(type_fqn)
    if not info:
        return None, None
    for meth in info.parsed.methods:
        if meth.name == member_name:
            return meth, type_fqn
    return _find_method(registry, getattr(info.parsed, "superclass_fqn", None), member_name, seen)


def _return_type_fqn(registry, method, owning_type_fqn):
    if method is None or not method.return_type_name:
        return None
    owner = registry.by_fqn.get(owning_type_fqn)
    if not owner:
        return None
    fqn, _ = registry.resolve(method.return_type_name, file_path=owner.path, current_type_fqn=owner.fqn)
    return fqn


def _find_field(registry, type_fqn, field_name, seen=None):
    if not type_fqn:
        return None, None
    seen = seen if seen is not None else set()
    if type_fqn in seen:
        return None, None
    seen.add(type_fqn)
    info = registry.by_fqn.get(type_fqn)
    if not info:
        return None, None
    for f in info.parsed.fields:
        if f.name == field_name:
            return f, type_fqn
    return _find_field(registry, getattr(info.parsed, "superclass_fqn", None), field_name, seen)


def _field_type_fqn(registry, field, owning_type_fqn):
    if field is None or not field.type_name:
        return None
    owner = registry.by_fqn.get(owning_type_fqn)
    if not owner:
        return None
    fqn, _ = registry.resolve(field.type_name, file_path=owner.path, current_type_fqn=owner.fqn)
    return fqn


def _peek_qualifier(registry, file_path, position):
    """Best-effort recovery of a qualifier javalang failed to attach, by
    looking at the source text immediately before the call token."""
    if not position:
        return None
    finfo = registry.files.get(file_path)
    if not finfo or not finfo.source_lines:
        return None
    line_idx = position.line - 1
    if not (0 <= line_idx < len(finfo.source_lines)):
        return None
    prefix = finfo.source_lines[line_idx][: position.column]
    m = _QUALIFIER_TAIL_RE.search(prefix)
    return m.group(1) if m else None


def _resolve_receiver_type(ptype, qualifier, registry, scope):
    """Resolve a (possibly dotted) qualifier like '', 'this', 'obj',
    'this.field', 'obj.fieldA.fieldB' to the FQN of the receiver type."""
    if not qualifier:
        return ptype.fqn
    segments = qualifier.split(".")
    head = segments[0]
    if head == "this":
        current_fqn = ptype.fqn
    elif head == "super":
        current_fqn = getattr(ptype, "superclass_fqn", None)
    else:
        var_type = scope.get(head)
        if var_type:
            current_fqn, _ = registry.resolve(var_type, file_path=ptype.file_path, current_type_fqn=ptype.fqn)
        else:
            current_fqn, _ = registry.resolve(head, file_path=ptype.file_path, current_type_fqn=ptype.fqn)

    for seg in segments[1:]:
        if current_fqn is None:
            return None
        fld, owning_fqn = _find_field(registry, current_fqn, seg)
        current_fqn = _field_type_fqn(registry, fld, owning_fqn) if fld else None

    return current_fqn


def resolve_method_body(ptype, method, registry, scope):
    """Returns (calls, instantiation_refs) for one method body.

    calls: list of dicts {callee_name, callee_type_fqn, callee_method, resolved, line}
    instantiation_refs: list of dicts {referenced_fqn, kind='instantiation'}
    """
    calls = []
    instantiations = []
    away_ids = _chained_away_ids(method.node)

    for _, node in _filter_any(method.node, _CALL_NODE_TYPES):
        if id(node) in away_ids:
            continue

        line = node.position.line if node.position else None

        if isinstance(node, javalang.tree.ClassCreator):
            type_name = _type_name(node.type)
            fqn, _ = registry.resolve(type_name, file_path=ptype.file_path, current_type_fqn=ptype.fqn)
            instantiations.append({"referenced_fqn": fqn or type_name, "kind": "instantiation"})
            current_type_fqn = fqn
        else:
            if isinstance(node, javalang.tree.SuperMethodInvocation):
                current_type_fqn = getattr(ptype, "superclass_fqn", None)
                member = node.member
            elif isinstance(node, javalang.tree.SuperConstructorInvocation):
                current_type_fqn = getattr(ptype, "superclass_fqn", None)
                member = "<init>"
            elif isinstance(node, javalang.tree.ExplicitConstructorInvocation):
                current_type_fqn = ptype.fqn
                member = "<init>"
            else:
                qualifier = (node.qualifier or "").strip()
                member = node.member
                if not qualifier:
                    qualifier = _peek_qualifier(registry, ptype.file_path, node.position) or ""
                current_type_fqn = _resolve_receiver_type(ptype, qualifier, registry, scope)

            target_method, owning_fqn = _find_method(registry, current_type_fqn, member)
            calls.append(
                {
                    "callee_name": member,
                    "callee_type_fqn": current_type_fqn,
                    "callee_method": target_method,
                    "resolved": target_method is not None,
                    "line": line,
                }
            )
            current_type_fqn = _return_type_fqn(registry, target_method, owning_fqn) if target_method else None

        # walk the flat rest-of-chain, propagating the receiver type as far
        # as we can resolve it; a MemberReference (field access) mid-chain
        # breaks the chain since we don't resolve field types here.
        for sel in getattr(node, "selectors", None) or []:
            if isinstance(sel, javalang.tree.MethodInvocation):
                sel_line = sel.position.line if sel.position else line
                target_method, owning_fqn = _find_method(registry, current_type_fqn, sel.member)
                calls.append(
                    {
                        "callee_name": sel.member,
                        "callee_type_fqn": current_type_fqn,
                        "callee_method": target_method,
                        "resolved": target_method is not None,
                        "line": sel_line,
                    }
                )
                current_type_fqn = _return_type_fqn(registry, target_method, owning_fqn) if target_method else None
            else:
                current_type_fqn = None  # field access or array/other selector: give up on the chain type

    return calls, instantiations
