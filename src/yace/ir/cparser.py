"""
The goal of this module is to provide the buildings blocks for a yace-file
generator. That is, something to aid the creation of **Yace**-files.

In this specific instance, to parse C Headers, and emit equivalent
**Yace**-files.

* :class:`.CParser`, parse a C header and emit a **Yace**-file
"""

import logging as log
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import clang
from clang.cindex import Config, CursorKind, Index, TypeKind
from pydantic import ValidationError

import yace
from yace.errors import Error, ParseError, UnsupportedDatatype
from yace.ir import constants, datatypes, directives
from yace.ir.base import Docstring
from yace.model import Model

REGEX_INTEGER_FIXEDWIDTH = "(?P<unsigned>u)?int(?P<width>8|16|32|64|128)_t"

SHORTHAND_DATA = datatypes.classes_shorthand_data()

SHORTHAND_TO_CLS = datatypes.get_shorthand_to_cls()

QUALIFIERS = [("volatile", False), ("restrict", False), ("const", True)]


def typedef_is_fixed_width_integer(text):
    """Returns true when the given typedef-spelling is a fixed-width integer typedef"""

    return re.match(f"^{REGEX_INTEGER_FIXEDWIDTH}$", text) is not None


def get_fixed_width(tokens):
    """Returns Typespec-instance for a fixed-width type when applicable"""

    if len(tokens) < 2:
        return None

    match = re.match(REGEX_INTEGER_FIXEDWIDTH, tokens[-2])
    if not match:
        return None

    if len(tokens) > 2:
        if tokens[0] != "const":
            return None

    unsigned = match.group("unsigned") == "u"
    width = int(match.group("width"))
    shorthand = "".join(["u" if unsigned else "i", str(width), "_tspec"])
    cls = SHORTHAND_TO_CLS.get(shorthand)
    if cls is None:
        return None
    inst = cls()

    if inst.c_spelling() != " ".join(tokens[:-1]):
        return None

    return inst


def _fptr_typespec(
    proto: clang.cindex.Type, sym: str, cursor: clang.cindex.Cursor
) -> Tuple[Optional[datatypes.FunctionPointer], Optional[Error]]:
    """Build a FunctionPointer typespec with full signature from a FUNCTIONPROTO type."""

    ret_typespec, err = typekind_to_typespec(proto.get_result(), cursor)
    if err:
        return datatypes.FunctionPointer(sym=sym), None  # fallback: no signature

    params = []
    for i, arg_type in enumerate(proto.argument_types()):
        ptyp, perr = typekind_to_typespec(arg_type, cursor)
        if perr:
            return datatypes.FunctionPointer(sym=sym), None  # fallback
        params.append({"typ": ptyp, "sym": f"arg{i}"})

    return datatypes.FunctionPointer(sym=sym, ret=ret_typespec, parameters=params), None


