import json
import subprocess

import yaml

from tests.conftest import ESCAPED, ESCAPED_VALUE, HEADERS, SKIPPED, needs_cc
from yace.compiler import process
from yace.ir import decls
from yace.ir.model import load
from yace.targets.capi.target import CAPI


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
    _, diagnostics = parser.parse(tmp_path / "capi" / "libvalid.h")
    assert [d.message for d in diagnostics if d.rule != "external-type"] == []
