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
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

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
        assert tokens[0] == "const", tokens[0]

    unsigned = match.group("unsigned") == "u"
    width = int(match.group("width"))
    shorthand = "".join(["u" if unsigned else "i", str(width), "_tspec"])
    inst = SHORTHAND_TO_CLS.get(shorthand)()

    assert inst.c_spelling() == " ".join(tokens[:-1])

    return inst


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

        case TypeKind.ELABORATED | TypeKind.RECORD:
            *head, keyword, sym = tobj.spelling.split()
            match keyword:
                case "union":
                    return (
                        datatypes.Record(
                            sym=sym, union=True, canonical=canonical, const=const
                        ),
                        None,
                    )
                case "struct":
                    return (
                        datatypes.Record(
                            sym=sym, struct=True, canonical=canonical, const=const
                        ),
                        None,
                    )
                case "enum":
                    return (
                        datatypes.Enumeration(
                            sym=sym, enum=True, canonical=canonical, const=const
                        ),
                        None,
                    )
                case _:
                    return None, ParseError.from_cursor(
                        message=f"kw({keyword}), sym({sym}), head({head}); {tobj}",
                        cursor=cursor,
                    )

        case TypeKind.POINTER:
            pointee = tobj.get_pointee()

            # Special-case for string-representation
            if pointee.is_const_qualified() and pointee.kind == TypeKind.CHAR_S:
                return datatypes.CString(), None

            # General case pointer to anything, everything, or nothing ;)
            typespec, error = typekind_to_typespec(pointee, cursor)
            if error:
                return None, error

            return (
                datatypes.Pointer(pointee=typespec, canonical=canonical, const=const),
                None,
            )

        case TypeKind.TYPEDEF:
            if not (
                ((canonical := tobj.get_canonical()).kind == TypeKind.POINTER)
                and (pointee := canonical.get_pointee()).kind == TypeKind.FUNCTIONPROTO
            ):
                return None, ParseError.from_cursor(
                    message=f"Unsuported typedef({tobj.get_canonical().kind})",
                    cursor=cursor,
                )

            return datatypes.FunctionPointer(sym=tobj.spelling, doc=""), None

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
        r"(?:\"(?P<str>[\s\wa-zA-Z0-9]+)\")"  # String constants
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
        if searchpath:
            Config().set_library_path(searchpath)

        self.index = Index.create()

    def parse_file(self, path: Path):
        """Parse the given file into a :class:`clang.cindex.TranslationUnit`."""

        return self.index.parse(
            path, options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        )

    def parse_macro(
        self, cursor
    ) -> Tuple[Optional[yace.model.base.Entity], Optional[yace.errors.Error]]:
        """TODO: hex + int"""

        tokens = [tok.spelling for tok in cursor.get_tokens()]
        log.debug(f"({cursor.spelling}), tokens({tokens})")

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
                        return None, ParseError.from_cursor(
                            f"unexpected '{field.kind}'; with children",
                            cursor=field,
                        )

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
        """Parse function-pointer typedefs that are pointers to function prototypes"""

        underlying_kind = cursor.underlying_typedef_type.kind
        if underlying_kind != clang.cindex.TypeKind.POINTER:
            return None, ParseError.from_cursor(
                f"{cursor.canonical.kind} not supported for {underlying_kind})", cursor
            )

        pointee = cursor.underlying_typedef_type.get_pointee()
        if pointee.kind != clang.cindex.TypeKind.FUNCTIONPROTO:
            return None, ParseError.from_cursor("No support for typedef", cursor)

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

        print("Type, not a function-pointer")

        return None, ParseError.from_cursor("Unsupported typedef-decl.", cursor)

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
        for cursor in tu.cursor.get_children():
            if not cursor.location.file:
                log.debug("Ignored definition which is not from the file")
                continue

            if Path(cursor.location.file.name).name != path.name:
                log.debug(f"Skipped {cursor.location.file.name} != {path.name}")
                continue

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
                case CursorKind.INCLUSION_DIRECTIVE:
                    entity, error = self.parse_inclusion_directive(cursor)
                case _:
                    error = Error(message=f"Unhandled cursor({cursor.kind})")

            if error:
                errors.append(error)
                continue

            if not entity:
                log.debug("No entity and no error for current cursor")
                continue

            entities.append(entity.model_dump())

        return entities, errors


def c_to_yace(paths: List[Path], output: Path) -> List[Error]:
    """Optimistically / best-offort transformation of a C Header to YACE File"""

    errors: List[Error] = []

    output.mkdir(parents=True, exist_ok=True)

    parser = CParser()
    for path in [p.resolve() for p in paths]:
        tu = parser.parse_file(path)

        entities, parse_errors = parser.tu_to_data(tu, path)
        errors += parse_errors

        data = {
            "meta": {
                "lic": "Unknown License",
                "version": "0.0.1",
                "author": "Foo Bar <foo@example.com>",
                "project": "foo",
                "prefix": "foo",
                "brief": "Brief Description",
                "full": "Full Description",
            },
        }
        data["entities"] = entities

        model = Model(**data)
        model.to_file(output / path.with_suffix(".yaml").name)

    return errors
