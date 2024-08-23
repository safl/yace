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
import typing
from pathlib import Path

import clang
from clang.cindex import Config, CursorKind, Index

import yace
from yace.model import Model

REGEX_INTEGER_FIXEDWIDTH = "(?P<unsigned>u?)int(?P<width>8|16|32|64|128)_t"

SHORTHAND_DATA = yace.idl.datatypes.classes_shorthand_data()


def typespec_data_from_cursor(cursor) -> dict:
    """
    Returns a typespec for the given cursor

    NOTE:

    * Assumes CursorKind in [PARAM_DECL, FIELD_DECL]
    * Array-Handling; replaces symbolic constants with numerical value

    It currently logs, but does not raise when:

    * Parsing lead to type confusion
    * Parsing hit unknown token

    TODO:

    * Handle bits and bitfields
    * Raise when const appears as anything but the first modifier
    * Raise after loggin error (type confusion and unknown token)
    """

    tokens_all = [tok.spelling for tok in cursor.get_tokens()]

    is_nested = not list(set(["{", "}"]) - set(tokens_all))
    if is_nested:
        return {"key": "typespec", "doc": "Nested struct"}

    is_bits = not list(set([":"]) - set(tokens_all))
    if is_bits:
        return {"key": "bits", "doc": "Bitfield"}

    data = {"key": "typespec"}

    # Skipping the last token;
    #
    # For PARAM and FIELD, then the last token is the identifier and thus not
    # part of the type itself
    last_token_index = -1

    # Skipping the last three tokens as these should be the tokens: "[", "FOO", "]"
    array_len = cursor.type.get_array_size()
    if array_len > 0:
        data["array"] = cursor.type.get_array_size()

        if not (
            len(tokens_all) > 4 and tokens_all[-1] == "]" and tokens_all[-3] == "["
        ):
            log.error("fooo")

        last_token_index = -4

    # Process the non-skipped tokens
    tokens = tokens_all[:last_token_index]
    for index, token in enumerate(tokens, 1):
        match = re.match(REGEX_INTEGER_FIXEDWIDTH, token)
        if match:
            data["integer"] = True
            data["unsigned"] = bool(match.group("unsigned"))
            data["width"] = int(match.group("width"))
            data["width_fixed"] = True
        elif token in ["size_t"]:
            data["size"] = True
            data["unsigned"] = True
            data["width"] = 16
        elif token in ["ssize_t"]:
            data["size"] = True
            data["width"] = 16
        elif token in ["short"]:
            data["integer"] = True
            data["width"] = 8
        # Integer without width modifier
        elif token in ["int"]:
            data["integer"] = True
            if "long" not in tokens and "short" not in tokens:
                data["width"] = 16
        elif token in ["long"]:
            data["integer"] = True
            data["width"] = 32 * sum([tok == token for tok in tokens])
        elif token in ["signed"]:
            data["integer"] = True
        elif token in ["unsigned"]:
            data["integer"] = True
            data["unsigned"] = True
        elif token in ["struct", "union"]:
            data[token] = True
            data["sym"] = tokens[-1]
            break  # last token should be name, anything in between we don't care about
        elif token in ["_Bool", "bool"]:
            data["boolean"] = True
        elif token in ["char"]:
            data["character"] = True
            data["width"] = 8
        elif token in ["*"]:
            if "pointer" not in data:
                data["pointer"] = 0
            data["pointer"] += 1
        elif token in ["const", "static"]:
            data[token] = True
        elif token in ["float"]:
            data["real"] = True
            data["width"] = 32
            data["width_fixed"] = True
        elif token in ["double"]:
            data["real"] = True
            data["width"] = 64
            data["width_fixed"] = True
        elif token in ["void"]:
            data[token] = True
        else:
            log.error(
                "Unknown token: {'%s', %d/%d}, tokens: %s",
                token,
                index,
                len(tokens),
                tokens,
            )

    typecount = sum(
        [
            val is True
            for key, val in data.items()
            if key
            in ["void", "boolean", "character", "integer", "real", "union", "struct"]
        ]
    )
    if typecount != 1:
        log.error("Type confusion; typecount: %d", typecount)

    return data


