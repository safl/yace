# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import json
import subprocess

import yaml

from tests.conftest import (
    BITS,
    ESCAPED,
    ESCAPED_VALUE,
    HEADERS,
    PACKED,
    PACKED_C,
    PACKED_PRINTED,
    SKIPPED,
    needs_cc,
)
from yace.compiler import process
from yace.ir import decls, types
from yace.ir.model import load
from yace.targets.capi.target import CAPI, CFLAGS


def emit(model, output):
    target = CAPI(output)
    target.emit(model)
    return target


@needs_cc
def test_the_subset_builds_and_prints(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["capi"], tmp_path) == []

    documents = list(yaml.safe_load_all((tmp_path / "capi" / "check.yaml").read_text()))
    by_name = {next(iter(doc)): doc[next(iter(doc))] for doc in documents}
    assert by_name["valid_all"]["grid"] == [[0, 0, 0], [0, 0, 0]]
    assert by_name["valid_all"]["at"] == {"x": 0, "y": 0}
    assert by_name["valid_all"]["label"] is None
    assert by_name["valid_either"]["point"] == {"x": 0, "y": 0}

    lines = (tmp_path / "capi" / "check.json").read_text().splitlines()
    assert json.loads(lines[-1]) == {"number": 0, "point": {"x": 0, "y": 0}}


@needs_cc
def test_headers_outside_the_subset_still_build(parse, tmp_path):
    model, diagnostics = parse(
        "#include <stdint.h>\n"
        "struct s { uint32_t tag; union { uint64_t i; double f; }; };\n"
        "typedef struct { int x; } point;\n"
        "struct outer { struct inner { int a; } in; unsigned int bits : 3; };\n"
        "struct flex { uint32_t n; uint8_t data[]; };\n"
        "int f(const point *p, int values[4]);\n"
    )
    assert diagnostics
    assert process(model, ["capi"], tmp_path / "out") == []


@needs_cc
def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["capi"], tmp_path) == []

    lines = (tmp_path / "capi" / "check.json").read_text().splitlines()
    assert {"a": 0, "b": 0} in [json.loads(line) for line in lines]


@needs_cc
def test_an_api_without_records_builds(parse, tmp_path):
    model, _ = parse(
        "/** The answer */\n#define ANSWER 42\n"
        "/**\n * Sum\n *\n * @param a A\n * @param b B\n *\n * @return a + b\n */\n"
        "int sum(int a, int b);\n"
    )
    assert process(model, ["capi"], tmp_path) == []


@needs_cc
def test_include_directories_reach_the_check(parse, tmp_path):
    (tmp_path / "inc").mkdir()
    (tmp_path / "inc" / "api_types.h").write_text("#define API_TYPES 1\n")
    model, _ = parse('#include "api_types.h"\nint f(void);\n')

    assert process(model, ["capi"], tmp_path / "out")
    assert process(model, ["capi"], tmp_path / "out", include=[tmp_path / "inc"]) == []


@needs_cc
def test_pointer_to_external_function_type_prints(parse, tmp_path):
    (tmp_path / "ext.h").write_text("typedef void ext_fn(void *ctx);\n")
    model, diagnostics = parse('#include "ext.h"\nstruct s { ext_fn *init; };\n')

    assert "parse-error" not in {d.rule for d in diagnostics}
    assert process(model, ["capi"], tmp_path / "out", include=[tmp_path]) == []


@needs_cc
def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["capi"], tmp_path)
    assert failures and "sizeof(valid_point)" in failures[0]


