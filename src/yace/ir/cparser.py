"""
Parse a C header into the **yace** IR

The header describes an FFI boundary in a subset of C99. Any header is parsed,
also one outside the subset: everything that can be represented is, and every
place the header steps outside the subset is reported as a
:class:`yace.ir.diagnostics.Diagnostic`. Nothing is dropped or changed without
one, so the IR of a header outside the subset is usable, and the diagnostics say
what to change for it to be within.

* :class:`.CParser` parses a header into a :class:`yace.ir.model.Model`
* :func:`.c_to_yace` writes the IR and the diagnostics of headers to files
"""

import logging as log
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import clang
from clang.cindex import (
    Config,
    CursorKind,
    Index,
    StorageClass,
    TokenKind,
    TranslationUnit,
    TypeKind,
)
from pydantic import BaseModel

from . import decls, doc, types
from .diagnostics import Diagnostic
from .model import Meta, Model, host_abi

BUILTIN_KINDS = {
    TypeKind.VOID: "void",
    TypeKind.BOOL: "bool",
    TypeKind.CHAR_S: "char",
    TypeKind.CHAR_U: "char",
    TypeKind.SCHAR: "signed char",
    TypeKind.UCHAR: "unsigned char",
    TypeKind.SHORT: "short",
    TypeKind.USHORT: "unsigned short",
    TypeKind.INT: "int",
    TypeKind.UINT: "unsigned int",
    TypeKind.LONG: "long",
    TypeKind.ULONG: "unsigned long",
    TypeKind.LONGLONG: "long long",
    TypeKind.ULONGLONG: "unsigned long long",
    TypeKind.FLOAT: "float",
    TypeKind.DOUBLE: "double",
}

RECORD_KINDS = (CursorKind.STRUCT_DECL, CursorKind.UNION_DECL)

CALLBACK_SUFFIXES = ("_cb", "_callback", "_fn", "_fun", "_func", "_function")

# What a typedef of its own name and its record or enum report a missing doc as
DOCUMENTED = ("struct", "union", "enum", "typedef")

EVAL_BATCH = 200  # macros evaluated per generated translation unit


class Unsupported(Exception):
    """A type that the IR cannot represent; the message says which"""


ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f"}
ESCAPES.update({"v": "\v", "\\": "\\", '"': '"', "'": "'", "?": "?"})


def unescape(text: str) -> str:
    """The value of the body of a C string literal, its escapes decoded; bytes
    that are not UTF-8 are kept as the surrogates of 'surrogateescape'"""

    found = bytearray()
    pos = 0
    for match in re.finditer(r"\\(x[0-9a-fA-F]+|[0-7]{1,3}|.)", text):
        found += text[pos : match.start()].encode()
        esc = match.group(1)
        if esc[0] == "x":
            found.append(int(esc[1:], 16) & 0xFF)
        elif esc[0] in "01234567":
            found.append(int(esc, 8) & 0xFF)
        else:
            found += ESCAPES.get(esc, esc).encode()
        pos = match.end()
    found += text[pos:].encode()
    return found.decode("utf-8", "surrogateescape")


CXX_KEYWORDS = set(
    "alignas alignof and and_eq asm bitand bitor bool catch char8_t char16_t"
    " char32_t class compl concept consteval constexpr constinit const_cast"
    " co_await co_return co_yield decltype delete dynamic_cast explicit export"
    " false friend mutable namespace new noexcept not not_eq nullptr operator or"
    " or_eq private protected public reinterpret_cast requires static_assert"
    " static_cast template this thread_local throw true try typeid typename using"
    " virtual wchar_t xor xor_eq".split()
)


def attribute(cursor) -> str:
    """The name of an attribute, from its tokens where libclang has none"""

    if cursor.spelling:
        return cursor.spelling
    tokens = [t.spelling for t in cursor.get_tokens()]
    return tokens[0] if tokens else cursor.kind.name


def element(ctype):
    """The type 'ctype' is made of, through pointers and arrays"""

    while ctype.kind in (
        TypeKind.POINTER,
        TypeKind.CONSTANTARRAY,
        TypeKind.INCOMPLETEARRAY,
        TypeKind.VARIABLEARRAY,
    ):
        if ctype.kind == TypeKind.POINTER:
            ctype = ctype.get_pointee()
        else:
            ctype = ctype.element_type
    return ctype


def location(cursor) -> Tuple[str, int, int]:
    loc = cursor.location
    return (loc.file.name if loc.file else "", loc.line or 0, loc.column or 0)


def is_unnamed(cursor) -> bool:
    """Whether the record or enum has no tag; libclang spells such a one '' or
    '(anonymous ...)' / '(unnamed ...)', and is_anonymous() misses typedef'd ones"""

    spelling = cursor.spelling
    return not spelling or "(anonymous" in spelling or "(unnamed" in spelling


def decl_key(cursor) -> Tuple[str, int]:
    """Identifies a declaration, also an anonymous one, within a translation unit"""

    loc = cursor.location
    return (loc.file.name if loc.file else "", loc.offset)


