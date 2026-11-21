# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import errno
import json
import os
import subprocess

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
    flat,
    needs_cargo,
    needs_cc,
)
from yace.compiler import process

pytestmark = needs_cargo


def json_lines(text):
    return [json.loads(line) for line in text.splitlines()]


def run_with_crate(tmp_path, main: str, env=None, user="user", fails=False) -> str:
    """Build and run 'main' as the package 'user' against the crate generated
    into 'tmp_path', and return its standard output. With 'fails', assert that
    the build or the run fails, and return the standard error instead."""

    project = tmp_path / user
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
    if fails:
        assert proc.returncode != 0, proc.stdout
        return proc.stderr
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


def test_the_meta_names_the_crate_and_another_crate_includes_the_bindings(
    parser, tmp_path
):
    """xNVMe names its crate 'xnvme-sys' in the meta, and a crate that generates
    the bindings in its build script includes bindings.rs with include!()."""

    header = tmp_path / "api.h"
    header.write_text(EDGES)
    model, _ = parser.parse(header, {"prefix": "api", "crate": "api-sys"})
    assert process(model, ["rust"], tmp_path) == []
    assert 'name = "api-sys"' in (tmp_path / "rust" / "Cargo.toml").read_text()

    project = tmp_path / "own"
    (project / "src").mkdir(parents=True)
    (project / "Cargo.toml").write_text(
        '[package]\nname = "own"\nversion = "0.0.0"\nedition = "2021"\n'
    )
    bindings = json.dumps(str(tmp_path / "rust" / "bindings.rs"))
    (project / "src" / "lib.rs").write_text(
        "#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]\n"
        "#![allow(clippy::all)]\n"
        f"include!({bindings});\n"
    )
    proc = subprocess.run(
        ["cargo", "build", "--quiet", "--offline"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "warning" not in proc.stderr


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

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub struct FILE {" in lib
    assert "pub fn log_it(fmt: *const c_char, ...) -> c_int;" in lib
    assert "pub _bits: [u32; 4]," in lib


def test_names_are_made_usable(parse, tmp_path):
    model, _ = parse(
        "struct foo_bar { int type; int self; };\n"
        "struct foo__bar { int x; };\n"
        "int match(int fn);\n"
        "enum kind { Self = 1 };\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub struct foo_bar {" in lib
    assert "pub r#type: c_int," in lib
    assert "pub self_: c_int," in lib
    assert "pub fn r#match(r#fn: c_int) -> c_int;" in lib


def test_debug_names_the_c_fields_and_reads_no_union(parse, tmp_path):
    model, _ = parse(
        "#include <stdint.h>\n"
        "enum api_e { API_E_A = -1 };\n"
        "struct api_p { int32_t x; int32_t y; };\n"
        "struct api_v { enum api_e e; uint8_t grid[2][2]; struct api_p at;\n"
        "\tconst char *label; int type; int self; };\n"
        "union api_u { uint32_t u; struct api_p p; };\n"
        "struct api_flags { unsigned int a : 4; unsigned int : 4; };\n"
        "struct api_k { int type; };\n"
    )
    assert process(model, ["rust"], tmp_path) == []
    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "#[derive(Clone, Copy, Debug)]\npub struct ApiP {" in lib

    out = run_with_crate(
        tmp_path,
        "use api::*;\nfn main() {\n"
        "    let mut v = ApiV::default();\n"
        "    v.e = API_E_A;\n    v.grid[1][0] = 5;\n    v.at.y = -2;\n"
        "    v.r#type = 3;\n    v.self_ = 4;\n"
        '    println!("{:?}", v);\n'
        '    println!("{:?}", ApiU { u: 1 });\n'
        '    println!("{:?}", ApiFlags::default());\n'
        '    println!("{:?}", ApiK { r#type: 1 });\n'
        "}\n",
        {"API_NO_LINK": "1"},
    )
    assert out.splitlines() == [
        "ApiV { e: ApiE(-1), grid: [[0, 0], [5, 0]], at: ApiP { x: 0, y: -2 },"
        " label: 0x0, type: 3, self: 4 }",
        "ApiU { .. }",
        "ApiFlags { .. }",
        "ApiK { type: 1 }",
    ]


def test_a_union_whose_members_span_it_reads_without_unsafe(parse, tmp_path):
    """Every member of api_word is 4 bytes without padding, so each is read by a
    safe method; the program forbids unsafe code and so builds only if it is"""

    model, _ = parse(
        "#include <stdint.h>\n"
        "struct api_rgb { uint8_t r; uint8_t g; uint8_t b; uint8_t a; };\n"
        "union api_word { uint32_t u; float f; struct api_rgb rgb;"
        " uint8_t bytes[4]; };\n"
    )
    assert process(model, ["rust"], tmp_path) == []
    lib = flat((tmp_path / "rust" / "bindings.rs").read_text())
    assert (
        flat(
            "const _: () = assert!(std::mem::size_of::<u32>()"
            " == std::mem::size_of::<ApiWord>());"
        )
        in lib
    )

    out = run_with_crate(
        tmp_path,
        "#![forbid(unsafe_code)]\nuse api::*;\nfn main() {\n"
        "    let w = ApiWord { bytes: [7, 7, 7, 7] };\n"
        "    let (u, f) = (w.u(), w.f().to_bits());\n"
        '    println!("{u:#x} {f:#x} {:?} {}", w.bytes(), w.rgb().a);\n'
        "}\n",
        {"API_NO_LINK": "1"},
    )
    assert out.splitlines() == ["0x7070707 0x7070707 [7, 7, 7, 7] 7"]


def test_a_union_reads_with_unsafe_where_a_member_is_short_padded_or_not_any_bits(
    parse, tmp_path
):
    """A member shorter than the union, or with padding, leaves bytes that may
    be uninitialised, so no member reads safely; a bool or a function pointer
    is not a value for every bit pattern, so that member alone needs unsafe"""

    model, _ = parse(
        "#include <stdbool.h>\n#include <stdint.h>\n"
        "struct api_pad { uint8_t a; uint32_t b; };\n"
        "union api_short { uint8_t b; uint32_t u; };\n"
        "union api_padded { struct api_pad p; uint64_t v; };\n"
        "typedef int (*api_cb)(void *arg);\n"
        "union api_fn { api_cb cb; uintptr_t v; };\n"
        "union api_flag { bool b; uint8_t v; };\n"
    )
    assert process(model, ["rust"], tmp_path) == []
    lib = flat((tmp_path / "rust" / "bindings.rs").read_text())
    assert "pub fn u(&self)" not in lib
    assert "pub fn p(&self)" not in lib
    assert "pub fn cb(&self)" not in lib
    assert "pub fn b(&self)" not in lib
    assert flat("pub fn v(&self) -> usize {") in lib
    assert flat("pub fn v(&self) -> u8 {") in lib
    assert "pub fn v(&self) -> u64" not in lib


def test_a_typedef_of_its_own_record_or_enum_is_that_type(parse, tmp_path):
    model, _ = parse(
        "struct api_buf { int len; };\ntypedef struct api_buf api_buf;\n"
        "enum api_kind { API_KIND_A = 1 };\ntypedef enum api_kind api_kind;\n"
        "int api_buf_len(const api_buf *b, api_kind k);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub struct ApiBuf {" in lib and "pub type ApiBuf" not in lib
    assert "b: *const ApiBuf, k: ApiKind" in lib


def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["rust"], tmp_path)
    assert failures and "size_of::<ValidPoint>() == 12" in failures[0]


def test_no_toolchain_is_a_failure_not_a_crash(parser, tmp_path, monkeypatch):
    monkeypatch.setenv("CARGO", "no-such-cargo")
    model, _ = parser.parse(HEADERS / "valid.h")

    assert process(model, ["rust"], tmp_path) == [
        "rust: no Rust toolchain ('no-such-cargo'); set CARGO"
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


def doc(*lines):
    return "/**\n" + "".join(f" * {line}\n" for line in lines) + " */\n"


def misindented_docs(source: str) -> list:
    """Return the doc comment lines whose indentation differs from that of the
    line they document."""

    lines = source.splitlines()
    found = []
    for idx, line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("///") and idx:
            indent = line[: len(line) - len(line.lstrip())]
            above = idx - 1
            while above >= 0 and lines[above].lstrip().startswith("///"):
                if not lines[above].startswith(indent + "///"):
                    found.append(lines[above])
                above -= 1
    return found


EDGES = (
    "#include <stddef.h>\n#include <stdint.h>\n"
    "struct api_h;\nstruct api_p { int *at; };\n"
    "typedef int (*api_cb)(void *arg, const struct api_p *p, int n);\n"
    + doc("Open", "@param[out] h H", "@nullable name", "@errno")
    + "int api_open(const char *name, struct api_h **h);\n"
    + doc("Close", "@destroys h", "@errno")
    + "int api_close(struct api_h *h);\n"
    + doc("Each", "@nullable cb", "@lifetime cb call", "@errno")
    + "int64_t api_each(struct api_h *h, api_cb cb, void *arg);\n"
    + doc("Submit", "@nullable cb", "@lifetime cb once", "@errno")
    + "int api_submit(struct api_h *h, api_cb cb, void *arg);\n"
    + doc("On", "@lifetime cb handle", "@errno")
    + "int api_on(const struct api_h *h, api_cb cb, void *arg);\n"
    + doc("Inline", "@errno")
    + "int api_inline(struct api_h *h, int (*fn)(void *ctx), void *ctx);\n"
    + doc("Step", "@param[in,out] pos P", "@param[out] got G", "@errno")
    + "int api_step(struct api_h *h, size_t *pos, int *got);\n"
    + doc("Raw")
    + "int api_raw(struct api_h *h, struct api_p *p, void *opaque);\n"
    + doc("Other", "@nullable return")
    + "struct api_h *api_other(struct api_h *h);\n"
    + doc("Base")
    + "const char *api_base(const char *path);\n"
    + doc("Pick")
    + "const char *api_pick(const char *a, const char *b);\n"
    + doc("Version")
    + "const char *api_version(void);\n"
)


HANDLE_NAMED_AS_PREFIX = (
    "#include <stddef.h>\nstruct api;\n"
    + doc("Open", "@param[out] h H", "@errno")
    + "int api_open(struct api **h);\n"
    + doc("Close", "@destroys h")
    + "void api_close(struct api *h);\n"
    + doc("Pointers", "@arrparam[out] ptrs P @len_at{n}", "@errno")
    + "int api_ptrs(struct api *h, int **ptrs, size_t n);\n"
)


def test_a_handle_named_as_the_prefix_is_api_handle_and_out_pointers_are_slices(
    parse, tmp_path
):
    model, _ = parse(HANDLE_NAMED_AS_PREFIX)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub struct ApiHandle {" in lib
    assert flat(
        "pub fn ptrs<'buf>(&mut self, ptrs: &'buf mut [*mut c_int])"
        " -> io::Result<&'buf mut [*mut c_int]>"
    ) in flat(lib)


MORE = (
    "#include <stddef.h>\nstruct api_h;\n"
    + doc("Open", "@param[out] h H", "@errno")
    + "int api_open(struct api_h **h);\n"
    + doc("Close", "@destroys h")
    + "void api_close(struct api_h *h);\n"
    + doc("Copy", "@param dst D", "@param src S", "@errno")
    + "int api_copy(struct api_h *dst, const struct api_h *src);\n"
    + doc("Make", "@param[out] h H")
    + "void api_make(struct api_h **h);\n"
    + doc("Dot", "@arrparam a A @len_at{n}", "@arrparam b B @len_at{n}")
    + "long api_dot(const int *a, const int *b, size_t n);\n"
    + doc(
        "Map",
        "@arrparam in I @len_at{n}",
        "@arrparam[out] out O @len_at{n}",
        "@errno",
    )
    + "int api_map(const int *in, int *out, size_t n);\n"
    + doc("Label", "@param[out] label L", "@errno")
    + "int api_label(const struct api_h *h, const char **label);\n"
    + doc("Raw")
    + "void *api_raw(void);\n"
)

MORE_C = """
static int made;
int api_open(struct api_h **h)
{
\t*h = (struct api_h *)&made;
\treturn 0;
}
void api_close(struct api_h *h) { (void)h; }
int api_copy(struct api_h *dst, const struct api_h *src)
{
\treturn dst == src ? 0 : -22;
}
void api_make(struct api_h **h) { *h = (struct api_h *)&made; }
long api_dot(const int *a, const int *b, size_t n)
{
\tlong s = 0;
\tfor (size_t i = 0; i < n; i++) s += (long)a[i] * b[i];
\treturn s;
}
int api_map(const int *in, int *out, size_t n)
{
\tfor (size_t i = 0; i < n; i++) out[i] = 2 * in[i];
\treturn 0;
}
int api_label(const struct api_h *h, const char **label)
{
\t(void)h;
\t*label = "lbl";
\treturn 0;
}
void *api_raw(void) { return (void *)16; }
"""


def test_handles_pass_by_reference_make_returns_an_option_and_shared_counts_must_match(
    parse, tmp_path
):
    model, _ = parse(MORE)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn copy(&mut self, src: &H) -> io::Result<()>" in lib
    assert "pub fn make() -> Option<H>" in lib
    assert "assert_eq!(b.len(), a.len()," in lib
    assert "assert_eq!(r#in.len(), out.len()," in lib


IO = (
    "#include <stddef.h>\n#include <stdint.h>\nstruct api_h;\nstruct api_x;\n"
    + doc("Open", "@param[out] h H", "@errno")
    + "int api_open(struct api_h **h);\n"
    + doc("Close", "@destroys h", "@errno")
    + "int api_close(struct api_h *h);\n"
    + doc("Clone", "@param[out] copy C", "@errno")
    + "int api_clone(const struct api_h *h, struct api_h **copy);\n"
    + doc("Write", "@arrparam buf B @len_at{n}")
    + "size_t api_write(const void *buf, size_t n);\n"
    + doc("Read", "@arrparam[out] buf B @len_at{n}", "@errno")
    + "int64_t api_read(void *buf, size_t n);\n"
    + doc(
        "Pair",
        "@arrparam[out] a A @len_at{n}",
        "@arrparam[out] b B @len_at{n}",
    )
    + "void api_pair(int32_t *a, int32_t *b, size_t n);\n"
    + doc("Twice", "@arrparam[in,out] v V @len_at{n}")
    + "void api_twice(int32_t *v, size_t n);\n"
    + doc("Default")
    + "struct api_x *api_default(void);\n"
    + doc("Use")
    + "int api_use(int x, struct api_x *p);\n"
)

IO_C = """
#include <string.h>
static int handles[2];
int api_open(struct api_h **h) { *h = (struct api_h *)&handles[0]; return 0; }
int api_close(struct api_h *h) { return h == (struct api_h *)&handles[1] ? -5 : 0; }
int api_clone(const struct api_h *h, struct api_h **copy)
{
\t(void)h;
\t*copy = (struct api_h *)&handles[1];
\treturn 0;
}
size_t api_write(const void *buf, size_t n) { (void)buf; return n; }
int64_t api_read(void *buf, size_t n)
{
\tsize_t len = n < 3 ? n : 3;
\tmemcpy(buf, "xyz", len);
\treturn (int64_t)len;
}
void api_pair(int32_t *a, int32_t *b, size_t n)
{
\tfor (size_t i = 0; i < n; i++) { a[i] = (int32_t)i; b[i] = (int32_t)(10 * i); }
}
void api_twice(int32_t *v, size_t n) { for (size_t i = 0; i < n; i++) v[i] *= 2; }
struct api_x *api_default(void) { return (struct api_x *)&handles[0]; }
int api_use(int x, struct api_x *p) { return p ? x : -1; }
"""


# api_reap writes at most three elements and returns -fail, so it succeeds only
# when 'fail' is 0
REAP = (
    "#include <stdint.h>\n"
    + doc(
        "Reap",
        "@arrparam[out] done D @len_at{max} @nwritten_at{n}",
        "@param[out] n N",
        "@errno partial",
    )
    + "int api_reap(int fail, int32_t *done, uint32_t max, uint32_t *n);\n"
)

REAP_C = """
int api_reap(int fail, int32_t *done, uint32_t max, uint32_t *n)
{
\tuint32_t i;
\tfor (i = 0; i < max && i < 3; i++)
\t\tdone[i] = (int32_t)(10 * i);
\t*n = i;
\treturn -fail;
}
"""


# Takes its arguments as a record, and fails with EINVAL unless given its size
SIZED = (
    "#include <stddef.h>\n#include <stdint.h>\n"
    + doc("Arguments")
    + "struct api_args {\n\tuint64_t slba; ///< First\n\tuint32_t nlb; ///< Count\n};\n"
    + doc("Prepare", "@param[out] cmd C", "@recparam args A", "@errno")
    + "int api_prep_sized(uint64_t *cmd, const struct api_args *args,"
    + " size_t args_nbytes);\n"
    + doc("Prepare, passing the size of args")
    + "static inline int api_prep(uint64_t *cmd, const struct api_args *args)\n"
    + "{\n\treturn api_prep_sized(cmd, args, sizeof(*args));\n}\n"
)

SIZED_C = """
int api_prep_sized(uint64_t *cmd, const struct api_args *args, size_t args_nbytes)
{
\tif (args_nbytes != sizeof(*args))
\t\treturn -22;
\t*cmd = args->slba + args->nlb;
\treturn 0;
}
"""


def library(tmp_path, source: str):
    """Build 'source' as the shared library 'libapi.so' in 'tmp_path'"""

    (tmp_path / "api.c").write_text(source)
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
        + ["-o", str(tmp_path / "libapi.so")],
        check=True,
    )
    return tmp_path / "libapi.so"


@needs_cc
def test_an_out_count_bounds_the_result_and_the_error_holds_what_was_written(
    parse, tmp_path
):
    model, _ = parse(REAP)
    assert process(model, ["rust"], tmp_path) == []
    library(tmp_path, REAP + REAP_C)

    main = (
        "use api::safe::*;\nfn main() {\n"
        "    let mut buf = [0i32; 4];\n"
        '    println!("{:?}", reap(0, &mut buf).unwrap());\n'
        f"    let failed = reap({errno.EAGAIN}, &mut buf[..2]).unwrap_err();\n"
        '    println!("{:?} {:?}", failed.error.kind(), failed.value);\n'
        f"    let error: std::io::Error = reap({errno.EAGAIN}, &mut buf)"
        ".unwrap_err().into();\n"
        '    println!("{:?}", error.raw_os_error());\n'
        "}\n"
    )
    env = {
        "API_LIB_DIR": str(tmp_path),
        "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
    }
    assert run_with_crate(tmp_path, main, env) == (
        f"[0, 10, 20]\nWouldBlock [0, 10]\nSome({errno.EAGAIN})\n"
    )


@needs_cc
def test_a_recparam_record_is_passed_with_its_size_by_the_c_name(parse, tmp_path):
    model, _ = parse(SIZED)
    assert process(model, ["rust"], tmp_path) == []
    library(tmp_path, SIZED + SIZED_C)

    main = (
        "use api::safe::*;\nfn main() {\n"
        "    let args = api::ApiArgs { slba: 40, nlb: 2 };\n"
        '    println!("{}", prep(&args).unwrap());\n'
        "}\n"
    )
    env = {
        "API_LIB_DIR": str(tmp_path),
        "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
    }
    assert run_with_crate(tmp_path, main, env) == "42\n"


def test_void_buffers_are_byte_slices_and_api_clone_returns_a_new_handle(
    parse, tmp_path
):
    model, _ = parse(IO)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn write(buf: &[u8]) -> usize" in lib
    assert "pub fn read<'buf>(buf: &'buf mut [u8]) -> io::Result<&'buf mut [u8]>" in lib
    assert "pub fn clone(&self) -> io::Result<H>" in lib


def test_the_idiomatic_layer_builds_for_every_kind_of_parameter(parse, tmp_path):
    model, _ = parse(EDGES)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn open(name: Option<&CStr>) -> io::Result<H>" in lib
    assert (
        "pub fn each(&mut self, cb: Option<&mut ApiCbFn>) -> io::Result<usize>" in lib
    )
    assert "pub fn step(&mut self, pos: &mut usize) -> io::Result<c_int>" in lib
    assert "pub unsafe fn raw(&mut self, p: &mut ApiP, opaque: *mut c_void)" in lib
    assert "pub fn close(self) -> io::Result<()>" in lib
    assert (
        "pub fn submit(&mut self, cb: Option<Box<ApiCbOnce>>) -> io::Result<()>" in lib
    )
    assert "pub fn on(&mut self, cb: Box<ApiCbFn<'static>>) -> io::Result<()>" in lib
    assert "keep: Vec<Box<dyn std::any::Any>>," in lib
    assert flat(
        'pub unsafe fn inline(&mut self, r#fn: Option<unsafe extern "C" fn(*mut c_void)'
        " -> c_int>, ctx: *mut c_void)"
    ) in flat(lib)
    assert "pub fn other(&mut self) -> *mut ApiH" in lib
    assert "pub fn base(path: &CStr) -> &CStr" in lib
    assert "pub unsafe fn pick(a: &CStr, b: &CStr) -> &'static CStr" in lib
    assert "pub fn version() -> &'static CStr" in lib
    assert misindented_docs(lib) == []


@needs_cc
def test_a_panic_in_a_closure_aborts(parse, tmp_path):
    header = (
        "typedef int (*api_cb)(void *arg, int v);\n"
        + doc("Each", "@param cb C", "@param arg A", "@lifetime cb call")
        + "int api_each(api_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["rust"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "int api_each(api_cb cb, void *arg) { return cb(arg, 1); }\n"
    )
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
        + ["-o", str(tmp_path / "libapi.so")],
        check=True,
    )

    project = tmp_path / "user"
    (project / "src").mkdir(parents=True)
    (project / "Cargo.toml").write_text(
        '[package]\nname = "user"\nversion = "0.0.0"\nedition = "2021"\n\n'
        f"[dependencies]\napi = {{ path = {json.dumps(str(tmp_path / 'rust'))} }}\n"
    )
    (project / "src" / "main.rs").write_text(
        'fn main() { api::safe::each(&mut |_v| panic!("in the closure")); }\n'
    )
    env = {**os.environ, "API_LIB_DIR": str(tmp_path)}
    env["RUSTFLAGS"] = f"-C link-arg=-Wl,-rpath,{tmp_path}"
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--offline"],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == -6, proc.stderr
    assert "in the closure" in proc.stderr


@needs_cc
def test_a_nullable_slice_passes_null(parse, tmp_path):
    header = (
        "#include <stddef.h>\n"
        + doc("Sum", "@nullable v", "@arrparam v V @len_at{n}")
        + "int api_sum(const int *v, size_t n);\n"
    )
    model, _ = parse(header)
    assert process(model, ["rust"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "int api_sum(const int *v, size_t n)\n"
        "{\n\tint s = 0;\n\tif (!v) return -1;\n"
        "\tfor (size_t i = 0; i < n; i++) s += v[i];\n\treturn s;\n}\n"
    )
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
        + ["-o", str(tmp_path / "libapi.so")],
        check=True,
    )
    main = (
        "fn main() {\n"
        "    let all = api::safe::sum(Some(&[1, 2, 3]));\n"
        '    println!("{} {}", all, api::safe::sum(None));\n'
        "}\n"
    )
    out = run_with_crate(
        tmp_path,
        main,
        {
            "API_LIB_DIR": str(tmp_path),
            "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
        },
    )
    assert out == "6 -1\n"


SHARED = (
    doc("Bar")
    + "int bar(int x);\n"
    + doc("Bar too")
    + "int api_bar(int x);\n"
    + doc("Std")
    + "int api_std(int x);\n"
)


# Parameters named as the locals that the idiomatic layers derive from the
# parameter name 'cb'
LOCALS = (
    "int cb_cb, int cb_ctx, int cb_c, int cb_key, int cb_kept, int cb_ref,"
    " int cb_tramp, int cb_t, int cb_fn_t, int cb_held, int cb_trampoline,"
    " int cb_context, int cb_fn"
)

NAMES = (
    "#include <stddef.h>\nstruct api_h;\nstruct api_g;\n"
    "typedef int (*api_cb)(void *arg, int v);\n"
    + doc("Open", "@param[out] h H", "@errno")
    + "int api_h_open(struct api_h **h);\n"
    + doc("Open", "@param[out] g G", "@errno")
    + "int api_g_open(struct api_g **g);\n"
    + doc("Me")
    + "int api_h_me(struct api_h *h, int self);\n"
    + doc("Ctx")
    + "int api_ctx(int ctypes, int v);\n"
    + doc("Out", "@param[out] ret R")
    + "void api_outret(int *ret);\n"
    + doc("In out", "@arrparam[in,out] ret R @len_at{n}")
    + "void api_ioret(int *ret, size_t n);\n"
    + doc("Names", "@lifetime a1 call")
    + "int api_names(int a0, api_cb a1, void *arg);\n"
    + doc("Call", "@nullable cb", "@lifetime cb call", "@errno")
    + f"int api_call(api_cb cb, void *arg, {LOCALS});\n"
    + doc("Once", "@lifetime cb once", "@errno")
    + f"int api_once(api_cb cb, void *arg, {LOCALS});\n"
    + doc("Keep", "@nullable cb", "@lifetime cb handle", "@errno")
    + f"int api_h_keep(struct api_h *h, api_cb cb, void *arg, {LOCALS});\n"
    + doc("Sum", "@arrparam xs X @len_at{n}")
    + "int api_sum(const int *xs, size_t n, int xs_c, int xs_cb);\n"
    + doc("Outs", "@param[out] x X", "@arrparam[out] ys Y @len_at{n}")
    + "void api_outs(int *x, int *ys, size_t n, int x_out, int ys_out);\n"
    + "typedef int (*api_x_cb)(void *arg, int v);\n"
    + doc("Two", "@lifetime api_x call other call")
    + "int api_two(api_x_cb api_x, void *arg, api_x_cb other, void *oarg);\n"
    + doc("Count", "@arrparam api A @len_at{n}")
    + "size_t api_c(const int *api, size_t n);\n"
)

NAMES_C = f"#define LOCALS {LOCALS}\n" + """
static int h, g;
int api_h_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }
int api_g_open(struct api_g **p) { *p = (struct api_g *)&g; return 0; }
int api_h_me(struct api_h *p, int self) { (void)p; return self; }
int api_ctx(int ctypes, int v) { return ctypes + v; }
void api_outret(int *ret) { *ret = 7; }
void api_ioret(int *ret, size_t n) { for (size_t i = 0; i < n; i++) ret[i] += 1; }
int api_names(int a0, api_cb a1, void *arg) { return a1(arg, a0); }
#define SUM (cb_cb + cb_ctx + cb_c + cb_key + cb_kept + cb_ref + cb_tramp + cb_t \\
             + cb_fn_t + cb_held + cb_trampoline + cb_context + cb_fn)
int api_call(api_cb cb, void *arg, LOCALS) { return cb ? cb(arg, SUM) : 0; }
int api_once(api_cb cb, void *arg, LOCALS) { return cb(arg, SUM); }
int api_h_keep(struct api_h *p, api_cb cb, void *arg, LOCALS)
{ (void)p; return cb ? cb(arg, SUM) : 0; }
int api_sum(const int *xs, size_t n, int xs_c, int xs_cb)
{ int s = xs_c + xs_cb; for (size_t i = 0; i < n; i++) s += xs[i]; return s; }
void api_outs(int *x, int *ys, size_t n, int x_out, int ys_out)
{ *x = x_out; for (size_t i = 0; i < n; i++) ys[i] = ys_out; }
int api_two(api_x_cb x, void *arg, api_x_cb other, void *oarg)
{ return x(arg, 1) + other(oarg, 2); }
size_t api_c(const int *api, size_t n) { (void)api; return n; }
"""

# Parameters named as identifiers that a generated function body uses
# unqualified, and parameters that, once renamed, would take the name of another
HIDDEN = (
    "#include <stddef.h>\n#include <stdio.h>\nstruct api_dev;\nstruct api_cb_out;\n"
    "typedef int (*api_cb)(void *arg, int v);\ntypedef unsigned api_u32;\n"
    + doc("Mode")
    + "enum api_mode { api_mode_read = 0, api_mode_write = 1 };\n"
    + doc("Set")
    + "int api_set(int api_mode_read, int ApiMode);\n"
    + doc("Locals")
    + "enum api_e { ret = 1, s, context, h, p, err, tag, field, self, a0 };\n"
    + doc("Count", "@nullable xs", "@arrparam xs X @len_at{n}")
    + "int api_count(const int *xs, size_t n);\n"
    + doc("Peer", "@nullable other")
    + "int api_dev_peer(struct api_dev *d, struct api_dev *other);\n"
    + doc("Foo")
    + "int api_foo(int x);\n"
    + doc("Foo arg")
    + "int api_foo_arg(int y);\n"
    + doc("Foos")
    + "int api_foos(int api_foo, int api_foo_arg, int api_foo_arg_);\n"
    + doc("File", "@param[out] f F")
    + "void api_file(FILE **f, int FILE);\n"
    + doc("Buffer")
    + "struct api_buf { char *chars; size_t len; };\n"
    + doc("Buffer")
    + "typedef struct api_buf api_buf;\n"
    + doc("Kind")
    + "enum api_kind { API_KIND_A = 1 };\n"
    + doc("Kind")
    + "typedef enum api_kind api_kind;\n"
    + doc("Length")
    + "size_t api_buf_len(const api_buf *b, api_kind k);\n"
    + doc("Kind, which the C++ namespace declares by its C name")
    + "enum kind { KIND_A = 1, KIND_B = 2 };\n"
    + doc("Flip", "@param[out] out O")
    + "enum kind api_flip(enum kind k, enum kind *out);\n"
    + doc("Media, its fields named as the printers of a record")
    + "struct api_media { unsigned format, json, yaml, fpr, pr, to_dict; };\n"
    + doc("Frame")
    + "struct api_frame { struct api_media media; int n; };\n"
    + doc("Size")
    + "int api_frame_size(const struct api_frame *f);\n"
    + doc("Handle, declared through a typedef of its own name")
    + "struct api_th;\ntypedef struct api_th api_th;\n"
    + doc("Open", "@param[out] t T", "@errno")
    + "int api_th_open(api_th **t);\n"
    + doc("Get")
    + "int api_th_get(const api_th *t);\n"
    + doc("Close", "@destroys t")
    + "void api_th_close(api_th *t);\n"
    + doc("Node")
    + "struct api_node { int v; };\n"
    + doc("Node, a pointer by the name of its record")
    + "typedef struct api_node *api_node;\n"
    + doc("Value")
    + "int api_node_value(api_node n, const struct api_node *m);\n"
    + doc("Message, its payload a flexible array")
    + "struct api_msg { unsigned len; unsigned char data[]; };\n"
    + doc("Message", "@nullable return")
    + "struct api_msg *api_dev_msg(struct api_dev *d);\n"
    + doc("Get")
    + "int api_dev_get(struct api_dev *d);\n"
    + doc("Get, a name told apart by a trailing underscore")
    + "int api_dev_get_(struct api_dev *d);\n"
    + doc("Take")
    + "int api_take(int x);\n"
    + doc("Take, a name told apart by a trailing underscore")
    + "int api_take_(int x);\n"
    + doc("Writer")
    + "struct writer { int fd; int count; };\n"
    + doc("Put")
    + "int api_put(struct writer *w, int c);\n"
    + doc("Buf")
    + "struct buf { int len; };\n"
    + doc("Buf")
    + "typedef struct buf buf;\n"
    + doc("Buf, as another C name the same in CamelCase")
    + "struct Buf { int len; };\n"
    + doc("O, a name the printers bind, kept as two are O in CamelCase")
    + "struct o { int len; };\n"
    + doc("O")
    + "struct O { int len; };\n"
    + doc("Size")
    + "int api_size(const buf *b, const struct Buf *c, const struct o *d);\n"
    + doc("U8")
    + "int api_u8(int _);\n"
    + doc("Add")
    + "int api_add(int api_add);\n"
    + doc("Get", "@param[out] api_got G")
    + "void api_got(int *api_got);\n"
    + doc("Open", "@param[out] out O", "@errno")
    + "int api_dev_open(int dev, int Dev, struct api_dev **out);\n"
    + doc("Make", "@param[out] out O")
    + "int api_dev_make(int dev, struct api_dev **out);\n"
    + doc("Me")
    + "int api_dev_me(struct api_dev *d, int v);\n"
    + doc("Keep", "@lifetime cb handle", "@errno")
    + "int api_dev_keep(struct api_dev *d, api_cb cb, void *arg, int keep_);\n"
    + doc("Ptr")
    + "int api_dev_ptr(struct api_dev *d, int ptr_, int ptr);\n"
    + doc("Open", "@param[out] cb O", "@errno")
    + "int api_cb_out_open(struct api_cb_out **cb);\n"
    + doc("Me")
    + "int api_cb_out_me(struct api_cb_out *h, int v);\n"
    + doc("Run", "@lifetime api_cb call")
    + "int api_run(api_cb api_cb, void *arg);\n"
    + doc("Run", "@lifetime cb call")
    + "int api_rerun(api_cb cb, void *arg, int api_cb_trampoline, int call);\n"
    + doc("Unsigned", "@param[out] v V")
    + "void api_unsigned(api_u32 *v, int api_u32);\n"
    + doc("Variants")
    + "int api_variants(int Some, int None, int Ok, int Err);\n"
    + doc("Primitives")
    + "int api_primitives(int u8, int c_int, int anyerror);\n"
    + doc("Renamed")
    + "int api_renamed(int ret, int ret_, int ret_arg, int x_, int x);\n"
)

HIDDEN_C = """
static int dev, cb_out;
int api_set(int r, int m) { return r - m; }
int api_u8(int u) { return u + 8; }
int api_count(const int *xs, size_t n) { return xs ? (int)n : -1; }
int api_dev_peer(struct api_dev *d, struct api_dev *o) { return d == o; }
int api_foo(int x) { return x; }
int api_foo_arg(int y) { return y; }
int api_foos(int a, int b, int c) { return a - b + c; }
void api_file(FILE **f, int u) { *f = u ? stdout : NULL; }
size_t api_buf_len(const api_buf *b, api_kind k) { return b->len + (size_t)k; }
int api_put(struct writer *w, int c) { return w->count + c; }
static struct { unsigned len; unsigned char data[3]; } msg = { 3, { 1, 2, 3 } };
struct api_msg *api_dev_msg(struct api_dev *d)
{ (void)d; return (struct api_msg *)&msg; }
int api_dev_get(struct api_dev *d) { (void)d; return 1; }
int api_dev_get_(struct api_dev *d) { (void)d; return 2; }
int api_take(int x) { return x; }
int api_take_(int x) { return x + 1; }
int api_node_value(api_node n, const struct api_node *m) { return n->v - m->v; }
int api_frame_size(const struct api_frame *f) { return f->n + (int)f->media.format; }
static int th = 7;
int api_th_open(api_th **t) { *t = (api_th *)&th; return 0; }
int api_th_get(const api_th *t) { return *(const int *)t; }
void api_th_close(api_th *t) { (void)t; }
enum kind api_flip(enum kind k, enum kind *out) { *out = k; return 3 - k; }
int api_size(const buf *b, const struct Buf *c, const struct o *d)
{ return b->len + c->len + d->len; }
int api_add(int api_add) { return api_add + 1; }
void api_got(int *api_got) { *api_got = 2; }
int api_dev_open(int d, int D, struct api_dev **out)
{ *out = (struct api_dev *)&dev; return d + D; }
int api_dev_make(int d, struct api_dev **out)
{ *out = (struct api_dev *)&dev; return d; }
int api_dev_me(struct api_dev *d, int v) { (void)d; return v; }
int api_dev_keep(struct api_dev *d, api_cb cb, void *arg, int keep_)
{ (void)d; return cb(arg, keep_) < 0 ? -1 : 0; }
int api_dev_ptr(struct api_dev *d, int ptr_, int ptr) { (void)d; return ptr_ - ptr; }
int api_cb_out_open(struct api_cb_out **cb)
{ *cb = (struct api_cb_out *)&cb_out; return 0; }
int api_cb_out_me(struct api_cb_out *h, int v) { (void)h; return v; }
int api_run(api_cb cb, void *arg) { return cb(arg, 3); }
int api_rerun(api_cb cb, void *arg, int t, int call) { return cb(arg, t - call); }
void api_unsigned(api_u32 *v, int u) { *v = (api_u32)u; }
int api_variants(int s, int n, int o, int e) { return s - n + o - e; }
int api_primitives(int a, int b, int c) { return a - b + c; }
int api_renamed(int a, int b, int c, int d, int e) { return a - b + c - d + e; }
"""


def test_the_crate_builds_with_parameters_named_as_what_the_body_uses(parse, tmp_path):
    model, _ = parse(HIDDEN)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    # api_msg ends in a flexible array, so msg() returns the pointer, not a copy
    assert "pub fn msg(&mut self) -> *mut ApiMsg {" in lib


def test_the_crate_builds_with_parameters_named_as_locals_of_the_layer(parse, tmp_path):
    model, _ = parse(NAMES)
    assert process(model, ["rust"], tmp_path) == []


def test_methods_named_as_a_constructor_or_as_ptr_build_without_warnings(
    parse, tmp_path
):
    model, _ = parse(
        "struct api_h;\n"
        + doc("From", "@param[out] h H", "@errno")
        + "int api_from_file(const char *path, struct api_h **h);\n"
        + doc("Reload", "@errno")
        + "int api_h_from_file(struct api_h *h, const char *path);\n"
        + doc("Close", "@destroys h")
        + "void api_close(struct api_h *h);\n"
        + doc("As")
        + "int api_h_as_ptr(struct api_h *h);\n"
        + doc("Get", "@param[out] retval R")
        + "void api_get(int *retval);\n"
    )
    assert process(model, ["rust"], tmp_path) == []
    assert "warning" not in (tmp_path / "rust" / "cargo.log").read_text()


def test_functions_sharing_a_name_keep_their_c_names(parse, tmp_path):
    model, _ = parse(SHARED)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn api_bar(x: c_int) -> c_int" in lib


def test_a_function_named_as_a_record_has_its_own_doc(parse, tmp_path):
    model, _ = parse(
        "/** The record */\nstruct api_tag;\n"
        + doc("The function")
        + "int api_tag(int v);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "    /// The function\n    ///\n    /// Calls [`super::api_tag`]." in lib


def test_closure_types_named_as_raw_types_build(parse, tmp_path):
    model, _ = parse(
        "typedef int (*api_cb)(void *arg, int v);\n"
        "typedef int (*api_cb_fn)(void *arg, int v);\n"
        "typedef int (*api_outer_cb)(void *arg, api_cb_fn inner);\n"
        + doc("Run", "@lifetime cb call")
        + "int api_run(api_cb cb, void *arg);\n"
        + doc("Outer", "@lifetime cb call")
        + "int api_outer(api_outer_cb cb, void *arg);\n"
    )
    assert process(model, ["rust"], tmp_path) == []


def test_closure_types_named_as_handles_build(parse, tmp_path):
    model, _ = parse(
        "struct api_api_cb_fn;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_api_cb_fn **h);\n"
        + doc("Visit", "@lifetime cb call")
        + "int api_visit(struct api_api_cb_fn *h, api_cb cb, void *arg);\n"
    )
    assert process(model, ["rust"], tmp_path) == []


def test_handles_named_as_std_types_get_a_handle_suffix(parse, tmp_path):
    model, _ = parse(
        "struct api_option;\nstruct api_vec;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_option **h);\n"
        + doc("Set", "@nullable name")
        + "void api_set(struct api_option *h, const char *name);\n"
        + doc("Make", "@param[out] v V", "@errno")
        + "int api_make(struct api_vec **v);\n"
        + doc("Fill", "@arrparam[in] vals V @len_at{n}")
        + "void api_fill(struct api_vec *v, const int *vals, unsigned n);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub struct OptionHandle" in lib and "pub struct VecHandle" in lib


KEPT = (
    "#include <stdint.h>\nstruct api_h;\n"
    "typedef int (*api_cb)(void *arg, int v);\n"
    + doc("Open", "@param[out] h H", "@errno")
    + "int api_open(struct api_h **h);\n"
    + doc("Close", "@destroys h")
    + "void api_close(struct api_h *h);\n"
    + doc("On", "@lifetime cb handle", "@errno")
    + "int api_on(struct api_h *h, api_cb cb, void *arg);\n"
    + doc("Fire", "@errno")
    + "int api_fire(struct api_h *h, int v);\n"
    + doc("Submit", "@nullable cb", "@lifetime cb once", "@errno")
    + "int api_submit(struct api_h *h, api_cb cb, void *arg);\n"
    + doc("Poke", "@errno")
    + "int64_t api_poke(struct api_h *h);\n"
)

KEPT_C = """
#include <stdlib.h>
struct api_h { api_cb on, once; void *on_arg, *once_arg; };
int api_open(struct api_h **h) { *h = calloc(1, sizeof(**h)); return 0; }
void api_close(struct api_h *h) { free(h); }
int api_on(struct api_h *h, api_cb cb, void *arg)
{
	if (h->on) return -16;
	h->on = cb; h->on_arg = arg; return 0;
}
int api_fire(struct api_h *h, int v) { return h->on ? h->on(h->on_arg, v) : -22; }
int api_submit(struct api_h *h, api_cb cb, void *arg)
{
	if (!cb) return 0;
	if (h->once) return -16;
	h->once = cb; h->once_arg = arg; return 0;
}
int64_t api_poke(struct api_h *h)
{
	api_cb cb = h->once;
	if (!cb) return 0;
	h->once = NULL;
	cb(h->once_arg, 7);
	return 1;
}
"""


@needs_cc
def test_kept_closures_are_called_and_released(parse, tmp_path):
    model, _ = parse(KEPT)
    assert process(model, ["rust"], tmp_path) == []
    (tmp_path / "api.c").write_text(KEPT + KEPT_C)
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
        + ["-o", str(tmp_path / "libapi.so")],
        check=True,
    )
    main = """
use std::cell::Cell;
use std::rc::Rc;
fn main() {
    let seen = Rc::new(Cell::new(0));
    let mut h = api::safe::H::open().unwrap();
    let s = seen.clone();
    h.on(Box::new(move |v| { s.set(s.get() + v); 0 })).unwrap();
    let s = seen.clone();
    let taken = h.on(Box::new(move |v| { s.set(s.get() + 10 * v); 0 }));
    h.submit(None).unwrap();
    let s = seen.clone();
    h.submit(Some(Box::new(move |v| { s.set(s.get() + 100 * v); 0 }))).unwrap();
    let s = seen.clone();
    let busy = h.submit(Some(Box::new(move |v| { s.set(s.get() + 1000 * v); 0 })));
    println!("{} {} {}", taken.is_err(), busy.is_err(), Rc::strong_count(&seen));
    println!("{}", h.poke().unwrap());
    h.fire(5).unwrap();
    println!("{} {}", seen.get(), Rc::strong_count(&seen));
    drop(h);
    println!("{}", Rc::strong_count(&seen));
}
"""
    out = run_with_crate(
        tmp_path,
        main,
        {
            "API_LIB_DIR": str(tmp_path),
            "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
        },
    )
    assert out == "true true 3\n1\n705 2\n1\n"


@needs_cc
def test_a_closure_run_once_by_any_later_call_is_send(parse, tmp_path):
    header = (
        "typedef void (*api_cb)(void *arg, int v);\n"
        + doc("Submit", "@lifetime cb once", "@errno")
        + "int api_submit(api_cb cb, void *arg);\n"
        + doc("Poll")
        + "void api_poll(void);\n"
    )
    model, _ = parse(header)
    assert process(model, ["rust"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "static api_cb once;\nstatic void *once_arg;\n"
        "int api_submit(api_cb cb, void *arg)\n"
        "{ once = cb; once_arg = arg; return 0; }\n"
        "void api_poll(void)\n"
        "{ api_cb cb = once; once = 0; if (cb) cb(once_arg, 7); }\n"
    )
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
        + ["-o", str(tmp_path / "libapi.so")],
        check=True,
    )
    env = {
        "API_LIB_DIR": str(tmp_path),
        "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
    }
    sent = """
use std::sync::{Arc, atomic::{AtomicI32, Ordering}};
fn main() {
    let seen = Arc::new(AtomicI32::new(0));
    let s = seen.clone();
    api::safe::submit(Box::new(move |v| s.store(v, Ordering::SeqCst))).unwrap();
    std::thread::spawn(api::safe::poll).join().unwrap();
    println!("{} {}", seen.load(Ordering::SeqCst), Arc::strong_count(&seen));
}
"""
    assert run_with_crate(tmp_path, sent, env) == "7 1\n"

    kept = """
use std::{cell::Cell, rc::Rc};
fn main() {
    let seen = Rc::new(Cell::new(0));
    let s = seen.clone();
    api::safe::submit(Box::new(move |v| s.set(v))).unwrap();
}
"""
    errors = run_with_crate(tmp_path, kept, env, user="rc", fails=True)
    assert "cannot be sent between threads safely" in errors


@needs_cc
def test_a_record_the_caller_may_write_is_not_copied(parse, tmp_path):
    model, _ = parse(POOL)
    assert process(model, ["rust"], tmp_path) == []
    (tmp_path / "api.c").write_text(POOL + POOL_C)
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
        + ["-o", str(tmp_path / "libapi.so")],
        check=True,
    )
    main = """
fn main() {
    let mut q = api::safe::Q::open().unwrap();
    let c = q.get();
    unsafe {
        (*c).opc = 7;
        q.put(&mut *c).unwrap();
    }
    let peeked = q.peek();
    let d = q.get();
    println!("{} {} {}", d == c, unsafe { (*d).opc }, peeked.opc);
}
"""
    out = run_with_crate(
        tmp_path,
        main,
        {
            "API_LIB_DIR": str(tmp_path),
            "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
        },
    )
    assert out == "true 7 7\n"


POOL = (
    "struct api_q;\nstruct api_cmd { int opc; struct api_cmd *next; };\n"
    + doc("Open", "@param[out] q Q", "@errno")
    + "int api_open(struct api_q **q);\n"
    + doc("Close", "@destroys q")
    + "void api_close(struct api_q *q);\n"
    + doc("Get", "@nullable return")
    + "struct api_cmd *api_get(struct api_q *q);\n"
    + doc("Put", "@errno")
    + "int api_put(struct api_q *q, struct api_cmd *cmd);\n"
    + doc("Peek")
    + "const struct api_cmd *api_peek(const struct api_q *q);\n"
)

POOL_C = """
#include <stdlib.h>
struct api_q { struct api_cmd pool[2]; struct api_cmd *head; };
int api_open(struct api_q **q)
{
	*q = calloc(1, sizeof(**q));
	(*q)->pool[0].next = &(*q)->pool[1];
	(*q)->head = &(*q)->pool[0];
	return 0;
}
void api_close(struct api_q *q) { free(q); }
struct api_cmd *api_get(struct api_q *q)
{
	struct api_cmd *c = q->head;
	if (c) q->head = c->next;
	return c;
}
int api_put(struct api_q *q, struct api_cmd *c)
{
	c->next = q->head;
	q->head = c;
	return 0;
}
const struct api_cmd *api_peek(const struct api_q *q) { return q->head; }
"""


def test_a_constructor_without_errno_keeps_no_closures_and_an_inline_callback_is_raw(
    parse, tmp_path
):
    model, _ = parse(
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H")
        + "void api_open(struct api_h **h);\n"
        + doc("Watch", "@lifetime cb handle", "@errno")
        + "int api_watch(struct api_h *h, api_cb cb, void *arg);\n"
        + doc("Each", "@lifetime fn call")
        + "int api_each(int (*fn)(void *ctx, int v), void *ctx);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert flat("map(|ptr| H { ptr, keep: Vec::new() })") in flat(lib)
    assert "pub unsafe fn each(r#fn: Option<unsafe extern" in flat(lib)


def test_inline_callbacks_kept_by_errno_functions_build(parse, tmp_path):
    model, _ = parse(
        "struct api_h;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Once", "@lifetime fn once", "@errno")
        + "int api_once(struct api_h *h, int (*fn)(void *ctx, int v), void *ctx);\n"
        + doc("Kept", "@lifetime fn handle", "@errno")
        + "int api_kept(struct api_h *h, int (*fn)(void *ctx, int v), void *ctx);\n"
    )
    assert process(model, ["rust"], tmp_path) == []


@needs_cc
def test_closures_kept_by_a_handle_whose_destructor_fails_are_kept(parse, tmp_path):
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
    assert process(model, ["rust"], tmp_path) == []
    assert "warning" not in (tmp_path / "rust" / "cargo.log").read_text()
    (tmp_path / "api.c").write_text(
        header + "static int h;\n"
        "int api_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }\n"
        "int api_close(struct api_h *p) { (void)p; return -5; }\n"
        "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ (void)p; (void)cb; (void)arg; }\n"
    )
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
        + ["-o", str(tmp_path / "libapi.so")],
        check=True,
    )
    main = (
        "use std::rc::Rc;\nfn main() {\n"
        "    let seen = Rc::new(0);\n"
        "    let mut h = api::safe::H::open().unwrap();\n"
        "    let s = seen.clone();\n"
        "    h.on(Box::new(move |v| v + *s));\n"
        "    let failed = h.close().is_err();\n"
        "    {\n"
        "        let mut g = api::safe::H::open().unwrap();\n"
        "        let s = seen.clone();\n"
        "        g.on(Box::new(move |v| v + *s));\n"
        "        let s = seen.clone();\n"
        "        let mut a = api::safe::H::open().unwrap();\n"
        "        a.on(Box::new(move |v| v + *s));\n"
        "        a = api::safe::H::open().unwrap();\n"
        "        let _ = &a;\n"
        "    }\n"
        '    println!("{} {}", failed, Rc::strong_count(&seen));\n'
        "}\n"
    )
    out = run_with_crate(
        tmp_path,
        main,
        {
            "API_LIB_DIR": str(tmp_path),
            "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
        },
    )
    assert out == "true 4\n"


def test_a_function_named_drop_builds(parse, tmp_path):
    model, _ = parse(
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Close", "@destroys h", "@errno")
        + "int api_close(struct api_h *h);\n"
        + doc("On", "@lifetime cb handle")
        + "void api_on(struct api_h *h, api_cb cb, void *arg);\n"
        + doc("Later", "@lifetime cb once")
        + "void api_later(struct api_h *h, api_cb cb, void *arg);\n"
        + doc("Drop")
        + "int api_drop(int x);\n"
    )
    assert process(model, ["rust"], tmp_path) == []


def test_closures_kept_by_a_handle_nothing_destroys_are_kept(parse, tmp_path):
    model, _ = parse(
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("On", "@lifetime cb handle")
        + "void api_on(struct api_h *h, api_cb cb, void *arg);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "std::mem::forget(std::mem::take(&mut self.keep));" in lib


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["rust"], tmp_path) == []


BITS_PRINTED = (
    "api_status:\n"
    "  code: {val: 0x8a05, type: 0x5, delay: 0xa, dnr: 0x1}\n"
    "  wide: {val: 0x8000000100000002, low: 0x2, top: 0x1}\n"
    '{"code": {"val": 35333, "type": 5, "delay": 10, "dnr": 1},'
    ' "wide": {"val": 9223372041149743106, "low": 2, "top": 1}}\n'
)


def test_a_field_of_bits_prints_its_parts(parse, tmp_path):
    model, _ = parse(BITS)
    assert process(model, ["rust"], tmp_path) == []

    main = (
        "use api::*;\nfn main() {\n"
        "    let s = ApiStatus { code: 0x8a05, wide: 0x8000000100000002 };\n"
        '    print!("{}", s);\n'
        "    ApiStatus::fpr(&mut std::io::stdout(), Some(&s), API_PR_JSON).unwrap();\n"
        "}\n"
    )
    assert run_with_crate(tmp_path, main, {"API_NO_LINK": "1"}) == BITS_PRINTED


BITS_UNION = (
    "/** U */\nunion api_u {\n"
    "\tuint32_t type; ///< Type, see API_U_TYPE_*\n\tint32_t i; ///< Signed\n};\n"
    "/** High half; bits 31:16 of 'type' */\n#define API_U_TYPE_HI 0xffff0000\n"
)


def test_the_parts_of_a_field_of_bits_are_methods(parse, tmp_path):
    model, _ = parse(BITS + BITS_UNION)
    assert process(model, ["rust"], tmp_path) == []
    assert "warning" not in (tmp_path / "rust" / "cargo.log").read_text()

    main = (
        "use api::*;\nfn main() {\n"
        "    let mut s = ApiStatus { code: 0x8a05, wide: 0x8000000100000002 };\n"
        '    println!("{} {} {} {} {}", s.code_type(), s.code_delay(), s.code_dnr(),'
        " s.wide_low(), s.wide_top());\n"
        "    s.set_code_delay(3);\n    s.set_code_dnr(0);\n"
        '    println!("{:#x} {}", s.code, s.code_type());\n'
        "    let over = std::panic::catch_unwind(|| {\n"
        "        ApiStatus::default().set_code_delay(16);\n    });\n"
        '    println!("{}", over.is_err());\n'
        "    let mut u = ApiU::default();\n    u.set_type_hi(0xabcd);\n"
        '    println!("{:#x} {:#x}", unsafe { u.r#type }, u.type_hi());\n'
        "}\n"
    )
    assert run_with_crate(tmp_path, main, {"API_NO_LINK": "1"}) == (
        "5 10 1 2 1\n0x305 5\ntrue\n0xabcd0000 0xabcd\n"
    )
    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "/// Kind; bits 2:0 of 'code'\n    pub fn code_type(&self) -> u16 {" in lib


def test_a_packed_record_is_read_by_copies(parse, tmp_path):
    model, _ = parse(
        PACKED + "/** R, its Debug written out, as a field is renamed */\n"
        "struct __attribute__((packed)) api_r {\n"
        "\tuint8_t a; ///< A\n\tuint32_t self; ///< Self\n};\n"
    )
    assert process(model, ["rust"], tmp_path) == []
    assert "warning" not in (tmp_path / "rust" / "cargo.log").read_text()
    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "#[repr(C, packed)]\n#[derive(Clone, Copy, Debug)]\npub struct ApiK {" in lib

    main = (
        "use api::*;\nfn main() {\n"
        "    let p = |x, y| ApiP { x, y };\n"
        "    let mut k = ApiK { tag: 1, value: 0xdeadbeef, at: p(-2, 3),"
        " path: [p(4, 5), p(6, 7)], pair: [8, 9], r#type: 0x10 };\n"
        "    k.set_type_low(0xa);\n"
        '    print!("{}", k);\n'
        "    ApiK::fpr(&mut std::io::stdout(), Some(&k), API_PR_JSON).unwrap();\n"
        '    println!("{:?} {}", k, k.type_low());\n'
        '    println!("{:?}", ApiR { a: 1, self_: 2 });\n'
        "}\n"
    )
    assert run_with_crate(tmp_path, main, {"API_NO_LINK": "1"}) == PACKED_PRINTED + (
        "ApiK { tag: 1, value: 3735928559, at: ApiP { x: -2, y: 3 }, path:"
        " [ApiP { x: 4, y: 5 }, ApiP { x: 6, y: 7 }], pair: [8, 9], type: 26 } 10\n"
        "ApiR { a: 1, self: 2 }\n"
    )


# Strings with a length, which C reads as bytes, one sharing its length with an
# array, and an [out] array of bytes that is no void *
COUNTED = (
    "#include <stddef.h>\n#include <stdint.h>\n"
    + doc("Put", "@arrparam buf B @len_at{n}")
    + "size_t api_put(const char *buf, size_t n);\n"
    + doc("Pair", "@arrparam w W @len_at{n}", "@arrparam v V @len_at{n}")
    + "size_t api_pair(const char *w, const int *v, size_t n);\n"
    + doc("Read", "@arrparam[out] buf B", "@errno")
    + "int api_read(uint8_t *buf, size_t buf_len);\n"
)

COUNTED_C = """
size_t api_put(const char *buf, size_t n) { (void)buf; return n; }
size_t api_pair(const char *w, const int *v, size_t n)
{
\treturn (size_t)(unsigned char)w[n - 1] + (size_t)v[n - 1];
}
int api_read(uint8_t *buf, size_t buf_len)
{
\tfor (size_t i = 0; i < buf_len; i++)
\t\tbuf[i] = (uint8_t)i;
\treturn 0;
}
"""


def test_strings_with_a_length_and_byte_arrays_build(parse, tmp_path):
    model, _ = parse(COUNTED)
    assert process(model, ["rust"], tmp_path) == []

    lib = flat((tmp_path / "rust" / "bindings.rs").read_text())
    assert "pub fn put(buf: &str) -> usize" in lib
    assert "buf.as_ptr() as *const c_char, buf.len() as usize" in lib
    assert "pub fn pair(w: &str, v: &[c_int]) -> usize" in lib
    assert "super::api_read(buf.as_mut_ptr(), buf.len() as usize)" in lib


def test_a_nullable_out_array_is_a_buffer_always_given(parse, tmp_path):
    model, _ = parse(
        "#include <stddef.h>\n#include <stdint.h>\n"
        + doc("Fill", "@arrparam[out] v V @len_at{n}", "@param n N", "@nullable v")
        + "void api_fill(int32_t *v, size_t n);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn fill<'buf>(v: &'buf mut [i32]) -> &'buf mut [i32]" in lib
    assert "v.len() as usize" in lib


def run_with_library(tmp_path, model, source: str, main: str, fails=False):
    """Generate the crate of 'model', build 'source' as its library, and run
    'main' against both, as run_with_crate() does"""

    assert process(model, ["rust"], tmp_path) == []
    library(tmp_path, source)
    env = {
        "API_LIB_DIR": str(tmp_path),
        "RUSTFLAGS": f"-C link-arg=-Wl,-rpath,{tmp_path}",
    }
    return run_with_crate(tmp_path, main, env, fails=fails)


@needs_cc
@needs_cargo
def test_an_allocated_buffer_is_freed_when_dropped_and_borrows_its_handle(
    parse, tmp_path
):
    from tests.test_python import BUFFERS, BUFFERS_C

    model, _ = parse(BUFFERS)
    main = """
use api::safe::*;
fn main() {
    let dev = Dev::open().unwrap();
    {
        let mut buf = dev.buf_alloc(4).unwrap();
        unsafe { buf.as_mut_slice() }.copy_from_slice(&[1, 2, 3, 4]);
        println!("{} {}", buf.len(), sum(unsafe { buf.as_slice() }));
        buf.realloc(8).unwrap();
        println!("{} {:?}", buf.len(), &unsafe { buf.as_slice() }[..4]);
        let _other = dev.buf_alloc(2).unwrap();
    }
    println!("{}", freed());
}
"""
    out = run_with_library(tmp_path, model, BUFFERS + BUFFERS_C, main)
    assert out == "4 10\n8 [1, 2, 3, 4]\n2\n"

    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn buf_free" not in lib and "pub fn buf_realloc" not in lib

    # The handle cannot be dropped while a buffer it allocated is alive
    early = main.replace("let _other = dev.buf_alloc(2).unwrap();", "drop(dev);")
    (tmp_path / "user").rename(tmp_path / "user-ran")
    err = run_with_library(tmp_path, model, BUFFERS + BUFFERS_C, early, fails=True)
    assert "because it is borrowed" in err


@needs_cc
@needs_cargo
def test_an_allocation_returns_its_out_values_with_the_buffer(parse, tmp_path):
    from tests.test_python import PHYS, PHYS_C

    model, _ = parse(PHYS)
    main = """
use api::safe::*;
fn main() {
    let dev = Dev::open().unwrap();
    let (phys, buf) = dev.buf_alloc(16);
    let mut buf = buf.unwrap();
    let (none_phys, none) = dev.buf_alloc(2048);
    println!("{} {} {} {}", phys, buf.len(), none_phys, none.is_none());
    println!("{}", buf.realloc(32).is_err());
    drop(buf);
    println!("{}", freed());
}
"""
    out = run_with_library(tmp_path, model, PHYS + PHYS_C, main)
    assert out == "4096 16 0 true\ntrue\n1\n"
    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn buf_realloc" not in lib


@needs_cc
@needs_cargo
def test_registered_memory_is_borrowed_until_unregistered(parse, tmp_path):
    from tests.test_python import REGISTRATIONS, REGISTRATIONS_C

    model, _ = parse(REGISTRATIONS)
    main = f"""
use api::safe::*;
fn main() {{
    let dev = Dev::open().unwrap();
    let mut memory = vec![0u8; 16];
    let at = memory.as_ptr() as usize;
    {{
        let mut reg = dev.buf_register(&mut memory).unwrap();
        reg[0] = 7;
        println!("{{}} {{}}", registered() == at, registered_nbytes());
        let mut other = [0u8; 8];
        let busy = dev.buf_register(&mut other).err().and_then(|e| e.raw_os_error());
        println!("{{}}", busy == Some({errno.EBUSY}));
    }}
    println!("{{}} {{}}", registered(), memory[0]);
    let reg = dev.buf_register(&mut memory).unwrap();
    println!("{{}} {{}}", reg.unregister().is_ok(), registered());
}}
"""
    out = run_with_library(tmp_path, model, REGISTRATIONS + REGISTRATIONS_C, main)
    assert out == "true 16\ntrue\n0 7\ntrue 0\n"
    lib = (tmp_path / "rust" / "bindings.rs").read_text()
    assert "pub fn buf_unregister" not in lib
    assert "pub unsafe fn buf_register" not in lib