def test_emitting_is_deterministic(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    first = [p.read_bytes() for p in emit(model, tmp_path / "a").emit(model)]
    second = [p.read_bytes() for p in emit(model, tmp_path / "b").emit(model)]
    assert first == second


def test_emitting_from_the_stored_ir_is_the_same(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.save(tmp_path / "valid.yaml")
    loaded = load(tmp_path / "valid.yaml")

    direct = [p.read_bytes() for p in emit(model, tmp_path / "a").emit(model)]
    stored = [p.read_bytes() for p in emit(loaded, tmp_path / "b").emit(loaded)]
    assert direct == stored


@needs_cc
def test_anonymous_records_and_enums_inside_records_build(parse, tmp_path):
    model, _ = parse(
        "/** A */\nstruct api_a {\n\tstruct { int a; } arr[2]; ///< A\n"
        "\tint tail; ///< T\n};\n"
        "/** C */\nstruct api_c {\n\tenum { API_C_A, API_C_B };\n\tint x; ///< X\n};\n"
    )
    assert process(model, ["capi"], tmp_path) == []
    assert [f.name for f in model.find("api_a").fields] == ["arr", "tail"]
    assert [f.name for f in model.find("api_c").fields] == ["x"]


@needs_cc
def test_strings_with_trigraphs_keep_their_value(parse, tmp_path):
    model, _ = parse('/** T */\n#define API_T "??=??/?"\n')
    assert process(model, ["capi"], tmp_path) == []

    program = tmp_path / "t.c"
    program.write_text(
        '#include <stdio.h>\n#include "libapi.h"\n'
        "int main(void) { fputs(API_T, stdout); return 0; }\n"
    )
    cmd = ["cc", "-std=c11", "-Werror", "-I", str(tmp_path / "capi"), str(program)]
    subprocess.run(cmd + ["-o", str(tmp_path / "t")], check=True)
    run = subprocess.run([str(tmp_path / "t")], capture_output=True, text=True)
    assert run.stdout == "??=??/?"


@needs_cc
def test_the_header_is_cxx_too(parse, tmp_path):
    model, _ = parse(
        "/**\n * Ok\n * @param class C\n */\nint ok(int class);\n"
        "typedef int (*api_cb)(void *this, int new);\n"
    )
    assert process(model, ["capi"], tmp_path) == []

    header = (tmp_path / "capi" / "libapi.h").read_text()
    assert "ok(int class_);" in header and "@param class_ C" in header
    cxx = ["c++", "-fsyntax-only", "-x", "c++", "-I", str(tmp_path / "capi"), "-"]
    proc = subprocess.run(
        cxx, input='#include "libapi.h"\n', capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_header_declares_everything(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    header = emit(model, tmp_path).emit(model)[0].read_text()

    assert "struct valid_handle;" in header
    assert "typedef int (*valid_visit_cb)(void *arg, uint64_t value);" in header
    assert "int32_t grid[2][3];" in header
    assert (
        "int64_t\nvalid_visit(struct valid_handle *handle, valid_visit_cb visit,"
        " void *arg);" in header
    )
    assert "const char *\nvalid_fill(" in header
    assert (
        "valid_all_fpr(FILE *stream, const struct valid_all *obj, int flags);" in header
    )
    assert "valid_opt_str(int value);" in header
    for entity in model.entities:
        if isinstance(entity, (decls.Define, decls.Enum, decls.Function)):
            assert entity.name in header


@needs_cc
def test_string_defines_keep_their_value(parse, tmp_path):
    model, _ = parse(ESCAPED)
    assert process(model, ["capi"], tmp_path) == []

    program = tmp_path / "s.c"
    program.write_text(
        '#include <stdio.h>\n#include "libapi.h"\n'
        "int main(void) { fputs(API_S, stdout); return 0; }\n"
    )
    cmd = ["cc", "-I", str(tmp_path / "capi"), str(program), "-o", str(tmp_path / "s")]
    subprocess.run(cmd, check=True)
    run = subprocess.run([str(tmp_path / "s")], capture_output=True, text=True)
    assert run.stdout == ESCAPED_VALUE


def test_the_header_generated_is_in_the_subset(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    emit(model, tmp_path)

    # The pretty-printers take the FILE of stdio.h, which the subset does not
    # define. They also have the names of the printers that yace generates, so
    # yace skips them when it reads its own C API, and generates them again.
    _, diagnostics = parser.parse(tmp_path / "capi" / "libvalid.h")
    allowed = ("external-type", "printer-name")
    assert [d.message for d in diagnostics if d.rule not in allowed] == []


@needs_cc
def test_a_field_of_bits_prints_its_parts(parse, tmp_path):
    model, diagnostics = parse(BITS)
    assert [d for d in diagnostics if d.rule == "bit-mask"] == []
    assert process(model, ["capi"], tmp_path) == []

    program = tmp_path / "b.c"
    program.write_text(
        '#include <string.h>\n#include "libapi.h"\n'
        "int main(int argc, char **argv) {\n"
        "\tstruct api_status s = {0x8a05, 0x8000000100000002ULL};\n"
        "\t(void)argc;\n"
        '\treturn api_status_pr(&s, strcmp(argv[1], "json") ? API_PR_YAML'
        " : API_PR_JSON) < 0;\n}\n"
    )
    cmd = ["cc", *CFLAGS, "-I", str(tmp_path / "capi"), str(program)]
    cmd += [str(tmp_path / "capi" / "api_pp.c"), "-o", str(tmp_path / "b")]
    subprocess.run(cmd, check=True)

    def run(fmt):
        proc = subprocess.run(
            [str(tmp_path / "b"), fmt], capture_output=True, text=True
        )
        assert proc.returncode == 0
        return proc.stdout

    assert run("yaml") == (
        "api_status:\n"
        "  code: {val: 0x8a05, type: 0x5, delay: 0xa, dnr: 0x1}\n"
        "  wide: {val: 0x8000000100000002, low: 0x2, top: 0x1}\n"
    )
    assert json.loads(run("json")) == {
        "code": {"val": 0x8A05, "type": 5, "delay": 10, "dnr": 1},
        "wide": {"val": 0x8000000100000002, "low": 2, "top": 1},
    }


@needs_cc
def test_a_packed_record_is_declared_packed_and_prints(parse, tmp_path):
    model, _ = parse(PACKED)
    assert process(model, ["capi"], tmp_path) == []
    header = (tmp_path / "capi" / "libapi.h").read_text()
    assert "enum api_pr {" in header
    assert "struct __attribute__((packed)) api_k {" in header
    assert "union __attribute__((packed)) api_ku {" in header

    program = tmp_path / "k.c"
    program.write_text(
        '#include "libapi.h"\n'
        f"int main(void) {{\n\tstruct api_k k = {PACKED_C};\n\n"
        "\treturn api_k_pr(&k, API_PR_YAML) < 0 || api_k_pr(&k, API_PR_JSON) < 0;\n}\n"
    )
    cmd = ["cc", *CFLAGS, "-I", str(tmp_path / "capi"), str(program)]
    cmd += [str(tmp_path / "capi" / "api_pp.c"), "-o", str(tmp_path / "k")]
    subprocess.run(cmd, check=True)

    run = subprocess.run([str(tmp_path / "k")], capture_output=True, text=True)
    assert run.returncode == 0
    assert run.stdout == PACKED_PRINTED


SIGNED = """#include <stdint.h>
/** A pair */
typedef struct { int a; } api_pair_t;
/** A count */
typedef uint32_t api_count_t;
/** Sum the pair @return the sum */
int api_sum(const api_pair_t *pair, api_count_t n, const char *name);
"""


@needs_cc
def test_the_signatures_are_checked_against_the_headers(parse, tmp_path):
    model, _ = parse(SIGNED)
    assert process(model, ["capi"], tmp_path / "out", include=[tmp_path]) == []

    source = (tmp_path / "out" / "capi" / "api_signatures.c").read_text()
    assert '#include "api.h"' in source
    assert "int (*)(const api_pair_t *, api_count_t, const char *)" in source


@needs_cc
def test_a_signature_the_header_does_not_have_fails(parse, tmp_path):
    model, _ = parse(SIGNED)
    model.find("api_sum").params[1].typ = types.Builtin(name="int")

    failures = process(model, ["capi"], tmp_path / "out", include=[tmp_path])
    assert len(failures) == 1
    assert "the signatures disagree with the headers" in failures[0]
    assert "api_sum: the IR and the headers disagree on its type" in failures[0]


@needs_cc
def test_without_the_headers_the_signatures_are_said_not_checked(
    parse, tmp_path, caplog
):
    model, _ = parse(SIGNED)
    assert process(model, ["capi"], tmp_path / "out") == []

    note = "the signatures are not checked: api.h not found; give its directory with -I"
    assert note in caplog.text
    assert (tmp_path / "out" / "capi" / "signatures.log").read_text() == f"{note}\n"


@needs_cc
def test_an_ir_of_no_headers_is_said_not_checked(parse, tmp_path, caplog):
    model, _ = parse(SIGNED)
    model.meta.headers = []
    assert process(model, ["capi"], tmp_path / "out", include=[tmp_path]) == []

    assert "the signatures are not checked: the IR records no headers" in caplog.text


# A record with a field of every kind that the printers print, a record of
# bit-fields, signed ones too, and a packed record holding both at offsets not
# aligned for them
KINDS = (
    "#include <stdbool.h>\n"
    "#include <stddef.h>\n"
    "#include <stdint.h>\n"
    "#include <sys/types.h>\n"
    "/** E */\n"
    "enum api_e {\n"
    "\tAPI_E_NEG = -3, ///< Negative\n"
    "\tAPI_E_POS = 7,  ///< Positive\n"
    "};\n"
    "/** Callback */\n"
    "typedef int (*api_cb)(void *arg);\n"
    "/** Inner */\n"
    "struct api_in {\n"
    "\tint16_t a; ///< A\n"
    "\tuint8_t b; ///< B\n"
    "};\n"
    "/** Bits */\n"
    "struct api_bits {\n"
    "\tint s : 5;           ///< Signed\n"
    "\tunsigned int u : 11; ///< Unsigned\n"
    "\tbool f : 1;          ///< Flag\n"
    "\tenum api_e e : 4;    ///< Enum\n"
    "};\n"
    "/** V */\n"
    "union api_v {\n"
    "\tuint32_t w; ///< W\n"
    "\tuint8_t b;  ///< B\n"
    "};\n"
    "/** All */\n"
    "struct api_all {\n"
    "\tint8_t i8;            ///< I8\n"
    "\tint16_t i16;          ///< I16\n"
    "\tint32_t i32;          ///< I32\n"
    "\tint64_t i64;          ///< I64\n"
    "\tuint8_t u8;           ///< U8\n"
    "\tuint16_t u16;         ///< U16\n"
    "\tuint32_t u32;         ///< U32\n"
    "\tuint64_t u64;         ///< U64\n"
    "\tchar c;               ///< C\n"
    "\tbool t;               ///< T\n"
    "\tfloat f;              ///< F\n"
    "\tdouble d;             ///< D\n"
    "\tsize_t sz;            ///< Size\n"
    "\tssize_t ss;           ///< Signed size\n"
    "\tenum api_e e;         ///< E\n"
    "\tchar name[6];         ///< Name\n"
    "\tconst char *str;      ///< Str\n"
    "\tconst char *none;     ///< None\n"
    "\tvoid *ptr;            ///< Ptr\n"
    "\tapi_cb cb;            ///< Cb\n"
    "\tint16_t m[2][3];      ///< Matrix\n"
    "\tstruct api_in ins[2]; ///< Records\n"
    "\tstruct api_in in;     ///< Record\n"
    "\tstruct api_bits bits; ///< Bits\n"
    "\tunion api_v v;        ///< Union\n"
    "};\n"
    "/** Packed */\n"
    "struct __attribute__((packed)) api_pk {\n"
    "\tuint8_t t;            ///< T\n"
    "\tstruct api_in in;     ///< In\n"
    "\tstruct api_bits bits; ///< Bits\n"
    "\tint64_t n;            ///< N\n"
    "};\n"
    "int api_use(struct api_all *a, struct api_pk *p, struct api_bits *b);\n"
)

KINDS_C = (
    "#include <string.h>\n"
    '#include "libapi.h"\n'
    "int main(int argc, char **argv) {\n"
    "\tstruct api_all a;\n"
    "\tstruct api_pk p;\n"
    '\tint flags = argc > 1 && !strcmp(argv[1], "json") ? API_PR_JSON : API_PR_YAML;\n'
    "\n"
    "\tmemset(&a, 0, sizeof(a));\n"
    "\ta.i8 = -8; a.i16 = -1600; a.i32 = -320000; a.i64 = -6400000000LL;\n"
    "\ta.u8 = 250; a.u16 = 65000; a.u32 = 4000000000u;\n"
    "\ta.u64 = 18000000000000000000ULL;\n"
    "\ta.c = 'x'; a.t = true; a.f = 1.5f; a.d = -2.25; a.sz = 123456789; a.ss = -42;\n"
    "\ta.e = API_E_NEG;\n"
    '\tmemcpy(a.name, "ab\\"c\\\\d", 6);\n'
    '\ta.str = "s\\tr"; a.none = NULL; a.ptr = (void *)0x1234; a.cb = NULL;\n'
    "\tfor (int i = 0; i < 2; ++i)\n"
    "\t\tfor (int j = 0; j < 3; ++j)\n"
    "\t\t\ta.m[i][j] = (int16_t)(-10 * i - j);\n"
    "\ta.ins[0].a = -1; a.ins[0].b = 2; a.ins[1].a = 3; a.ins[1].b = 254;\n"
    "\ta.in.a = -32768; a.in.b = 9;\n"
    "\ta.bits.s = -11; a.bits.u = 2047; a.bits.f = true; a.bits.e = API_E_NEG;\n"
    "\ta.v.w = 0x01020304;\n"
    "\n"
    "\tmemset(&p, 0, sizeof(p));\n"
    "\tp.t = 7; p.in.a = -5; p.in.b = 200;\n"
    "\tp.bits.s = 15; p.bits.u = 1; p.bits.f = false;\n"
    "\tp.bits.e = API_E_POS; p.n = -9;\n"
    "\n"
    "\treturn api_all_pr(&a, flags) < 0 || api_pk_pr(&p, flags) < 0\n"
    "\t       || api_bits_pr(NULL, flags) < 0;\n"
    "}\n"
)


@needs_cc
def test_the_printers_print_the_value_of_every_kind_of_field(parse, tmp_path):
    model, _ = parse(KINDS)
    assert process(model, ["capi"], tmp_path) == []

    program = tmp_path / "kinds.c"
    program.write_text(KINDS_C)
    cmd = ["cc", *CFLAGS, "-I", str(tmp_path / "capi"), str(program)]
    cmd += [str(tmp_path / "capi" / "api_pp.c"), "-o", str(tmp_path / "kinds")]
    subprocess.run(cmd, check=True)

    def run(fmt):
        proc = subprocess.run(
            [str(tmp_path / "kinds"), fmt], capture_output=True, text=True
        )
        assert proc.returncode == 0
        return proc.stdout

    assert run("yaml") == (
        "api_all:\n"
        "  i8: -8\n"
        "  i16: -1600\n"
        "  i32: -320000\n"
        "  i64: -6400000000\n"
        "  u8: 250\n"
        "  u16: 65000\n"
        "  u32: 4000000000\n"
        "  u64: 18000000000000000000\n"
        "  c: 120\n"
        "  t: true\n"
        "  f: 1.5\n"
        "  d: -2.25\n"
        "  sz: 123456789\n"
        "  ss: -42\n"
        "  e: -3\n"
        '  name: "ab\\"c\\\\d"\n'
        '  str: "s\\u0009r"\n'
        "  none: null\n"
        '  ptr: "0x1234"\n'
        "  cb: null\n"
        "  m: [[0, -1, -2], [-10, -11, -12]]\n"
        '  ins: [{"a": -1, "b": 2}, {"a": 3, "b": 254}]\n'
        "  in:\n"
        "    a: -32768\n"
        "    b: 9\n"
        "  bits:\n"
        "    s: -11\n"
        "    u: 2047\n"
        "    f: true\n"
        "    e: -3\n"
        "  v:\n"
        "    w: 16909060\n"
        "    b: 4\n"
        "api_pk:\n"
        "  t: 7\n"
        "  in:\n"
        "    a: -5\n"
        "    b: 200\n"
        "  bits:\n"
        "    s: 15\n"
        "    u: 1\n"
        "    f: false\n"
        "    e: 7\n"
        "  n: -9\n"
        "api_bits: ~\n"
    )
    assert [json.loads(line) for line in run("json").splitlines()] == [
        {
            "i8": -8,
            "i16": -1600,
            "i32": -320000,
            "i64": -6400000000,
            "u8": 250,
            "u16": 65000,
            "u32": 4000000000,
            "u64": 18000000000000000000,
            "c": 120,
            "t": True,
            "f": 1.5,
            "d": -2.25,
            "sz": 123456789,
            "ss": -42,
            "e": -3,
            "name": 'ab"c\\d',
            "str": "s\tr",
            "none": None,
            "ptr": "0x1234",
            "cb": None,
            "m": [[0, -1, -2], [-10, -11, -12]],
            "ins": [{"a": -1, "b": 2}, {"a": 3, "b": 254}],
            "in": {"a": -32768, "b": 9},
            "bits": {"s": -11, "u": 2047, "f": True, "e": -3},
            "v": {"w": 16909060, "b": 4},
        },
        {
            "t": 7,
            "in": {"a": -5, "b": 200},
            "bits": {"s": 15, "u": 1, "f": False, "e": 7},
            "n": -9,
        },
        None,
    ]