def typekind_to_typespec(
    tobj: clang.cindex.Type, cursor: clang.cindex.Cursor
) -> Tuple[Optional[datatypes.Typespec], Error]:
    canonical = tobj.get_canonical().spelling
    const = tobj.is_const_qualified()

    # Handle fixed-width integers
    fw_typ = get_fixed_width([tok.spelling for tok in cursor.get_tokens()])
    if fw_typ:
        fw_typ.canonical = fw_typ.c_spelling()
        fw_typ.const = const
        return fw_typ, None

    # When a TYPEDEF makes it here...
    fw_typ = get_fixed_width(tobj.spelling.split(" ") + ["foo"])
    if fw_typ:
        fw_typ.canonical = fw_typ.c_spelling()
        fw_typ.const = const
        return fw_typ, None

    match tobj.kind:
        case TypeKind.CHAR_S | TypeKind.CHAR_U:
            return datatypes.Char(
                canonical="signed char", signed=True, const=const
            ), UnsupportedDatatype.from_cursor(
                cursor,
                f"Unsupported type({TypeKind.CHAR_S}); from 'char' without sign."
                f" Coercing '{canonical}' into 'signed char'.",
            )

        case TypeKind.SCHAR:
            return datatypes.Char(canonical=canonical, signed=True, const=const), None

        case TypeKind.UCHAR:
            return datatypes.Char(canonical=canonical, signed=False, const=const), None

        case TypeKind.VOID:
            return datatypes.Void(canonical=canonical, const=const), None

        case TypeKind.BOOL:
            return datatypes.Bool(canonical=canonical, const=const), None

        case TypeKind.INT:
            return datatypes.I(canonical=canonical, const=const), None

        case TypeKind.UINT:
            return datatypes.U(canonical=canonical, const=const), None

        case TypeKind.SHORT:
            return datatypes.IShort(canonical=canonical, const=const), None

        case TypeKind.USHORT:
            return datatypes.UShort(canonical=canonical, const=const), None

        case TypeKind.LONG:
            return datatypes.ILong(canonical=canonical, const=const), None
        case TypeKind.ULONG:
            return datatypes.ULong(canonical=canonical, const=const), None

        case TypeKind.LONGLONG:
            return datatypes.ILongLong(canonical=canonical, const=const), None
        case TypeKind.ULONGLONG:
            return datatypes.ULongLong(canonical=canonical, const=const), None

        case TypeKind.FLOAT:
            return datatypes.F32(canonical=canonical, const=const), None
        case TypeKind.DOUBLE:
            return datatypes.F64(canonical=canonical, const=const), None

        case TypeKind.ENUM:
            # Bare enum type (not wrapped in ELABORATED)
            sym = tobj.get_declaration().spelling
            return (
                datatypes.Enumeration(
                    sym=sym, enum=True, canonical=canonical, const=const
                ),
                None,
            )

        case TypeKind.ELABORATED | TypeKind.RECORD:
            spelling = tobj.spelling
            # Strip leading const/volatile qualifiers
            for qual in ("const ", "volatile ", "restrict "):
                spelling = spelling.removeprefix(qual)

            parts = spelling.split(None, 1)
            keyword = parts[0] if parts else ""

            if keyword == "struct" and len(parts) == 2:
                sym = parts[1]
                if "(unnamed" not in sym:
                    return (
                        datatypes.Record(
                            sym=sym, struct=True, canonical=canonical, const=const
                        ),
                        None,
                    )
            elif keyword == "union" and len(parts) == 2:
                sym = parts[1]
                if "(unnamed" not in sym:
                    return (
                        datatypes.Record(
                            sym=sym, union=True, canonical=canonical, const=const
                        ),
                        None,
                    )
            elif keyword == "enum" and len(parts) == 2:
                sym = parts[1]
                return (
                    datatypes.Enumeration(
                        sym=sym, enum=True, canonical=canonical, const=const
                    ),
                    None,
                )

            # Typedef-based elaborated type (e.g., "const point_t") or
            # unnamed struct/union — resolve via canonical type
            canonical_type = tobj.get_canonical()
            if canonical_type.kind != tobj.kind:
                return typekind_to_typespec(canonical_type, cursor)

            return None, ParseError.from_cursor(
                message=f"Unresolved elaborated type: {tobj.spelling}",
                cursor=cursor,
            )

        case TypeKind.POINTER:
            pointee = tobj.get_pointee()

            # Special-case for string-representation
            if pointee.is_const_qualified() and pointee.kind == TypeKind.CHAR_S:
                return datatypes.CString(), None

            # Special-case for function pointers: void (*cb)(int, int)
            if pointee.kind == TypeKind.FUNCTIONPROTO:
                return _fptr_typespec(pointee, tobj.spelling, cursor)

            # General case pointer to anything, everything, or nothing ;)
            typespec, error = typekind_to_typespec(pointee, cursor)
            if error:
                return None, error

            return (
                datatypes.Pointer(pointee=typespec, canonical=canonical, const=const),
                None,
            )

        case TypeKind.TYPEDEF:
            # Preserve well-known platform typedefs instead of canonicalizing
            _KNOWN_TYPEDEFS = {
                "size_t": lambda: datatypes.USize(canonical="size_t"),
                "ssize_t": lambda: datatypes.ISize(canonical="ssize_t"),
            }
            typedef_name = tobj.spelling
            if typedef_name in _KNOWN_TYPEDEFS:
                typ = _KNOWN_TYPEDEFS[typedef_name]()
                typ.const = const
                return typ, None

            canonical_type = tobj.get_canonical()

            # Special case: pointer to function prototype
            if (
                canonical_type.kind == TypeKind.POINTER
                and canonical_type.get_pointee().kind == TypeKind.FUNCTIONPROTO
            ):
                return _fptr_typespec(
                    canonical_type.get_pointee(), tobj.spelling, cursor
                )

            # General case: resolve the typedef to its canonical type
            return typekind_to_typespec(canonical_type, cursor)

        case TypeKind.FUNCTIONPROTO:
            return _fptr_typespec(tobj, tobj.spelling, cursor)

        case TypeKind.FUNCTIONNOPROTO:
            return datatypes.FunctionPointer(sym=tobj.spelling), None

        case TypeKind.CONSTANTARRAY:
            array_typ, error = typekind_to_typespec(
                cursor.type.get_array_element_type(), cursor
            )
            if error:
                return None, error

            return (
                datatypes.Array(
                    array=True,
                    array_typ=array_typ,
                    array_length=cursor.type.get_array_size(),
                    const=cursor.type.is_const_qualified(),
                ),
                None,
            )

        case _:
            return None, ParseError.from_cursor(
                message=f"Unhandled TypeKind({tobj.kind})",
                cursor=cursor,
            )


