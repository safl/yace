import json
import subprocess
import sys

import yaml

from tests.conftest import ESCAPED, ESCAPED_VALUE, HEADERS, SKIPPED, needs_cc
from yace.compiler import process
from yace.targets.python.target import Python


def module(tmp_path, name="api"):
    """Run the source of the generated module 'name'; returns its namespace"""

    namespace: dict = {}
    path = tmp_path / "python" / f"{name}.py"
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    return namespace


def json_lines(text):
    return [json.loads(line) for line in text.splitlines()]


def test_the_subset_binds_and_prints(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["python"], tmp_path) == []

    documents = list(
        yaml.safe_load_all((tmp_path / "python" / "check.yaml").read_text())
    )
    by_name = {next(iter(doc)): doc[next(iter(doc))] for doc in documents}
    assert by_name["valid_all"]["grid"] == [[0, 0, 0], [0, 0, 0]]
    assert by_name["valid_all"]["at"] == {"x": 0, "y": 0}
    assert by_name["valid_all"]["label"] is None
    assert by_name["valid_all"]["name"] == ""
    assert by_name["valid_either"]["point"] == {"x": 0, "y": 0}

    lines = (tmp_path / "python" / "check.json").read_text().splitlines()
    assert json.loads(lines[-1]) == {"number": 0, "point": {"x": 0, "y": 0}}


@needs_cc
def test_the_subset_prints_as_the_c_api_does(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["capi", "python"], tmp_path) == []

    for fmt, load in (("yaml", yaml.safe_load_all), ("json", json_lines)):
        c_out = (tmp_path / "capi" / f"check.{fmt}").read_text()
        py_out = (tmp_path / "python" / f"check.{fmt}").read_text()
        assert list(load(py_out)) == list(load(c_out))


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
    assert process(model, ["python"], tmp_path) == []

    ns = module(tmp_path)
    assert "FILE" in ns  # FILE, declared outside the header, is a stub
    assert "log_it" not in ns  # variadic, so not bound
    assert ns["Outer"]._fields_[1] == ("bits", ns["ctypes"].c_uint, 3)
    assert ns["Flex"]().to_dict() == {"n": 0, "data": None}


def test_names_are_made_usable(parse, tmp_path):
    model, _ = parse(
        "struct foo_bar { int class; };\n"
        "struct foo__bar { int x; };\n"
        '/** Ends in a quote, "so" */\nint pass(int lambda);\n'
        "enum kind { None = 1 };\n"
        "int json(int sys);\n"
        "int sys(int os);\n"
    )
    assert process(model, ["python"], tmp_path) == []

    ns = module(tmp_path)
    assert ns["foo_bar"]().to_dict() == {"class": 0}
    assert ns["foo__bar"]().to_dict() == {"x": 0}
    assert ns["pass_"].__doc__ == 'Ends in a quote, "so"'
    assert ns["Kind"].None_ == 1
    assert str(ns["foo__bar"]()) == "foo__bar:\n  x: 0\n"


def test_a_header_named_as_a_module_of_the_standard_library(parse, tmp_path):
    """json, never built into an interpreter, which zlib may or may not be"""

    model, _ = parse("/** J */\nstruct json_s { int a; };\n", "json.h")
    assert process(model, ["python"], tmp_path) == []
    assert (tmp_path / "python" / "json_.py").exists()


def test_typedefs_of_their_own_names_and_fields_named_as_printers(parse, tmp_path):
    model, _ = parse(
        "struct api_buf { int len; };\ntypedef struct api_buf api_buf;\n"
        "enum api_kind { API_KIND_A = 1 };\ntypedef enum api_kind api_kind;\n"
        "struct api_rec { int pr, fpr, to_dict; };\n"
        "int api_len(const api_buf *b, api_kind k);\n"
    )
    assert process(model, ["python"], tmp_path) == []  # its check prints them

    api = module(tmp_path)
    assert api["ApiBuf"]._yace_name == "api_buf" and "api_buf" not in api
    assert str(api["ApiRec"](1, 2, 3)) == "api_rec:\n  pr: 1\n  fpr: 2\n  to_dict: 3\n"


def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["python"], tmp_path)
    assert failures and "sizeof(ValidPoint)" in failures[0]


def test_emitting_is_deterministic(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    first = [p.read_bytes() for p in Python(tmp_path / "a").emit(model)]
    second = [p.read_bytes() for p in Python(tmp_path / "b").emit(model)]
    assert first == second


def test_calling_without_the_library_says_how_to_find_it(parse, tmp_path):
    model, _ = parse("/** Sum */\nint api_sum(int a, int b);\n")
    assert process(model, ["python"], tmp_path) == []

    proc = subprocess.run(
        [sys.executable, "-c", "import api; api.api_sum(1, 2)"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(tmp_path / "python"), "API_LIBRARY": ""},
    )
    assert "set API_LIBRARY" in proc.stderr


def test_string_defines_keep_their_value(parse, tmp_path):
    model, _ = parse(ESCAPED)
    assert process(model, ["python"], tmp_path) == []

    assert module(tmp_path)["API_S"] == ESCAPED_VALUE


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["python"], tmp_path) == []