def comment_before(lines: List[str], lineno: int) -> Optional[str]:
    """
    The Doxygen comment ending on the line above 'lineno', or trailing on it;
    libclang does not attach comments to macros, so they are found in the source
    """

    line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    trailing = re.search(r"((?:///|//!)<.*|/\*[*!]<.*\*/)\s*$", line)
    if trailing:
        return trailing.group(1)

    end = lineno - 2
    if end < 0:
        return None
    if lines[end].strip().startswith(("///", "//!")):
        start = end
        while start > 0 and lines[start - 1].strip().startswith(("///", "//!")):
            start -= 1
        return "\n".join(lines[start : end + 1])
    if lines[end].strip().endswith("*/"):
        start = end
        while start >= 0 and "/*" not in lines[start]:
            start -= 1
        if start >= 0 and lines[start].strip().startswith(("/**", "/*!")):
            return "\n".join(lines[start : end + 1])
    return None


class CParser(object):
    """Wraps libclang; parse a header with :meth:`.parse`"""

    def __init__(self, args: Optional[List[str]] = None):
        searchpath = os.environ.get("YACE_SEARCHPATH_LIBCLANG")
        if not searchpath:
            for path in Path(clang.__file__).resolve().parent.rglob("*libclang.*"):
                if path.suffix in [".dylib", ".so"]:
                    searchpath = str(path.parent)
                    break
        if searchpath and not Config.loaded:
            Config().set_library_path(searchpath)

        self.index = Index.create()
        self.args = list(args or [])
        builtin = self._clang_builtin_include()
        if builtin:
            self.args += ["-isystem", builtin]
        sysroot = self._sysroot()
        if sysroot:
            self.args += ["-isysroot", sysroot]

    @staticmethod
    def _sysroot() -> Optional[str]:
        """
        The SDK of macOS, where its C headers are; the libclang of the libclang
        package has no default for it, as Apple's clang does
        """

        if platform.system() != "Darwin":
            return None
        try:
            found = subprocess.run(
                ["xcrun", "--show-sdk-path"], capture_output=True, text=True
            ).stdout.strip()
        except OSError:
            return None
        return found if found and Path(found).is_dir() else None

    @staticmethod
    def _clang_builtin_include() -> Optional[str]:
        """clang's own include directory, with stddef.h and friends"""

        searchpath = os.environ.get("YACE_SEARCHPATH_LIBCLANG")
        base = (
            Path(searchpath).parent
            if searchpath
            else Path(clang.__file__).resolve().parent
        )
        for found in base.rglob("stddef.h"):
            return str(found.parent)

        for cc in (os.environ.get("CC", ""), "clang", "cc"):
            if not cc or not shutil.which(cc):
                continue
            proc = subprocess.run(
                [cc, "-print-resource-dir"], capture_output=True, text=True
            )
            include = Path(proc.stdout.strip()) / "include"
            if proc.returncode == 0 and (include / "stddef.h").exists():
                return str(include)

        for ver in sorted(
            Path("/usr/lib").glob("llvm-*/lib/clang/*/include"), reverse=True
        ):
            if (ver / "stddef.h").exists():
                return str(ver)

        return None

    def parse(self, path: Path, meta: Optional[dict] = None):
        """Parse the header at 'path'; returns the (Model, [Diagnostic])"""

        return _HeaderParser(self, Path(path).resolve(), meta or {}).run()