def literal_from_text(
    text: str,
) -> Optional[Union[constants.Dec, constants.Hex, constants.String]]:
    """
    Given a string on the forms:

    * 42
    * 0xACDC
    * "foobar is the baz!"

    Will return the correct instance
    """

    regex = (
        r"(?P<hex>0x[0-9a-fA-F]+)|"  # Hexi-decimal
        r"(?P<int>\d+)|"  # Plain integers
        r"(?:\"(?P<str>[^\"]+)\")"  # String constants
    )

    mapping = {
        "hex": (constants.Hex, lambda x: int(x, 16)),
        "int": (constants.Dec, lambda x: int(x, 10)),
        "str": (constants.String, str),
    }

    match = re.match(regex, text)
    if not match:
        return None

    for key, val in match.groupdict().items():
        if val:
            cls, transform = mapping[key]
            return cls(lit=transform(val))

    return None


class CParser(object):
    """
    Primitive wrapper around libclang Python bindings
    """

    def __init__(self):
        """Figure out a way to setup the index..."""

        searchpath = os.environ.get("YACE_SEARCHPATH_LIBCLANG")
        if not searchpath:
            for path in Path(clang.__file__).resolve().parent.rglob("*libclang.*"):
                if path.suffix in [".dylib", ".so"]:
                    searchpath = str(path.parent)
                    break
        if searchpath and not Config.loaded:
            Config().set_library_path(searchpath)

        self.index = Index.create()

    def _clang_builtin_include(self):
        """Find clang's built-in include directory (contains stddef.h, etc.)."""

        # Check alongside the libclang shared library
        searchpath = os.environ.get("YACE_SEARCHPATH_LIBCLANG")
        if searchpath:
            base = Path(searchpath).parent
        else:
            base = Path(clang.__file__).resolve().parent

        for include_dir in base.rglob("stddef.h"):
            return str(include_dir.parent)

        # Fallback: search common system paths
        for ver in sorted(Path("/usr/lib").glob("llvm-*/lib/clang/*/include"), reverse=True):
            if (ver / "stddef.h").exists():
                return str(ver)

        return None

    def parse_file(self, path: Path):
        """Parse the given file into a :class:`clang.cindex.TranslationUnit`."""

        args = []
        builtin_inc = self._clang_builtin_include()
        if builtin_inc:
            args.extend(["-isystem", builtin_inc])

        return self.index.parse(
            str(path),
            args=args,
            options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )

    def parse_macro(
        self, cursor
    ) -> Tuple[Optional[yace.model.base.Entity], Optional[yace.errors.Error]]:
        """TODO: hex + int"""

        tokens = [tok.spelling for tok in cursor.get_tokens()]
        log.debug(f"({cursor.spelling}), tokens({tokens})")

        if len(tokens) == 1:
            log.debug(f"Skipping value-less define: '#define {tokens[0]}'")
            return None, None

        if len(tokens) != 2:
            error = UnsupportedDatatype.from_cursor(
                cursor,
                f"'#define {tokens[0]}' unsupported amount of ntokens({len(tokens)}); "
                "expecting two, e.g. 'FOO_MAX 42'",
            )
            return None, error

        sym, lit, *excess = list([tok.spelling for tok in cursor.get_tokens()])
        if excess:
            return None, ParseError.from_cursor(
                message=f"sym({sym}), lit({lit}); Unexpected ntokens({len(excess)})",
                cursor=cursor,
            )

        val = literal_from_text(lit)
        if not val:
            return None, ParseError.from_cursor(
                message=f"sym({sym}), lit({lit}); Failed converting", cursor=cursor
            )

        try:
            return constants.Define(sym=sym, val=val), None
        except ValidationError as exc:
            return None, [ParseError.from_exception(exc, cursor)]

    def evaluate_expression_macros(
        self, macro_names: List[str], header_path: Path
    ) -> Dict[str, int]:
        """Evaluate expression macros by wrapping them in enum constants.

        Generates a temporary C file that includes the original header and
        defines an enum with each macro as a value. Clang evaluates the
        expressions at parse time, and we extract the integer results.

        Returns a dict of {macro_name: evaluated_value} for macros that
        successfully evaluate to integer constants.
        """

        if not macro_names:
            return {}

        # Build the temporary C source — use absolute path for the include
        abs_header = str(header_path.resolve())
        include_dir = str(header_path.resolve().parent)

        # Split into batches to avoid enum overflow (enum values are int-sized)
        # and to isolate failures
        BATCH_SIZE = 200
        results: Dict[str, int] = {}

        for i in range(0, len(macro_names), BATCH_SIZE):
            batch = macro_names[i : i + BATCH_SIZE]

            lines = [f'#include "{abs_header}"\n', "enum __yace_eval {\n"]
            for name in batch:
                lines.append(f"    __yace_{name} = {name},\n")
            lines.append("};\n")

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".c", delete=True
            ) as tmp:
                tmp.write("".join(lines))
                tmp.flush()

                try:
                    tu = self.index.parse(
                        tmp.name,
                        args=[f"-I{include_dir}"],
                        options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
                    )
                except Exception:
                    log.debug("Failed to parse macro evaluation file")
                    continue

                for cursor in tu.cursor.get_children():
                    if cursor.kind != CursorKind.ENUM_DECL:
                        continue
                    if cursor.spelling != "__yace_eval":
                        continue
                    for child in cursor.get_children():
                        if child.kind != CursorKind.ENUM_CONSTANT_DECL:
                            continue
                        name = child.spelling
                        if name.startswith("__yace_"):
                            original_name = name[7:]
                            results[original_name] = child.enum_value

        return results

    def parse_inclusion_directive(
        self, cursor
    ) -> Tuple[Optional[yace.model.base.Entity], Optional[yace.errors.Error]]:
        return directives.IncludeDirective(**{"filename": cursor.displayname}), None

    def parse_enum(
        self, cursor
    ) -> Tuple[Optional[yace.model.base.Entity], Optional[yace.errors.Error]]:
        """Parse into key-objects enum and enum_value"""

        members = []
        for child in cursor.get_children():
            if child.kind not in [CursorKind.ENUM_CONSTANT_DECL]:
                return None, ParseError.from_cursor(
                    f"expected ENUM_CONSTANT_DECL; got: ({child})", cursor=child
                )

            try:
                members.append(
                    constants.EnumValue(
                        sym=child.spelling,
                        doc=Docstring.from_cursor(child),
                        val=constants.Dec(lit=child.enum_value),
                    )
                )
            except ValidationError as exc:
                return None, ParseError.from_exception(exc, child)

        try:
            return (
                constants.Enum(
                    sym=cursor.spelling,
                    doc=Docstring.from_cursor(cursor),
                    members=members,
                ),
                None,
            )
        except ValidationError as exc:
            return None, ParseError.from_exception(exc, cursor)

    def parse_record(
        self, cursor
    ) -> Tuple[Optional[yace.model.base.Entity], Optional[yace.errors.Error]]:
        try:
            cls = yace.model.derivedtypes.Struct
            if cursor.kind == CursorKind.UNION_DECL:
                cls = yace.model.derivedtypes.Union

            record = cls(
                sym=cursor.spelling,
                doc=Docstring.from_cursor(cursor),
                members=[],
            )
        except ValidationError as exc:
            return None, ParseError.from_exception(exc, cursor)

        for field in cursor.get_children():
            match field.kind:
                case CursorKind.FIELD_DECL:
                    pass

                case CursorKind.STRUCT_DECL | CursorKind.UNION_DECL:
                    if list(field.get_children()):
                        # Inline anonymous struct/union definition — skip the
                        # type definition node; its fields appear as FIELD_DECLs
                        # in the parent record.
                        continue

                case CursorKind.PACKED_ATTR:
                    # __attribute__((packed)) — skip, doesn't affect IR
                    continue

                case CursorKind.ENUM_DECL:
                    # Inline enum definition inside a struct — skip the
                    # definition node; the field using it follows as FIELD_DECL.
                    continue

                case _:
                    return None, ParseError.from_cursor(
                        f"expected FIELD_DECL; got: {field.kind}", cursor=field
                    )

            ftyp, error = typekind_to_typespec(field.type, field)
            if error:
                return None, error

            if field.is_bitfield():
                field = yace.model.derivedtypes.Bitfield(
                    sym=field.spelling,
                    doc=Docstring.from_cursor(field),
                    nbits=field.get_bitfield_width(),
                    typ=ftyp,
                )
            else:
                field = yace.model.derivedtypes.Field(
                    sym=field.spelling,
                    doc=Docstring.from_cursor(field),
                    typ=ftyp,
                )

            record.members.append(field)

        return record, None

    def parse_union(
        self, cursor
    ) -> Tuple[Optional[yace.model.base.Entity], Optional[yace.errors.Error]]:
        """Parse union declaration"""

        try:
            return yace.model.derivedtypes.Union(
                sym=cursor.spelling, doc=Docstring.from_cursor(cursor)
            )
        except ValidationError as exc:
            return None, ParseError.from_exception(exc, cursor)

    def parse_typedef(
        self, cursor
    ) -> Tuple[Optional[yace.model.base.Entity], Optional[yace.errors.Error]]:
        """Parse typedef declarations.

        Function-pointer typedefs produce FunctionPointer entities.
        Other typedefs (type aliases) are silently skipped — they are
        resolved transparently when used as field/parameter types.
        """

        underlying_kind = cursor.underlying_typedef_type.kind
        if underlying_kind != clang.cindex.TypeKind.POINTER:
            return None, None

        pointee = cursor.underlying_typedef_type.get_pointee()
        if pointee.kind != clang.cindex.TypeKind.FUNCTIONPROTO:
            return None, None

        parameters = []
        for child in cursor.get_children():
            if child.kind not in [CursorKind.PARM_DECL]:
                log.warning(f"Skipping: {child} not PARM_DECL")
                continue

            ptyp, error = typekind_to_typespec(child.type, child)
            if error:
                return None, error

            parameters.append(
                yace.model.functiontypes.Parameter(
                    typ=ptyp,
                    sym=child.spelling,
                    doc=Docstring.from_cursor(child),
                )
            )

        try:
            rtyp, error = typekind_to_typespec(pointee.get_result(), cursor)
            if error:
                return None, error

            return (
                yace.model.functiontypes.FunctionPointer(
                    sym=cursor.spelling,
                    doc=Docstring.from_cursor(cursor),
                    ret=rtyp,
                    parameters=parameters,
                ),
                None,
            )
        except ValidationError as exc:
            return None, ParseError.from_exception(exc, cursor)

    def parse_function(self, cursor):
        """Parse function declaration"""

        parameters = []
        for child in cursor.get_arguments():
            if child.kind not in [CursorKind.PARM_DECL]:
                return None, ParseError.from_cursor(
                    f"Skipping: {child.spelling} {cursor.spelling} not PARM_DECL",
                    cursor,
                )

            ptyp, error = typekind_to_typespec(child.type, child)
            if error:
                return None, error

            parameters.append(
                yace.model.functiontypes.Parameter(
                    typ=ptyp,
                    sym=child.spelling,
                    doc=Docstring.from_cursor(child),
                )
            )

        try:
            rtyp, error = typekind_to_typespec(cursor.result_type, cursor)
            if error:
                return None, error

            return (
                yace.model.functiontypes.Function(
                    sym=cursor.spelling,
                    doc=Docstring.from_cursor(cursor),
                    ret=rtyp,
                    parameters=parameters,
                ),
                None,
            )

        except ValidationError as exc:
            return None, ParseError.from_exception(exc, cursor)

    def tu_to_data(self, tu, path: Path) -> Tuple[List[Any], List[Error]]:
        """Transform the given translation-unit (tu) to data"""

        errors: List[Error] = []
        path.resolve()

        entities = []
        expression_macros: List[str] = []

        for cursor in tu.cursor.get_children():
            if not cursor.location.file:
                log.debug("Ignored definition which is not from the file")
                continue

            if Path(cursor.location.file.name).name != path.name:
                log.debug(f"Skipped {cursor.location.file.name} != {path.name}")
                continue

            try:
                match cursor.kind:
                    case CursorKind.ENUM_DECL:
                        entity, error = self.parse_enum(cursor)
                    case CursorKind.STRUCT_DECL | CursorKind.UNION_DECL:
                        entity, error = self.parse_record(cursor)
                    case CursorKind.TYPEDEF_DECL:
                        entity, error = self.parse_typedef(cursor)
                    case CursorKind.FUNCTION_DECL:
                        entity, error = self.parse_function(cursor)
                    case CursorKind.MACRO_DEFINITION:
                        entity, error = self.parse_macro(cursor)
                        # Collect unresolved macros for second-pass enum trick
                        # evaluation — covers both expression macros (ntokens>2)
                        # and symbolic aliases (#define FOO BAR)
                        if error and (
                            "unsupported amount of ntokens" in str(error)
                            or "Failed converting" in str(error)
                        ):
                            expression_macros.append(cursor.spelling)
                    case CursorKind.INCLUSION_DIRECTIVE:
                        entity, error = self.parse_inclusion_directive(cursor)
                    case CursorKind.MACRO_INSTANTIATION:
                        log.debug(f"Skipping macro instantiation: {cursor.spelling}")
                        continue
                    case _:
                        error = Error(message=f"Unhandled cursor({cursor.kind})")
            except Exception as exc:
                errors.append(Error(message=f"Exception parsing {cursor.spelling}: {exc}"))
                continue

            if error:
                errors.append(error)
                continue

            if not entity:
                log.debug("No entity and no error for current cursor")
                continue

            entities.append(entity.model_dump())

        # Second pass: evaluate expression macros via the enum trick
        if expression_macros:
            evaluated = self.evaluate_expression_macros(expression_macros, path)
            if evaluated:
                log.debug(
                    f"Evaluated {len(evaluated)}/{len(expression_macros)} "
                    "expression macros"
                )
                # Remove errors for successfully evaluated macros
                resolved_msgs = set()
                for name in evaluated:
                    resolved_msgs.add(f"'#define {name}'")  # expression macros
                    resolved_msgs.add(f"sym({name}),")  # alias macros
                errors = [
                    e for e in errors
                    if not any(msg in str(e) for msg in resolved_msgs)
                ]
                # Add Define entities for evaluated macros
                for name, value in evaluated.items():
                    if value < 0:
                        val = constants.Dec(lit=value)
                    elif value > 255:
                        val = constants.Hex(lit=value)
                    else:
                        val = constants.Dec(lit=value)
                    entities.append(
                        constants.Define(sym=name, val=val).model_dump()
                    )

        return entities, errors


