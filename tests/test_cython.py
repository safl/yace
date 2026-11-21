# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Tests of the Cython target: the .pxd, checked against the header, and the
behaviour of the Cython module that differs from the ctypes module.
test_python.py tests the behaviour that the two modules share, against both.
"""

import gc
import importlib.util
import io
import json
import os
import subprocess
import sys
import sysconfig
import weakref

import pytest
import yaml

from tests.conftest import (
    BITS,
    ESCAPED,
    ESCAPED_VALUE,
    HEADERS,
    PACKED,
    PACKED_PRINTED,
    SKIPPED,
    needs_cc,
    needs_cython,
)
from tests.test_python import (
    BUFFERS,
    PHYS,
    REGISTRATIONS,
    SHADOWED_REGISTRATION,
    compiled,
    json_lines,
)
from yace.compiler import process
from yace.ir import types
from yace.targets.cython import cygen
from yace.targets.cython import target as cython_target

pytestmark = [needs_cc, needs_cython]

needs_mypy = pytest.mark.skipif(
    importlib.util.find_spec("mypy") is None, reason="no mypy"
)

# Records, enums, defines and functions whose names Python, Cython or the
# generated module already uses
NAMED = (
    "#include <stdint.h>\n"
    "struct foo_bar { int class; };\nstruct foo__bar { int x; };\n"
    "struct api_buf { int len; };\ntypedef struct api_buf api_buf;\n"
    "struct api_rec { int pr, fpr, to_dict; char name[4]; int16_t grid[2][2];"
    " const char *label; void *nil; struct api_buf at; struct api_buf two[2]; };\n"
    "enum kind { None = 1, DEF = 2 };\ntypedef enum kind kind_t;\n"
    '#define API_S "s"\n#define API_N 3\n'
    "int pass(int lambda);\nint json(int sys);\nint include(int cdef);\n"
    "int len(const struct api_buf *b, kind_t k);\n"
)

# C names that Cython reserves, and the name 'tag' for both a struct tag and a
# function. C keeps the two in separate namespaces; Cython does not.
RESERVED = (
    "/** S */\nstruct api_s {\n\tint class; ///< C\n\tint include; ///< I\n};\n"
    "/** Tag */\nstruct tag { int a; };\n"
    "/** Kinds */\nenum kind { None = 1, DEF = 2 };\n"
    "/** Include */\nint include(int cdef);\n"
    "/** Tag */\nint tag(const struct tag *t, const struct api_s *s);\n"
)


def test_names_cython_reserves_are_declared_by_their_c_names(parse, tmp_path):
    model, _ = parse(RESERVED)
    # process() compiles the check of the .pxd, and the module
    assert process(model, ["cython"], tmp_path) == []

    pxd = (tmp_path / "cython" / "api.pxd").read_text().splitlines()
    for line in (
        '        int class_ "class"',
        '        int include_ "include"',
        '    struct tag_ "tag":',
        '        None_ "None"',
        '        DEF_ "DEF"',
        '    int include_ "include"(int cdef_)',
        "    int tag(const tag_ *t, const api_s *s)",
    ):
        assert line in pxd
    ns = compiled(tmp_path)
    assert ns["include"].__name__ == "include" and "tag" in ns
    assert ns["Kind"].DEF == 2 and ns["DEF"] == 2
    assert ns["ApiS"](class_=1).to_dict() == {"class": 1, "include": 0}


def test_a_declaration_that_disagrees_with_the_header_fails_the_check(
    parser, tmp_path, monkeypatch
):
    model, _ = parser.parse(HEADERS / "valid.h")
    decl = cygen.Names.decl

    def signed(self, typ, *args):
        if isinstance(typ, types.Builtin) and typ.name == "uint32_t":
            typ = typ.model_copy(update={"name": "int32_t"})
        return decl(self, typ, *args)

    # signed() declares uint32_t as int32_t, in the .pxd and in its check alike
    monkeypatch.setattr(cygen.Names, "decl", signed)
    failures = process(model, ["cython"], tmp_path)
    assert len(failures) == 1
    assert failures[0].startswith("cython: compiling the check of the .pxd failed")


# Declarations that Cython spells differently from C: const pointers, and
# fields of function pointer type, which Cython does not declare nogil
SPELLED = (
    "#include <stddef.h>\n"
    "/** P */\nstruct api_p {\n\tint x; ///< X\n};\n"
    "/** Cb */\ntypedef int (*api_cb)(void *arg, int v);\n"
    "/** F */\nstruct api_f {\n"
    "\tint (*fp)(int, ...); ///< Fp\n"
    "\tvoid *(*alloc)(size_t); ///< Alloc\n"
    "\tconst struct api_p *const *pp; ///< Pp\n"
    "\tapi_cb cb; ///< Cb\n};\n"
    "/** Run */\nint api_run(int argc, char *const argv[]);\n"
    "/** Ptr */\nvoid api_ptr(int *const p);\n"
)


def test_function_pointer_fields_and_const_pointers_pass_the_check(parse, tmp_path):
    model, _ = parse(SPELLED)
    assert process(model, ["cython"], tmp_path) == []

    pxd = (tmp_path / "cython" / "api.pxd").read_text()
    assert "    int api_run(int argc, char *const *argv)" in pxd
    assert "        const api_p *const *pp" in pxd
    assert (
        "referenced before assignment"
        not in (tmp_path / "cython" / "cython.log").read_text()
    )


def test_the_check_needs_a_c_compiler(parse, tmp_path, monkeypatch):
    model, _ = parse(SPELLED)
    monkeypatch.setenv("CC", "/nonexistent/cc")

    failures = process(model, ["cython"], tmp_path)
    assert failures == ["cython: no C compiler ('/nonexistent/cc'); set CC"]


def test_the_check_needs_cython(parse, tmp_path, monkeypatch):
    model, _ = parse(SPELLED)
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args: None if name == "Cython" else find_spec(name, *args),
    )

    failures = process(model, ["cython"], tmp_path)
    assert len(failures) == 1 and failures[0].startswith("cython: no Cython in ")


def test_the_check_of_the_pxd_takes_no_address_of_a_packed_field(parse, tmp_path):
    model, _ = parse(PACKED)
    assert process(model, ["cython"], tmp_path) == []

    assert "packed struct api_k:" in (tmp_path / "cython" / "api.pxd").read_text()
    log = (tmp_path / "cython" / "cython.log").read_text()
    assert "pxd_check.c" in log and "address-of-packed-member" not in log


def test_the_subset_prints_as_the_c_api_does(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["capi", "cython"], tmp_path) == []

    for fmt, load in (("yaml", yaml.safe_load_all), ("json", json_lines)):
        c_out = (tmp_path / "capi" / f"check.{fmt}").read_text()
        cy_out = (tmp_path / "cython" / f"check.{fmt}").read_text()
        assert list(load(cy_out)) == list(load(c_out))


def test_headers_outside_the_subset_still_bind(parse, tmp_path):
    model, diagnostics = parse(
        "#include <stdint.h>\n"
        "#include <stdio.h>\n"
        "struct s { uint32_t tag; union { uint64_t i; double f; }; };\n"
        "typedef struct { int x; } point;\n"
        "typedef uint32_t id;\n"
        "struct outer { struct inner { int a; } in; unsigned int bits : 3;"
        " id ids[2]; };\n"
        "struct flex { uint32_t n; uint8_t data[]; };\n"
        "struct uses { FILE *stream; point at; };\n"
        "int f(const point *p, int values[4]);\n"
        "int g(int, char *);\n"
        "int log_it(const char *fmt, ...);\n"
        "enum e { A, B };\n"
        "enum e h(struct s by_value);\n"
    )
    assert diagnostics
    assert process(model, ["cython"], tmp_path) == []

    ns = compiled(tmp_path)
    assert "log_it" not in ns  # a variadic function is not bound
    outer = ns["Outer"](bits=9)
    assert (outer.bits, list(outer.ids)) == (1, [0, 0])
    assert ns["Flex"]().to_dict() == {"n": 0}
    assert ns["Uses"]().stream is None


def test_names_are_made_usable(parse, tmp_path):
    model, _ = parse(
        "struct foo_bar { int class; };\n"
        "struct foo__bar { int x; };\n"
        '/** Ends in a quote, "so" */\nint pass(int lambda);\n'
        "enum kind { None = 1 };\n"
        "int json(int sys);\n"
        "int sys(int os);\n"
    )
    assert process(model, ["cython"], tmp_path) == []

    ns = compiled(tmp_path)
    assert ns["foo_bar"]().to_dict() == {"class": 0}
    assert ns["foo__bar"]().to_dict() == {"x": 0}
    assert ns["pass_"].__doc__.startswith('Ends in a quote, "so"')
    assert ns["Kind"].None_ == 1
    assert str(ns["foo__bar"]()) == "foo__bar:\n  x: 0\n"


def test_a_field_named_as_a_keyword_is_reached_by_its_escaped_name(parse, tmp_path):
    model, _ = parse(
        "/** R */\nstruct api_r {\n\tint async; ///< A\n"
        "\tint class; ///< C\n\tint class_; ///< Taken\n};\n"
    )
    assert process(model, ["cython"], tmp_path) == []

    record = compiled(tmp_path)["ApiR"]()
    record.async_ = 3
    with pytest.raises(AttributeError):
        record.unknown = 1  # a record has no attributes but its fields
    assert record.to_dict() == {"async": 3, "class": 0, "class_": 0}


def test_a_field_named_self_is_given_to_the_constructor_by_its_name(parse, tmp_path):
    model, _ = parse("/** S */\nstruct api_s {\n\tvoid *self; ///< S\n};\n")
    assert process(model, ["cython"], tmp_path) == []

    record = compiled(tmp_path)["ApiS"]
    assert (record(self=16).self, record(32).self, record().self) == (16, 32, None)
    stub = (tmp_path / "cython" / "api.pyi").read_text()
    assert "def __init__(_self, self: int | None = None) -> None: ..." in stub


def test_records_are_views_of_c_memory_and_arrays_are_buffers(parse, tmp_path):
    model, _ = parse(
        "#include <stdbool.h>\n#include <stdint.h>\n"
        "enum api_e { API_E_A = -1, API_E_B = 2, API_E_C = 2 };\n"
        "typedef enum api_e api_e_t;\n"
        "struct api_p { int32_t x; int32_t y; };\n"
        "struct api_v { bool flag; char letter; double d; enum api_e e;\n"
        "\tapi_e_t es[3]; char name[4]; int16_t grid[2][2]; struct api_p at;\n"
        "\tstruct api_p path[2]; const char *label; void *nil; };\n"
        "union api_u { uint32_t u; struct api_p p; };\n" + BITS
    )
    assert process(model, ["cython"], tmp_path) == []

    api = compiled(tmp_path)
    v = api["ApiV"](flag=True, letter=b"y", d=-2.5, e=-1, es=(2, 7, -1), name=b"ab")
    grid = v.grid
    grid[1, 0] = -5
    at = v.at
    at.x = 3
    v.path[1].y, v.label = 4, b"hi"
    del v
    gc.collect()
    # 'grid' and 'at' are views, and each keeps the deleted record alive
    assert (grid.tolist(), at.x) == ([[0, 0], [-5, 0]], 3)
    v = api["ApiV"](flag=True, letter=b"y", d=-2.5, e=-1, es=(2, 7, -1), name=b"ab")
    v.grid[1, 0] = -5
    v.at.x, v.path[1].y, v.label = 3, 4, b"hi"
    assert repr(v) == (
        "ApiV(flag=True, letter=b'y', d=-2.5, e=ApiE.API_E_A,"
        " es=[ApiE.API_E_B, 7, ApiE.API_E_A], name=b'ab', grid=[[0, 0], [-5, 0]],"
        " at=ApiP(x=3, y=0), path=[ApiP(x=0, y=0), ApiP(x=0, y=4)],"
        " label='hi', nil=None)"
    )
    assert memoryview(v.es).format == "i" and v.es.nbytes == 12
    v.grid, v.es = [[1, 2], (3, 4)], [-1, 2, 2]
    assert (v.grid.tolist(), v.es.tolist()) == ([[1, 2], [3, 4]], [-1, 2, 2])
    with pytest.raises(ValueError):
        v.grid = [[1, 2], [3]]
    with pytest.raises(ValueError):
        v.name = b"abcde"
    with pytest.raises(TypeError):
        v.name = [1]
    assert v.name == b"ab"
    assert repr(api["ApiU"](u=0xFFFFFFFF)) == "ApiU(u=4294967295, p=ApiP(x=-1, y=0))"


def test_a_string_set_is_kept_by_every_record_whose_memory_points_to_it(
    parse, tmp_path
):
    """A string field holds a pointer to the bytes given, and Python frees the
    bytes with their last reference. The record holding the C memory therefore
    keeps the bytes when they are set through a view, and a copy of a record
    keeps the bytes that the record keeps."""

    model, _ = parse(
        "struct api_in { const char *label; int x; };\n"
        "struct api_out { struct api_in in; struct api_in two[2]; };\n"
        "struct __attribute__((packed)) api_k { char tag; struct api_in in;"
        " struct api_in two[2]; };\n"
    )
    assert process(model, ["cython"], tmp_path) == []
    api = compiled(tmp_path)

    class Label(bytearray):
        """Bytes that a weak reference can be made to"""

    def labelled():
        label = Label(b"label")
        return api["ApiIn"](label=label), weakref.ref(label)

    def kept(ref):
        gc.collect()
        return ref() is not None

    out = api["ApiOut"]()
    label = Label(b"label")
    ref = weakref.ref(label)
    out.in_.label = label  # set through the view out.in_, which nothing keeps
    del label
    assert kept(ref) and out.in_.label == "label"
    with pytest.raises(TypeError):
        out.in_.label = 5
    assert kept(ref) and out.in_.label == "label"
    out.in_.label = None
    assert not kept(ref)

    for cls in ("ApiOut", "ApiK"):
        made, ref = labelled()
        out = api[cls](in_=made)
        del made
        assert kept(ref), cls
        got = out.in_
        del out
        assert kept(ref) and got.label == "label", cls
        del got
        assert not kept(ref), cls

        made, ref = labelled()
        out = api[cls](two=[made, made])
        del made
        assert kept(ref), cls
        got = out.two[1]
        del out
        assert kept(ref) and got.label == "label", cls
        del got
        assert not kept(ref), cls


def test_a_field_of_bits_prints_its_parts_and_they_are_properties(parse, tmp_path):
    model, _ = parse(BITS)
    assert process(model, ["cython"], tmp_path) == []

    api = compiled(tmp_path)
    status = api["ApiStatus"](0x8A05, 0x8000000100000002)
    assert str(status) == (
        "api_status:\n"
        "  code: {val: 0x8a05, type: 0x5, delay: 0xa, dnr: 0x1}\n"
        "  wide: {val: 0x8000000100000002, low: 0x2, top: 0x1}\n"
    )
    status.code_delay = 3
    assert status.code == 0x8305 and status.code_type == 5
    with pytest.raises(ValueError, match="code_delay is 4 bits, not 16"):
        status.code_delay = 16
    assert api["ApiStatus"].code_type.__doc__ == "Kind; bits 2:0 of 'code'"


def test_a_packed_record_is_printed_as_in_c(parse, tmp_path):
    model, _ = parse(PACKED)
    assert process(model, ["cython"], tmp_path) == []

    api = compiled(tmp_path)
    packed, point = api["ApiK"], api["ApiP"]
    value = packed(
        tag=1,
        value=0xDEADBEEF,
        at=point(-2, 3),
        path=(point(4, 5), point(6, 7)),
        pair=(8, 9),
        type=0x1A,
    )
    out = io.StringIO()
    packed.fpr(out, value, api["API_PR_YAML"])
    packed.fpr(out, value, api["API_PR_JSON"])
    assert out.getvalue() == PACKED_PRINTED


def test_skipped_records_padding_bits_and_string_defines_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["cython"], tmp_path / "skipped") == []
    model, _ = parse(ESCAPED)
    assert process(model, ["cython"], tmp_path) == []
    assert compiled(tmp_path)["API_S"] == ESCAPED_VALUE


def test_the_module_is_built_for_the_full_api(parse, tmp_path):
    model, _ = parse("int api_add(int a, int b);\n")
    assert process(model, ["cython"], tmp_path) == []
    log: list = []
    assert cython_target.build(tmp_path / "cython", "api", log) == []
    assert "Py_LIMITED_API" not in "\n".join(log)
    made = tmp_path / "cython" / f"api{sysconfig.get_config_var('EXT_SUFFIX')}"
    assert made.is_file() and "add" in compiled(tmp_path)


def test_typedefs_alias_their_class_and_fields_named_as_printers_print(parse, tmp_path):
    model, _ = parse(
        "struct api_buf { int len; };\ntypedef struct api_buf api_buf;\n"
        "struct api_pt { int x; };\ntypedef struct api_pt api_pt_t;\n"
        "enum api_kind { API_KIND_A = 1 };\ntypedef enum api_kind api_kind;\n"
        "struct api_rec { int pr, fpr, to_dict; };\n"
        "int api_len(const api_buf *b, api_kind k);\n"
    )
    # process() runs the generated check, which prints ApiRec
    assert process(model, ["cython"], tmp_path) == []

    api = compiled(tmp_path)
    assert api["ApiBuf"]._yace_name == "api_buf" and api["ApiPtT"] is api["ApiPt"]
    assert str(api["ApiRec"](1, 2, 3)) == "api_rec:\n  pr: 1\n  fpr: 2\n  to_dict: 3\n"
    check = (tmp_path / "cython" / "check.json").read_text().splitlines()
    assert json.loads(check[-1]) == {"pr": 0, "fpr": 0, "to_dict": 0}


def test_closures_kept_by_a_handle_whose_destructor_fails_are_kept(parse, tmp_path):
    from tests.test_rust import doc, library

    header = (
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Close", "@destroys h", "@errno")
        + "int api_close(struct api_h *h);\n"
        + doc("On", "@lifetime cb handle")
        + "void api_on(struct api_h *h, api_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cython"], tmp_path, check=False) == []
    built = library(
        tmp_path,
        header + "static int h;\n"
        "int api_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }\n"
        "int api_close(struct api_h *p) { (void)p; return -5; }\n"
        "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ (void)p; (void)cb; (void)arg; }\n",
    )
    api = compiled(tmp_path, built)

    handle = api["open"]()
    handle.on(lambda v: v)
    with pytest.raises(OSError):
        handle.close()
    handle = api["open"]()
    handle.on(lambda v: v)
    del handle  # __dealloc__ calls api_close(), which fails
    assert len(api["_KEPT"]) == 2


def test_arrays_of_strings_are_given_and_returned_as_strings(parse, tmp_path):
    from tests.test_rust import doc, library

    header = (
        "#include <stddef.h>\n"
        + doc("Join", "@arrparam words W")
        + "size_t api_join(const char *const *words, size_t words_len);\n"
        + doc("Names", "@arrparam[out] names N")
        + "void api_names(const char **names, size_t names_len);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cython"], tmp_path, check=False) == []
    built = library(
        tmp_path,
        "#include <string.h>\n" + header + "size_t api_join(const char *const *w,"
        " size_t n)\n{ size_t s = 0; while (n--) s += strlen(w[n]); return s; }\n"
        "void api_names(const char **names, size_t n)\n"
        '{ for (size_t i = 0; i < n; i++) names[i] = i ? "name" : NULL; }\n',
    )
    api = compiled(tmp_path, built)

    assert api["join"](["a", b"bc", "é"]) == 5
    assert api["names"](3) == [None, "name", "name"]
    stub = (tmp_path / "cython" / "api.pyi").read_text()
    assert "def join(words: Sequence[str | bytes]) -> int:" in stub
    assert "def names(names_len: int) -> list[str | None]:" in stub


def test_a_capacity_whose_size_in_bytes_overflows_raises(parse, tmp_path):
    """The module allocates the array at the capacity given, because C is told
    that the array has that capacity"""

    from tests.test_rust import doc, library

    header = (
        "#include <stddef.h>\n#include <stdint.h>\n"
        + doc("Fill", "@arrparam[out] vals V")
        + "void api_fill(int32_t *vals, size_t vals_len);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cython"], tmp_path, check=False) == []
    built = library(
        tmp_path,
        header + "void api_fill(int32_t *vals, size_t n)\n"
        "{ if (n > 2) return; while (n--) vals[n] = 7; }\n",
    )
    api = compiled(tmp_path, built)

    assert api["fill"](2).tolist() == [7, 7]
    with pytest.raises((MemoryError, OverflowError)):
        api["fill"](2**62 + 1)  # times 4 bytes is 4 modulo 2**64


def test_parameters_named_as_what_a_body_calls_pass_their_values_to_c(parse, tmp_path):
    from tests.test_rust import doc, library

    header = (
        "#include <stddef.h>\nstruct api_p { int x; };\n"
        + doc("Recs", "@arrparam[out] recs R")
        + "void api_recs(struct api_p *recs, size_t recs_len, int free,"
        " int memset);\n"
        + doc("Raw", "@arrparam[out] raw R", "@param[out] memset M")
        + "void api_raw(void *raw, size_t raw_len, int bytearray, int *memset);\n"
        + doc("Sum", "@arrparam vals V", "@arrparam name N")
        + "int api_sum(const int *vals, size_t vals_len, const char *name,"
        " size_t name_len, int PyBuffer_Release, int PyObject_Length,"
        " int Py_buffer, int uintptr_t);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cython"], tmp_path, check=False) == []
    built = library(
        tmp_path,
        header + "void api_recs(struct api_p *recs, size_t n, int free, int memset)\n"
        "{ while (n--) recs[n].x = free + memset; }\n"
        "void api_raw(void *raw, size_t n, int bytearray, int *memset)\n"
        "{ (void)raw; *memset = (int)n + bytearray; }\n"
        "int api_sum(const int *vals, size_t n, const char *name, size_t m,\n"
        "\tint a, int b, int c, int d)\n"
        "{ (void)vals; (void)name; return (int)(n + m) + a + b + c + d; }\n",
    )
    api = compiled(tmp_path, built)

    assert [each.x for each in api["recs"](2, 3, 4)] == [7, 7]
    assert api["raw"](2, 5) == (bytearray(2), 7)
    assert api["sum"]([1, 2], "abc", 10, 20, 30, 40) == 105


# Parameters and results that the stub must type as the module converts them:
# an [out] array of bool, a 'char *' parameter, and a callback returning a string
TYPED = (
    "#include <stdbool.h>\n#include <stddef.h>\n"
    "typedef const char *(*api_name_cb)(void *arg);\n"
    "/**\n * Flags\n * @arrparam[out] flags F\n */\n"
    "void api_flags(bool *flags, size_t flags_len);\n"
    "/**\n * Fill\n */\nint api_fill(char *buf);\n"
    "/**\n * Name\n * @lifetime cb call\n */\n"
    "int api_name(api_name_cb cb, void *arg);\n"
    "/**\n * Buf\n */\nvoid *api_buf(void);\n"
)


def test_the_stub_types_a_pointer_given_as_its_address(parse, tmp_path):
    from tests.test_rust import library

    model, _ = parse(TYPED)
    assert process(model, ["cython"], tmp_path, check=False) == []
    built = library(
        tmp_path,
        TYPED + "static char buf[4];\n"
        "void api_flags(bool *flags, size_t n) { while (n--) flags[n] = n & 1; }\n"
        "int api_fill(char *p) { return p == buf; }\n"
        "int api_name(api_name_cb cb, void *arg) { return cb(arg) == buf; }\n"
        "void *api_buf(void) { return buf; }\n",
    )
    api = compiled(tmp_path, built)

    address = api["buf"]()
    assert api["fill"](address) == 1 and api["name"](lambda: address) == 1
    assert api["flags"](3).tolist() == [0, 1, 0]
    stub = (tmp_path / "cython" / "api.pyi").read_text()
    assert "def fill(buf: int) -> int:" in stub
    assert "def name(cb: Callable[[], int]) -> int:" in stub
    assert "def flags(flags_len: int) -> array.array[int]:" in stub


# Functions, methods, fields and a handle with the Python names that the stub
# uses in its annotations and decorators
SHADOWING = (
    "#include <stddef.h>\n#include <stdint.h>\nstruct api_buffer;\n"
    "struct api_r { uint32_t bytes, list, str, property, Any; char name[4];"
    " const char *label; int vals[3]; struct api_r *next; };\n"
    "struct api_s { void *self; };\n"
    "/**\n * Open\n * @param[out] b B\n * @errno\n */\n"
    "int api_buffer_open(struct api_buffer **b);\n"
    "/**\n * Close\n * @destroys b\n */\nvoid api_buffer_close(struct api_buffer *b);\n"
    "/**\n * List\n * @arrparam[out] vals V\n */\n"
    "void api_buffer_list(struct api_buffer *b, int *vals, size_t vals_len);\n"
    "/**\n * Bytes\n * @arrparam vals V\n */\n"
    "void api_buffer_bytes(struct api_buffer *b, const int *vals, size_t vals_len);\n"
    "/**\n * Int\n */\nint api_buffer_int(struct api_buffer *b, const char *s);\n"
    "/**\n * List\n * @arrparam[out] recs R\n */\n"
    "void api_list(struct api_r *recs, size_t recs_len);\n"
    "/**\n * Array\n * @arrparam[out] vals V\n */\n"
    "void api_array(int *vals, size_t vals_len);\n"
    "/**\n * Int\n * @arrparam vals V\n */\n"
    "int api_int(const int *vals, size_t vals_len);\n"
    "/**\n * Str\n */\nint api_str(const char *s);\n"
    "/**\n * Tuple\n * @param[out] a A\n * @param[out] b B\n */\n"
    "void api_tuple(int *a, int *b);\n"
    "/**\n * Float\n */\ndouble api_float(double d, _Bool b);\n"
)


# SHADOWING has a handle whose class is named Buffer, so the buffer is Buffer_
SHADOWED_BUFFER = SHADOWING + (
    "/**\n * Allocate\n * @param nbytes N\n */\nvoid *api_mem_alloc(size_t nbytes);\n"
    "/**\n * Free\n * @param buf B\n */\nvoid api_mem_free(void *buf);\n"
)


@needs_mypy
@pytest.mark.parametrize(
    "header",
    [
        NAMED,
        RESERVED,
        BITS,
        PACKED,
        TYPED,
        SHADOWING,
        BUFFERS,
        PHYS,
        SHADOWED_BUFFER,
        REGISTRATIONS,
        SHADOWED_REGISTRATION,
    ],
    ids=[
        "named",
        "reserved",
        "bits",
        "packed",
        "typed",
        "shadowing",
        "buffers",
        "phys",
        "shadowed-buffer",
        "registrations",
        "shadowed-registration",
    ],
)
def test_the_stub_is_that_of_the_module(parse, tmp_path, header):
    """stubtest compares the stub with the module, and mypy checks the stub on
    its own. The module is imported with RTLD_LAZY, because the check built the
    module without linking the library. The allowlist names the __init__ of the
    handles and of the classes of an allocated buffer and a registration,
    slots without a signature."""

    model, _ = parse(header)
    assert process(model, ["cython"], tmp_path) == []
    out = tmp_path / "cython"
    (tmp_path / "allowlist.txt").write_text(
        "api.Buffer.__init__\napi.Buffer_.__init__\napi.Dev.__init__\n"
        "api.Registration.__init__\napi.Registration_.__init__\n"
    )
    env = {**os.environ, "PYTHONPATH": str(out), "MYPYPATH": str(out)}
    lazy = (
        "import os, sys; sys.setdlopenflags(os.RTLD_LAZY);"
        " from mypy.stubtest import main; sys.exit(main())"
    )
    stubtest = [sys.executable, "-c", lazy, "api", "--allowlist", "allowlist.txt"]
    run = dict(capture_output=True, text=True, env=env, cwd=tmp_path)
    proc = subprocess.run([*stubtest, "--ignore-unused-allowlist"], **run)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    mypy = [sys.executable, "-m", "mypy", "--strict", "--no-incremental"]
    proc = subprocess.run([*mypy, str(out / "api.pyi")], **run)
    assert proc.returncode == 0, proc.stdout + proc.stderr