class _HeaderParser(object):
    """The state of parsing one header"""

    def __init__(self, parser: CParser, path: Path, meta: dict):
        self.parser = parser
        self.path = path
        self.meta = meta
        self.lines = path.read_text(errors="replace").splitlines()
        self.diagnostics: List[Diagnostic] = []
        self.names: Dict[Tuple[str, int], str] = {}  # anonymous decl -> its name
        self.absorbed: set = set()  # typedefs naming an anonymous record or enum
        self.aliases: set = set()  # typedefs of the record or enum of their name
        self.skipped: set = set()  # typedefs skipped, which their uses are too
        self.skipped_records: set = set()  # records skipped, by name, as typedefs
        self.external: set = set()  # records declared outside the header
        self.typedefs: set = set()  # typedef names declared in the header
        self.defined: set = set()  # records defined in the header, by name

    def report(self, rule: str, message: str, cursor=None):
        file, line, column = location(cursor) if cursor is not None else ("", 0, 0)
        self.diagnostics.append(
            Diagnostic(
                rule=rule,
                message=message,
                file=Path(file).name if file else "",
                line=line,
                column=column,
            )
        )

    def in_header(self, cursor) -> bool:
        file = cursor.location.file
        return bool(file) and Path(file.name).resolve() == self.path

    def typ(self, ctype, cursor) -> types.Type:
        """The IR type of the libclang 'ctype'; raises Unsupported"""

        found = self._typ(ctype, cursor)
        if ctype.is_const_qualified() and hasattr(found, "const"):
            found.const = True
        return found

    def _typ(self, ctype, cursor) -> types.Type:
        const = ctype.is_const_qualified()
        kind = ctype.kind

        if kind in BUILTIN_KINDS:
            return types.Builtin(name=BUILTIN_KINDS[kind], const=const)

        if kind == TypeKind.ELABORATED:
            return self.typ(ctype.get_named_type(), cursor)

        if kind == TypeKind.TYPEDEF:
            decl = ctype.get_declaration()
            name = decl.spelling
            if name in types.BUILTINS and not self.in_header(decl):
                return types.Builtin(name=name, const=const)
            if self.in_header(decl):
                if decl_key(decl) in self.skipped:
                    raise Unsupported(f"'{name}', a typedef that is skipped")
                if decl_key(decl) in self.absorbed | self.aliases:
                    found = self.typ(decl.underlying_typedef_type, cursor)
                    found.const = found.const or const
                    return found
                return types.TypedefRef(name=name, const=const)
            self.report(
                "external-type",
                f"'{name}' is declared outside the header, in"
                f" {Path(location(decl)[0]).name or 'the compiler'}",
                cursor,
            )
            # Of a record, a type of its own the bindings declare opaque; of
            # anything else, an integer, a pointer, an array, that type
            canonical = ctype.get_canonical()
            if canonical.kind == TypeKind.RECORD:
                self.external.add(name)
                return types.TypedefRef(name=name, const=const)
            found = self.typ(canonical, cursor)
            if hasattr(found, "const"):
                found.const = found.const or const
            return found

        if kind in (TypeKind.RECORD, TypeKind.ENUM):
            decl = ctype.get_declaration()
            name = self.names.get(decl_key(decl), decl.spelling)
            if is_unnamed(decl) and decl_key(decl) not in self.names:
                raise Unsupported(f"an anonymous {ctype.spelling} with no name")
            if not self.in_header(decl):
                self.report(
                    "external-type",
                    f"'{ctype.spelling}' is declared outside the header",
                    cursor,
                )
                self.external.add(name)
                if kind == TypeKind.ENUM:  # by value, as its integer
                    return self.typ(decl.enum_type, cursor)
            if kind == TypeKind.ENUM:
                return types.EnumRef(name=name, const=const)
            if name in self.skipped_records:
                raise Unsupported(f"'{name}', a record that is skipped")
            tag = "union" if decl.kind == CursorKind.UNION_DECL else "struct"
            return types.Record(tag=tag, name=name, const=const)

        if kind == TypeKind.POINTER:
            return types.Pointer(to=self.typ(ctype.get_pointee(), cursor), const=const)

        if kind == TypeKind.CONSTANTARRAY:
            return types.Array(
                of=self.typ(ctype.element_type, cursor), length=ctype.element_count
            )

        if kind == TypeKind.INCOMPLETEARRAY:
            return types.Array(of=self.typ(ctype.element_type, cursor), length=None)

        if kind == TypeKind.FUNCTIONPROTO:
            args = list(ctype.argument_types())
            parms = [c for c in cursor.get_children() if c.kind == CursorKind.PARM_DECL]
            if len(parms) != len(args):
                parms = [cursor] * len(args)
            params = [self.typ(arg, parm) for arg, parm in zip(args, parms)]
            names = [p.spelling if p is not cursor else "" for p in parms]
            return types.FunctionType(
                ret=self.typ(ctype.get_result(), cursor),
                params=[types.TypeParam(name=n, typ=p) for n, p in zip(names, params)],
                variadic=ctype.is_function_variadic(),
            )

        canonical = ctype.get_canonical()
        if canonical.kind != kind and canonical.kind in BUILTIN_KINDS:
            return self.typ(canonical, cursor)

        raise Unsupported(f"'{ctype.spelling}' ({kind.spelling})")

    def doc_of(self, cursor) -> doc.Doc:
        """The doc of a declaration; libclang joins adjacent comments into one,
        which is reported rather than read as one doc"""

        raw = cursor.raw_comment or ""
        lines = [line.lstrip() for line in raw.splitlines()]
        blocks = len(re.findall(r"(?:^|\*/)\s*/\*[*!]", raw, re.M))
        if blocks > 1 or blocks and any(t.startswith(("///", "//!")) for t in lines):
            self.report(
                "doc-comment",
                f"'{cursor.spelling}' has more than one doc comment",
                cursor,
            )
        return doc.parse(cursor.raw_comment)

    def share_docs(self, entities: list):
        """A typedef of the record or enum of its own name is that type, so
        the doc of either is the doc of both, and neither then lacks one"""

        tags = {
            e.name: e for e in entities if isinstance(e, (*decls.RECORDS, decls.Enum))
        }
        shared = set()
        for typedef in entities:
            tag = tags.get(getattr(typedef, "name", None))
            if not isinstance(typedef, decls.Typedef) or tag is None:
                continue
            if getattr(typedef.typ, "name", None) != typedef.name:
                continue
            if tag.doc.is_empty() and not typedef.doc.is_empty():
                tag.doc = typedef.doc
            elif typedef.doc.is_empty() and not tag.doc.is_empty():
                typedef.doc = tag.doc
            else:
                continue
            shared |= {f"{w} '{typedef.name}' has no doc" for w in DOCUMENTED}
        seen: set = set()  # a record declared, then defined, lacks one doc
        kept = []
        for d in self.diagnostics:
            if d.rule == "missing-doc" and (d.message in shared or d.message in seen):
                continue
            seen.add(d.message if d.rule == "missing-doc" else None)
            kept.append(d)
        self.diagnostics = kept

    def by_value(self, typ):
        """'typ', unless it holds a record declared outside the header by
        value, whose layout is unknown here; raises Unsupported then"""

        held = typ
        while isinstance(held, types.Array):
            held = held.of
        if isinstance(held, (types.Record, types.TypedefRef)) and (
            held.name in self.external
        ):
            spelled = f"{held.tag} {held.name}" if held.key == "record" else held.name
            raise Unsupported(f"'{spelled}', declared outside the header, by value")
        function = held.to if isinstance(held, types.Pointer) else held
        if isinstance(function, types.FunctionType):
            for param in function.params:
                self.by_value(param.typ)
            self.by_value(function.ret)
        return typ

    def drop_uses(self, entities: list) -> list:
        """'entities' without those using a record or typedef that is skipped,
        each reported; one declared before the skip got through the parse"""

        def used(node, kind):
            if isinstance(node, kind):
                yield node.name
            if isinstance(node, BaseModel):
                node = list(vars(node).values())
            if isinstance(node, list):
                for item in node:
                    yield from used(item, kind)

        typedefs: set = set()
        while True:
            kept = []
            for entity in entities:
                records = set(used(entity, types.Record)) & self.skipped_records
                aliases = set(used(entity, types.TypedefRef)) & typedefs
                if isinstance(entity, decls.RECORDS) and entity.name in records:
                    records.discard(entity.name)
                if not records and not aliases:
                    kept.append(entity)
                    continue
                self.report(
                    "unsupported-type",
                    f"'{entity.name}' uses '{sorted(records | aliases)[0]}', which"
                    " is skipped; it is skipped",
                )
                if isinstance(entity, decls.RECORDS):
                    self.skipped_records.add(entity.name)
                elif isinstance(entity, decls.Typedef):
                    typedefs.add(entity.name)
            if len(kept) == len(entities):
                return kept
            entities = kept

    def check_doc(self, entity, what: str, cursor):
        if entity.doc.is_empty():
            self.report("missing-doc", f"{what} '{entity.name}' has no doc", cursor)

    def record(self, cursor, name: str) -> list:
        """The record, after the records nested in it, which are hoisted"""

        self.keyword(name, "a record", cursor)
        hoisted: list = []
        fields: List[decls.Field] = []
        children = list(cursor.get_children())
        anon_count = 0
        member = ""

        for idx, child in enumerate(children):
            if child.kind in RECORD_KINDS + (CursorKind.ENUM_DECL,):
                if not child.is_definition():
                    continue

                user = next(
                    (
                        c
                        for c in children[idx + 1 :]
                        if c.kind == CursorKind.FIELD_DECL
                        and decl_key(element(c.type).get_declaration())
                        == decl_key(child)
                    ),
                    None,
                )
                kind = child.kind.name.split("_")[0].lower()
                if is_unnamed(child) and user is not None:
                    nested = f"{name}_{user.spelling}"
                    self.report(
                        "anonymous-record",
                        f"field '{user.spelling}' of '{name}' has an anonymous"
                        f" {kind} type; it is named '{nested}'",
                        child,
                    )
                elif is_unnamed(child) and child.kind == CursorKind.ENUM_DECL:
                    nested = f"{name}_anon{anon_count}"
                    anon_count += 1
                    self.report(
                        "anonymous-record",
                        f"'{name}' has an anonymous enum; it is named '{nested}'",
                        child,
                    )
                elif is_unnamed(child):
                    nested = f"{name}_anon{anon_count}"
                    member = f"anon{anon_count}"
                    anon_count += 1
                    self.report(
                        "anonymous-record",
                        f"'{name}' has an anonymous {kind} member; it is"
                        f" named '{nested}' and made the field '{member}'",
                        child,
                    )
                else:
                    nested = child.spelling
                    self.report(
                        "nested-record",
                        f"{kind} '{nested}' is defined inside '{name}'; it is"
                        " hoisted to the top level",
                        child,
                    )
                self.names[decl_key(child)] = nested

                if child.kind == CursorKind.ENUM_DECL:
                    hoisted.append(self.enum(child, nested))
                else:
                    hoisted += self.record(child, nested)
                found = hoisted[-1] if hoisted else None
                if not is_unnamed(child) and getattr(found, "name", None) == nested:
                    kind = "enum" if child.kind == CursorKind.ENUM_DECL else "struct"
                    if child.kind == CursorKind.UNION_DECL:
                        kind = "union"
                    self.check_doc(found, kind, child)

                if (
                    is_unnamed(child)
                    and user is None
                    and child.kind != CursorKind.ENUM_DECL
                ):
                    first = next(
                        (
                            c
                            for c in child.get_children()
                            if c.kind == CursorKind.FIELD_DECL
                        ),
                        None,
                    )
                    offset = None
                    if first is not None:
                        found = cursor.type.get_offset(first.spelling)
                        offset = found - max(first.get_field_offsetof(), 0)
                    tag = "union" if child.kind == CursorKind.UNION_DECL else "struct"
                    fields.append(
                        decls.Field(
                            name=member,
                            typ=types.Record(tag=tag, name=nested),
                            offset=(
                                offset if offset is not None and offset >= 0 else None
                            ),
                        )
                    )
                continue

            if child.kind == CursorKind.FIELD_DECL:
                self.keyword(child.spelling, f"a field of '{name}'", child)
                try:
                    typ = self.by_value(self.typ(child.type, child))
                except Unsupported as exc:
                    if name not in self.skipped_records:
                        self.report(
                            "unsupported-type",
                            f"field '{child.spelling}' of '{name}' has the type"
                            f" {exc}; '{name}' is skipped",
                            child,
                        )
                    self.skipped_records.add(name)
                    continue  # for the records nested after it, which are kept
                if name in self.skipped_records:
                    continue

                self.inline_callback(
                    typ, f"field '{child.spelling}' of '{name}'", child
                )
                bits = None
                if child.is_bitfield():
                    bits = child.get_bitfield_width()
                    self.report(
                        "bitfield",
                        (
                            f"field '{child.spelling}' of '{name}' is a bit-field"
                            if child.spelling
                            else f"'{name}' has an unnamed bit-field, as padding"
                        ),
                        child,
                    )
                if isinstance(typ, types.Array) and typ.length is None:
                    self.report(
                        "flexible-array",
                        f"field '{child.spelling}' of '{name}' is a flexible array",
                        child,
                    )
                offset = child.get_field_offsetof()
                fields.append(
                    decls.Field(
                        name=child.spelling,
                        typ=typ,
                        bits=bits,
                        offset=offset if offset >= 0 else None,
                        doc=self.doc_of(child),
                    )
                )
                continue

            if child.kind.is_attribute():
                self.report(
                    "attribute",
                    f"'{name}' has the attribute '{attribute(child)}'",
                    child,
                )
                continue

            self.report(
                "unsupported-declaration",
                f"'{name}' contains a {child.kind.name}, which is skipped",
                child,
            )

        if fields and not any(f.name for f in fields):
            self.report(
                "unsupported-declaration",
                f"'{name}' has only unnamed bit-fields, which ISO C does not allow;"
                " it is skipped",
                cursor,
            )
            self.skipped_records.add(name)
        if name in self.skipped_records:
            return hoisted
        size, align = cursor.type.get_size(), cursor.type.get_align()
        cls = decls.Union if cursor.kind == CursorKind.UNION_DECL else decls.Struct
        return hoisted + [
            cls(
                name=name,
                fields=fields,
                size=size if size > 0 else None,
                align=align if align > 0 else None,
                doc=self.doc_of(cursor),
            )
        ]

    def enum(self, cursor, name: str) -> decls.Enum:
        underlying = None
        try:
            found = self.typ(cursor.enum_type, cursor)
            if isinstance(found, types.Builtin):
                underlying = found
        except Unsupported:
            pass

        self.keyword(name, "an enum", cursor)
        for child in cursor.get_children():
            if child.kind == CursorKind.ENUM_CONSTANT_DECL:
                self.keyword(child.spelling, f"a member of '{name}'", child)
            if child.kind == CursorKind.ENUM_CONSTANT_DECL and not (
                -(2**31) <= child.enum_value < 2**31
            ):
                self.report(
                    "enum-value",
                    f"'{child.spelling}' of enum '{name}' does not fit an int",
                    child,
                )
        return decls.Enum(
            name=name,
            members=[
                decls.EnumMember(
                    name=child.spelling, value=child.enum_value, doc=self.doc_of(child)
                )
                for child in cursor.get_children()
                if child.kind == CursorKind.ENUM_CONSTANT_DECL
            ],
            underlying=underlying,
            doc=self.doc_of(cursor),
        )

    def signature_checks(self, fname: str, ret, params, cursor):
        """Report records by value and enums, as parameters or as the return"""

        for what, typ in [("returns", ret)] + [
            (f"parameter '{p.name}'", p.typ) for p in params
        ]:
            if isinstance(typ, types.Record):
                self.report(
                    "record-by-value",
                    f"'{fname}' {what} {typ.tag} {typ.name} by value",
                    cursor,
                )
            if isinstance(typ, types.EnumRef):
                self.report(
                    "enum-in-signature",
                    f"'{fname}' {what} enum {typ.name}",
                    cursor,
                )

    def function(self, cursor) -> Optional[decls.Function]:
        name = cursor.spelling
        self.keyword(name, "a function", cursor)
        if cursor.storage_class == StorageClass.STATIC or cursor.is_definition():
            self.report(
                "unsupported-declaration",
                f"'{name}' is a static or inline function; it is skipped",
                cursor,
            )
            return None

        for child in cursor.get_children():
            if child.kind.is_attribute():
                self.report(
                    "attribute",
                    f"'{name}' has the attribute '{attribute(child)}';"
                    " it is ignored",
                    child,
                )

        try:
            params = []
            for idx, arg in enumerate(cursor.get_arguments()):
                if not arg.spelling:
                    self.report(
                        "param-name",
                        f"parameter {idx} of '{name}' has no name",
                        cursor,
                    )
                if "va_list" in arg.type.spelling:
                    raise Unsupported(f"'{arg.type.spelling}', which no binding passes")
                typ = self.typ(arg.type, arg)
                if isinstance(typ, types.Array):
                    self.report(
                        "array-parameter",
                        f"parameter '{arg.spelling}' of '{name}' is an array",
                        arg,
                    )
                    typ = types.Pointer(to=typ.of)  # as C passes it
                typ = self.by_value(typ)
                params.append(decls.Param(name=arg.spelling, typ=typ))
                self.inline_callback(
                    typ, f"parameter '{arg.spelling}' of '{name}'", arg
                )
            ret = self.by_value(self.typ(cursor.result_type, cursor))
            self.inline_callback(ret, f"the return of '{name}'", cursor)
        except Unsupported as exc:
            self.report(
                "unsupported-type",
                f"'{name}' uses the type {exc}; it is skipped",
                cursor,
            )
            return None

        variadic = cursor.type.is_function_variadic()
        if variadic:
            self.report("variadic-function", f"'{name}' is variadic", cursor)
        self.signature_checks(name, ret, params, cursor)

        function = decls.Function(
            name=name,
            ret=ret,
            params=params,
            variadic=variadic,
            doc=self.doc_of(cursor),
        )
        self.check_doc(function, "function", cursor)
        return function

    def typedef(self, cursor) -> Optional[decls.Typedef]:
        name = cursor.spelling
        self.keyword(name, "a typedef", cursor)
        try:
            typ = self.by_value(self.typ(cursor.underlying_typedef_type, cursor))
        except Unsupported as exc:
            self.report(
                "unsupported-type",
                f"typedef '{name}' is of the type {exc}; it is skipped",
                cursor,
            )
            self.skipped.add(decl_key(cursor))
            return None

        tags = set()
        node = typ
        while isinstance(node, (types.Pointer, types.Array)):
            node = node.to if isinstance(node, types.Pointer) else node.of
        if isinstance(node, (types.Record, types.EnumRef)) and node is not typ:
            tags.add(node.name)
        if name in tags:
            self.report(
                "typedef",
                f"typedef '{name}' is another type than the record or enum of its"
                " name, which no binding can declare beside it; its type is used"
                " in its place",
                cursor,
            )
            self.absorbed.add(decl_key(cursor))
            return None

        if isinstance(typ, types.Pointer) and isinstance(typ.to, types.FunctionType):
            for param in typ.to.params:
                self.inline_callback(
                    param.typ, f"parameter '{param.name}' of '{name}'", cursor
                )
            self.inline_callback(typ.to.ret, f"the return of '{name}'", cursor)
            if not name.endswith(CALLBACK_SUFFIXES):
                self.report(
                    "callback-name",
                    f"function pointer '{name}' does not end in one of"
                    f" {', '.join(CALLBACK_SUFFIXES)}",
                    cursor,
                )
            unnamed = [i for i, p in enumerate(typ.to.params) if not p.name]
            if unnamed:
                self.report(
                    "callback-param-name",
                    f"function pointer '{name}' has unnamed parameters",
                    cursor,
                )
        elif isinstance(typ, (types.Record, types.EnumRef)) and typ.name == name:
            self.aliases.add(decl_key(cursor))  # that type, where it is used
        else:
            self.report(
                "typedef",
                f"'{name}' is a typedef of something other than a function pointer",
                cursor,
            )

        typedef = decls.Typedef(name=name, typ=typ, doc=self.doc_of(cursor))
        self.check_doc(typedef, "typedef", cursor)
        return typedef

    def macro(self, cursor):
        """A Define, None when skipped, or the name of a macro to evaluate"""

        tokens = list(cursor.get_tokens())
        if len(tokens) < 2:
            return None  # no value, such as an include guard

        name = tokens[0].spelling
        self.keyword(name, "a define", cursor)
        if (
            tokens[1].spelling == "("
            and tokens[1].extent.start.offset == tokens[0].extent.end.offset
        ):
            self.report(
                "function-like-macro", f"'{name}' is a function-like macro", cursor
            )
            return None

        values = tokens[1:]
        if all(
            t.kind == TokenKind.LITERAL and t.spelling.startswith('"') for t in values
        ):
            text = "".join(unescape(t.spelling[1:-1]) for t in values)
            return decls.Define(
                name=name,
                value=decls.StrLiteral(value=text),
                doc=self.macro_doc(cursor),
            )

        return name

    def macro_doc(self, cursor) -> doc.Doc:
        return doc.parse(comment_before(self.lines, cursor.location.line))

    def evaluate(self, names: List[str]) -> Dict[str, int]:
        """
        The integer value of each macro clang can evaluate as a constant; each is
        made the value of an enumerator in a translation unit including the
        header, as a long long, or else, where it does not fit one, an unsigned
        """

        found: Dict[str, int] = {}
        for idx in range(0, len(names), EVAL_BATCH):
            batch = names[idx : idx + EVAL_BATCH]
            source = [f'#include "{self.path}"']
            for enum, underlying in (("s", "long long"), ("u", "unsigned long long")):
                source.append(f"enum yace_eval_{enum} : {underlying} {{")
                source += [f"\tyace_eval_{enum}_{name} = ({name})," for name in batch]
                source.append("};")
            source.append("")

            with tempfile.NamedTemporaryFile("w", suffix=".c") as tmp:
                tmp.write("\n".join(source))
                tmp.flush()
                tu = self.parser.index.parse(
                    tmp.name, args=self.parser.args + [f"-I{self.path.parent}"]
                )
                invalid = {
                    diag.location.line
                    for diag in tu.diagnostics
                    if diag.severity >= 3
                    and diag.location.file
                    and diag.location.file.name == tmp.name
                }
                for cursor in tu.cursor.get_children():
                    if cursor.kind != CursorKind.ENUM_DECL:
                        continue
                    if cursor.spelling not in ("yace_eval_s", "yace_eval_u"):
                        continue
                    for child in cursor.get_children():
                        if child.location.line in invalid:
                            continue
                        name = child.spelling[len("yace_eval_s_") :]
                        found.setdefault(name, child.enum_value)
        return found

    def run(self):
        tu = self.parser.index.parse(
            str(self.path),
            args=self.parser.args,
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )
        for diag in tu.diagnostics:
            if diag.severity >= 3:
                self.diagnostics.append(
                    Diagnostic(
                        rule="parse-error",
                        message=diag.spelling,
                        file=(
                            Path(diag.location.file.name).name
                            if diag.location.file
                            else ""
                        ),
                        line=diag.location.line,
                        column=diag.location.column,
                    )
                )

        cursors = [c for c in tu.cursor.get_children() if self.in_header(c)]

        for cursor in cursors:
            if cursor.kind != CursorKind.TYPEDEF_DECL:
                continue
            underlying = cursor.underlying_typedef_type
            if underlying.kind == TypeKind.ELABORATED:
                underlying = underlying.get_named_type()
            decl = underlying.get_declaration()
            if (
                decl.kind in RECORD_KINDS + (CursorKind.ENUM_DECL,)
                and is_unnamed(decl)
                and decl_key(decl) not in self.names
            ):
                self.names[decl_key(decl)] = cursor.spelling
                self.absorbed.add(decl_key(cursor))
            self.typedefs.add(cursor.spelling)

        defined = {
            c.spelling
            for c in cursors
            if c.kind in RECORD_KINDS + (CursorKind.ENUM_DECL,) and c.is_definition()
        }

        entities: list = []  # entities, and names of macros to evaluate
        declared: set = set()
        for cursor in cursors:
            try:
                entities += self.declaration(cursor, defined, declared)
            except Exception as exc:  # a bug in yace, not in the header
                log.debug("internal error", exc_info=True)
                self.report(
                    "internal-error",
                    f"'{cursor.spelling}': {type(exc).__name__}: {exc}",
                    cursor,
                )

        macros = [e for e in entities if isinstance(e, tuple)]
        values = self.evaluate([name for name, _ in macros]) if macros else {}
        resolved = []
        for entity in entities:
            if not isinstance(entity, tuple):
                resolved.append(entity)
                continue
            name, cursor = entity
            if name not in values:
                self.report(
                    "macro-value",
                    f"'{name}' is not a string literal or integer constant expression",
                    cursor,
                )
                continue
            text = " ".join(t.spelling for t in list(cursor.get_tokens())[1:])
            base = (
                16 if re.match(r"^\(?\s*0[xX][0-9a-fA-F]+[uUlL]*\s*\)?$", text) else 10
            )
            resolved.append(
                decls.Define(
                    name=name,
                    value=decls.IntLiteral(value=values[name], base=base),
                    doc=self.macro_doc(cursor),
                )
            )

        for entity in resolved:
            if isinstance(entity, decls.Define):
                self.check_doc(entity, "define", None)

        # A record declared, then defined nested in another, is the definition
        nested = {
            e.name: e for e in resolved if isinstance(e, decls.RECORDS) and e.fields
        }
        for opaque in resolved:
            if isinstance(opaque, decls.RECORDS) and not opaque.fields:
                if opaque.name in nested and nested[opaque.name].doc.is_empty():
                    nested[opaque.name].doc = opaque.doc
        resolved = [
            e
            for e in resolved
            if not (isinstance(e, decls.RECORDS) and not e.fields and e.name in nested)
        ]
        resolved = self.drop_uses(resolved)
        self.share_docs(resolved)

        meta = {
            "name": self.path.stem,
            "prefix": self.path.stem,
            "header": self.path.name,
            "abi": host_abi(),
        }
        meta.update(self.meta)

        return Model(meta=Meta(**meta), entities=resolved), self.diagnostics

    def inline_callback(self, typ, what: str, cursor):
        """Report a function pointer not named by a typedef, also one within a
        pointer or array"""

        while isinstance(typ, (types.Pointer, types.Array)):
            inner = typ.to if isinstance(typ, types.Pointer) else typ.of
            if isinstance(typ, types.Pointer) and isinstance(inner, types.FunctionType):
                self.report(
                    "callback-typedef",
                    f"{what} is a function pointer not typedef'd",
                    cursor,
                )
                return
            typ = inner

    def keyword(self, name: str, what: str, cursor):
        """Report 'name' where C++ reserves it; parameters are renamed instead"""

        if name in CXX_KEYWORDS:
            self.report("cxx-keyword", f"'{name}', {what}, is a keyword of C++", cursor)

    def declaration(self, cursor, defined: set, declared: set) -> list:
        kind = cursor.kind

        if kind == CursorKind.INCLUSION_DIRECTIVE:
            system = any(t.spelling == "<" for t in cursor.get_tokens())
            return [decls.Include(name=cursor.displayname, system=system)]

        if kind == CursorKind.MACRO_DEFINITION:
            found = self.macro(cursor)
            if found is None:
                return []
            if isinstance(found, str):
                return [(found, cursor)]
            return [found]

        if kind == CursorKind.MACRO_INSTANTIATION:
            return []

        if kind in RECORD_KINDS + (CursorKind.ENUM_DECL,):
            what = kind.name.split("_")[0].lower()
            if decl_key(cursor) in self.names:
                name = self.names[decl_key(cursor)]
                self.report(
                    "anonymous-record",
                    f"the anonymous {what} named by typedef '{name}' is named"
                    f" '{name}'",
                    cursor,
                )
            elif is_unnamed(cursor) and kind == CursorKind.ENUM_DECL:
                return self.anonymous_enum(cursor)
            elif is_unnamed(cursor):
                self.report(
                    "unsupported-declaration",
                    f"an anonymous {what} not named by a typedef is skipped",
                    cursor,
                )
                return []
            else:
                name = cursor.spelling

            if not cursor.is_definition():
                if name in defined or name in declared or kind == CursorKind.ENUM_DECL:
                    return []  # a forward declaration of what the header defines
                declared.add(name)
                cls = decls.Union if kind == CursorKind.UNION_DECL else decls.Struct
                opaque = cls(name=name, fields=[], doc=self.doc_of(cursor))
                self.check_doc(opaque, what, cursor)
                return [opaque]

            declared.add(name)
            if kind == CursorKind.ENUM_DECL:
                enum = self.enum(cursor, name)
                self.check_doc(enum, "enum", cursor)
                return [enum]
            found = self.record(cursor, name)
            if found and found[-1].name == name:
                self.check_doc(found[-1], what, cursor)
            return found

        if kind == CursorKind.TYPEDEF_DECL:
            if decl_key(cursor) in self.absorbed:
                return []
            typedef = self.typedef(cursor)
            return [typedef] if typedef else []

        if kind == CursorKind.FUNCTION_DECL:
            function = self.function(cursor)
            return [function] if function else []

        if kind == CursorKind.VAR_DECL:
            self.report(
                "unsupported-declaration",
                f"variable '{cursor.spelling}' is skipped",
                cursor,
            )
            return []

        self.report(
            "unsupported-declaration",
            f"'{cursor.spelling}', a {kind.name}, is skipped",
            cursor,
        )
        return []

    def anonymous_enum(self, cursor) -> list:
        """The members of an anonymous enum, as integer constants"""

        self.report(
            "anonymous-record",
            "an anonymous enum; its members are made constants",
            cursor,
        )
        return [
            decls.Define(
                name=child.spelling,
                value=decls.IntLiteral(value=child.enum_value),
                doc=self.doc_of(child),
            )
            for child in cursor.get_children()
            if child.kind == CursorKind.ENUM_CONSTANT_DECL
        ]


def c_to_yace(
    paths: List[Path], output: Path, meta: Optional[dict] = None, args=None
) -> List[Tuple[Path, Model, List[Diagnostic]]]:
    """
    Parse each header in 'paths', writing its IR to '<output>/<stem>.yaml' and
    its diagnostics to '<output>/<stem>.status'
    """

    output.mkdir(parents=True, exist_ok=True)
    parser = CParser(args)

    results = []
    for path in [Path(p).resolve() for p in paths]:
        model, diagnostics = parser.parse(path, meta)
        model.save(output / f"{path.stem}.yaml")

        lines = [
            f"Parsed {len(model.entities)} entities," f" {len(diagnostics)} diagnostics"
        ]
        lines += [str(diag) for diag in diagnostics]
        (output / f"{path.stem}.status").write_text("\n".join(lines) + "\n")

        results.append((path, model, diagnostics))

    return results
