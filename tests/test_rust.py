import json
import os
import subprocess

import pytest
import yaml

from tests.conftest import (
    ESCAPED,
    ESCAPED_VALUE,
    HEADERS,
    SKIPPED,
    needs_cargo,
    needs_cc,
)
from yace.compiler import process
from yace.targets.rust.target import Rust

pytestmark = needs_cargo


def json_lines(text):
    return [json.loads(line) for line in text.splitlines()]


def run_with_crate(tmp_path, main: str, env=None) -> str:
    """Build and run 'main' against the crate generated into 'tmp_path'"""

    project = tmp_path / "user"
    (project / "src").mkdir(parents=True)
    (project / "Cargo.toml").write_text(
        '[package]\nname = "user"\nversion = "0.0.0"\nedition = "2021"\n\n'
        f"[dependencies]\napi = {{ path = {json.dumps(str(tmp_path / 'rust'))} }}\n"
    )
    (project / "src" / "main.rs").write_text(main)
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--offline"],
        cwd=project,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@needs_cc
def test_the_subset_prints_as_the_c_api_does(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["capi", "rust"], tmp_path) == []

    for fmt, load in (("yaml", yaml.safe_load_all), ("json", json_lines)):
        c_out = (tmp_path / "capi" / f"check.{fmt}").read_text()
        rust_out = (tmp_path / "rust" / f"check.{fmt}").read_text()
        assert list(load(rust_out)) == list(load(c_out))


@needs_cc
def test_floats_print_as_printf_g_does(parse, tmp_path):
    values = [0.1, -2.5e-5, 1e-4, 123456.0, 1234567.0, 1e300, -0.0, 0.5, 99999.95]
    model, _ = parse("/** Values */\nstruct api_f { double d; float f; };\n")
    assert process(model, ["rust"], tmp_path) == []

    lines = "".join(
        f'    println!("{{}}", ApiF {{ d: {v!r}, f: {v!r}_f64 as f32 }}'
        ".to_string().replace('\\n', \" \"));\n"
        for v in values
    )
    rust = run_with_crate(
        tmp_path, f"use api::*;\nfn main() {{\n{lines}}}\n", {"API_NO_LINK": "1"}
    )

    program = tmp_path / "g.c"
    program.write_text(
        "#include <stdio.h>\nint main(void) {\n"
        + "".join(
            f'\tprintf("api_f:   d: %g   f: %g \\n", {v!r}, (double){v!r}f);\n'
            for v in values
        )
        + "\treturn 0;\n}\n"
    )
    subprocess.run(["cc", str(program), "-o", str(tmp_path / "g")], check=True)
    c = subprocess.run([str(tmp_path / "g")], capture_output=True, text=True).stdout

    assert rust.split("\n") == c.split("\n")


@pytest.mark.parametrize(
    "header",
    [
        (
            "/** P */\nstruct api_p {\n\tint x; ///< X\n};\n"
            "/** A */\nstruct api_a {\n\tconst char *names[2]; ///< N\n"
            "\tdouble v[2][2]; ///< V\n\tstruct api_p ps[2]; ///< P\n};\n"
        ),
        "/** F */\nint api_f(int x);\n",
    ],
    ids=["records", "no-records"],
)
def test_the_crate_builds_without_warnings(parse, tmp_path, header):
    model, _ = parse(header)
    assert process(model, ["rust"], tmp_path) == []

    assert "warning" not in (tmp_path / "rust" / "cargo.log").read_text()


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
        "struct uses { FILE *stream; point at; struct outer o; };\n"
        "int f(const point *p, int values[4]);\n"
        "int g(int, char *);\n"
        "int log_it(const char *fmt, ...);\n"
        "enum e { A, B };\n"
        "enum e h(struct s by_value);\n"
    )
    assert diagnostics
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub struct FILE {" in lib
    assert "pub fn log_it(fmt: *const c_char, ...) -> c_int;" in lib
    assert "pub _bits: [u8; 16]," in lib


def test_names_are_made_usable(parse, tmp_path):
    model, _ = parse(
        "struct foo_bar { int type; int self; };\n"
        "struct foo__bar { int x; };\n"
        "int match(int fn);\n"
        "enum kind { Self = 1 };\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub struct foo_bar {" in lib
    assert "pub r#type: c_int," in lib
    assert "pub self_: c_int," in lib
    assert "pub fn r#match(r#fn: c_int) -> c_int;" in lib


def test_a_typedef_of_its_own_record_or_enum_is_that_type(parse, tmp_path):
    model, _ = parse(
        "struct api_buf { int len; };\ntypedef struct api_buf api_buf;\n"
        "enum api_kind { API_KIND_A = 1 };\ntypedef enum api_kind api_kind;\n"
        "int api_buf_len(const api_buf *b, api_kind k);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub struct ApiBuf {" in lib and "pub type ApiBuf" not in lib
    assert "b: *const ApiBuf, k: ApiKind" in lib


def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["rust"], tmp_path)
    assert failures and "size_of::<ValidPoint>() == 12" in failures[0]


def test_emitting_is_deterministic(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    first = [p.read_bytes() for p in Rust(tmp_path / "a").emit(model)]
    second = [p.read_bytes() for p in Rust(tmp_path / "b").emit(model)]
    assert first == second


def test_no_toolchain_is_a_failure_not_a_crash(parser, tmp_path, monkeypatch):
    monkeypatch.setenv("CARGO", "no-such-cargo")
    model, _ = parser.parse(HEADERS / "valid.h")

    assert process(model, ["rust"], tmp_path) == [
        "rust: no Rust toolchain" " ('no-such-cargo'); set CARGO"
    ]


def test_enums_are_integers_with_names(parse, tmp_path):
    model, _ = parse("/** Kinds */\nenum api_kind { API_A = 1, API_B = 2 };\n")
    assert process(model, ["rust"], tmp_path) == []

    out = run_with_crate(
        tmp_path,
        "use api::*;\nfn main() {\n"
        '    println!("{:?} {:?} {}", ApiKind(2).name(), ApiKind(7).name(),'
        " API_A.0);\n}\n",
        {"API_NO_LINK": "1"},
    )
    assert out == 'Some("API_B") None 1\n'


def test_string_defines_keep_their_value(parse, tmp_path):
    model, _ = parse(ESCAPED)
    assert process(model, ["rust"], tmp_path) == []

    main = 'fn main() { print!("{}", api::API_S.to_str().unwrap()); }\n'
    assert run_with_crate(tmp_path, main, {"API_NO_LINK": "1"}) == ESCAPED_VALUE


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["rust"], tmp_path) == []