def c_to_yace(paths: List[Path], output: Path) -> Tuple[int, List[Error]]:
    """Best-effort transformation of a C Header to a YACE File

    Returns a tuple of (entity_count, errors). The YAML is written regardless
    of errors — unsupported constructs are skipped and reported.
    """

    entity_count = 0
    errors: List[Error] = []

    output.mkdir(parents=True, exist_ok=True)

    parser = CParser()
    for path in [p.resolve() for p in paths]:
        try:
            tu = parser.parse_file(path)
        except Exception as exc:
            errors.append(Error(message=f"Failed to parse translation unit: {exc}"))
            continue

        entities, parse_errors = parser.tu_to_data(tu, path)
        errors += parse_errors
        entity_count += len(entities)

        stem = path.stem
        data = {
            "meta": {
                "lic": "Unknown License",
                "version": "0.0.1",
                "author": "Foo Bar <foo@example.com>",
                "project": stem,
                "prefix": stem,
                "brief": "Brief Description",
                "full": "Full Description",
                "pkg": "",
            },
        }
        data["entities"] = entities

        model = Model(**data)
        model.to_file(output / path.with_suffix(".yaml").name)

        # Write status file
        status_path = output / path.with_suffix(".status").name
        with status_path.open("w") as status:
            status.write(f"Parsed {len(entities)} entities")
            if parse_errors:
                status.write(f", skipped {len(parse_errors)} constructs")
            status.write("\n")

            if parse_errors:
                status.write("\nSkipped:\n")
                for error in parse_errors:
                    status.write(f"  {error}\n")

    return entity_count, errors