def typespec_data_to_typ(data):
    """
    Some typespec instances have short-hands, these are used for 'typ'
    keys, this function produces the short or data-identify
    """

    ignore = ["key", "lbl", "array"]
    for shorthand, shorthand_data in SHORTHAND_DATA.items():
        if {key: val for key, val in shorthand_data.items() if key not in ignore} != {
            key: val for key, val in data.items() if key not in ignore
        }:
            continue

        if "array" not in data:
            return shorthand

        # Compact array representation
        #
        # Remove the shorthand-attributes, as the assignment of the shorthand-class
        # carries the attributes, thereby providing the most compact representation
        [data.pop(key) for key in shorthand_data.keys() if key in data]
        data["key"] = shorthand

        return data

    return data


class CParser(object):
    """
    Primitive wrapper around libclang Python bindings
    """

    def __init__(self):
        """Figure out a way to setup the index..."""

        searchpath = print(os.environ.get("YACE_SEARCHPATH_LIBCLANG"))
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

    def parse_macro(self, cursor, data):
        """TODO: hex + int"""

        tokens = list(cursor.get_tokens())

        data["key"] = "define"
        data["val"] = {
            "key": "str",
            "lit": " ".join([token.spelling for token in tokens[1:]]),
        }

    def parse_enum(self, cursor, data):
        """Parse into key-objects enum and enum_value"""

        data["key"] = "enum"
        data["members"] = []

        for child in cursor.get_children():
            if child.kind not in [CursorKind.ENUM_CONSTANT_DECL]:
                log.warning(f"Skipping: {child} not ENUM_CONSTANT_DECL")
                continue

            data["members"].append(
                {
                    "key": "enum_value",
                    "sym": child.spelling,
                    "doc": child.brief_comment,
                    "val": child.enum_value,
                }
            )

    def parse_struct(self, cursor, data):
        data["key"] = "struct"
        data["members"] = []

        for child in cursor.get_children():
            if child.kind not in [CursorKind.FIELD_DECL]:
                log.warning(f"Skipping: {child} not ENUM_CONSTANT_DECL")
                continue

            child_data = {
                "key": "field",
                "sym": child.spelling,
                "doc": child.brief_comment,
                "typ": typespec_data_to_typ(typespec_data_from_cursor(child)),
            }
            data["members"].append(child_data)

    def parse_union(self, cursor, data):
        """Parse union declaration"""

        data["key"] = "union"

    def parse_fun(self, cursor, data):
        """Parse function declaration"""

        data["key"] = "fun"
        data["ret"] = {
            "key": "ret",
            "doc": "TODO: parse / extract return-doc",
        }
        data["parameters"] = []

        for child in cursor.get_children():
            if child.kind not in [CursorKind.PARM_DECL]:
                log.warning(f"Skipping: {child} not PARM_DECL")
                continue

            child_data = {
                "key": "param",
                "typ": typespec_data_to_typ(typespec_data_from_cursor(child)),
                "sym": child.spelling,
                "doc": child.brief_comment,
            }
            data["parameters"].append(child_data)

    def tu_to_data(self, tu):
        """Transform the given translation-unit (tu) to data"""

        entities = []
        for cursor in tu.cursor.get_children():
            if not cursor.location.file:
                log.debug("Ignore definition which is not from the file")
                continue
            entity = {
                "sym": cursor.spelling,
                "doc": cursor.brief_comment if cursor.brief_comment else "",
            }
            if cursor.kind in [CursorKind.ENUM_DECL]:
                self.parse_enum(cursor, entity)
            elif cursor.kind in [CursorKind.STRUCT_DECL]:
                self.parse_struct(cursor, entity)
            elif cursor.kind in [CursorKind.UNION_DECL]:
                self.parse_union(cursor, entity)
            elif cursor.kind in [CursorKind.FUNCTION_DECL]:
                self.parse_fun(cursor, entity)
            elif cursor.kind in [CursorKind.MACRO_DEFINITION]:
                self.parse_macro(cursor, entity)
            else:
                continue

            entities.append(entity)

        return entities


def c_to_yace(paths: typing.List[Path], output: Path):
    """Optimistically / best-offort transformation of a C Header to YACE File"""

    output.mkdir(parents=True, exist_ok=True)

    # TODO: this information / structure should be read from a single point,
    # somewhere in the yace.idl module

    parser = CParser()
    for path in [p.resolve() for p in paths]:
        tu = parser.parse_file(path)

        ydata = {
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
        ydata["entities"] = parser.tu_to_data(tu)

        model = Model(**ydata)
        model.to_file(output / f"{path.stem}_parsed.yaml")

    return 0
