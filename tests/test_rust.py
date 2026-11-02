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


def doc(*lines):
    return "/**\n" + "".join(f" * {line}\n" for line in lines) + " */\n"


def misindented_docs(source: str) -> list:
    """The doc comment lines indented otherwise than what they document"""

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
    + doc("Each", "@nullable cb", "@errno")
    + "int64_t api_each(struct api_h *h, api_cb cb, void *arg);\n"
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
    + doc("Pointers", "@param[out] ptrs P", "@len ptrs n", "@errno")
    + "int api_ptrs(struct api *h, int **ptrs, size_t n);\n"
)


def test_a_handle_named_as_the_prefix_and_out_pointers_build(parse, tmp_path):
    model, _ = parse(HANDLE_NAMED_AS_PREFIX)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub struct ApiHandle {" in lib
    assert "vec![std::ptr::null_mut(); n as usize]" in lib


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
    + doc("Dot", "@len a n", "@len b n")
    + "long api_dot(const int *a, const int *b, size_t n);\n"
    + doc("Map", "@param[out] out O", "@len in n", "@len out n", "@errno")
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


def test_shared_counts_handles_given_and_constructors_without_errno(parse, tmp_path):
    model, _ = parse(MORE)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub fn copy(&mut self, src: &H) -> io::Result<()>" in lib
    assert "pub fn make() -> Option<H>" in lib
    assert "assert_eq!(b.len(), a.len()," in lib
    assert "assert_eq!(r#in.len(), n as usize," in lib


IO = (
    "#include <stddef.h>\n#include <stdint.h>\nstruct api_h;\nstruct api_x;\n"
    + doc("Open", "@param[out] h H", "@errno")
    + "int api_open(struct api_h **h);\n"
    + doc("Close", "@destroys h", "@errno")
    + "int api_close(struct api_h *h);\n"
    + doc("Clone", "@param[out] copy C", "@errno")
    + "int api_clone(const struct api_h *h, struct api_h **copy);\n"
    + doc("Write", "@len buf n")
    + "size_t api_write(const void *buf, size_t n);\n"
    + doc("Read", "@param[out] buf B", "@len buf n", "@errno")
    + "int64_t api_read(void *buf, size_t n);\n"
    + doc("Pair", "@param[out] a A", "@param[out] b B", "@len a n", "@len b n")
    + "void api_pair(int32_t *a, int32_t *b, size_t n);\n"
    + doc("Twice", "@param[in,out] v V", "@len v n")
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


def test_bytes_out_arrays_sharing_a_count_and_clones_build(parse, tmp_path):
    model, _ = parse(IO)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub fn write(buf: &[u8]) -> usize" in lib
    assert "pub fn read(n: usize) -> io::Result<Vec<u8>>" in lib
    assert "pub fn clone(&self) -> io::Result<H>" in lib


def test_the_idiomatic_layer_builds_for_every_kind_of_parameter(parse, tmp_path):
    model, _ = parse(EDGES)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub fn open(name: Option<&CStr>) -> io::Result<H>" in lib
    assert (
        "pub fn each(&mut self, cb: Option<&mut ApiCbFn>) -> io::Result<usize>" in lib
    )
    assert "pub fn step(&mut self, pos: &mut usize) -> io::Result<c_int>" in lib
    assert "pub unsafe fn raw(&mut self, p: &mut ApiP, opaque: *mut c_void)" in lib
    assert "pub fn close(self) -> io::Result<()>" in lib
    assert "fn inline(" not in lib  # no trampoline for an inline callback type
    assert "pub fn other(&mut self) -> *mut ApiH" in lib
    assert "pub fn base(path: &CStr) -> &CStr" in lib
    assert "pub unsafe fn pick(a: &CStr, b: &CStr) -> &'static CStr" in lib
    assert "pub fn version() -> &'static CStr" in lib
    assert misindented_docs(lib) == []


@needs_cc
def test_a_panic_in_a_closure_aborts(parse, tmp_path):
    header = (
        "typedef int (*api_cb)(void *arg, int v);\n"
        + doc("Each", "@param cb C", "@param arg A")
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
        + doc("Sum", "@nullable v", "@len v n")
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


# Parameters named as the locals the layers derive from the name of 'cb'
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
    + doc("In out", "@param[in,out] ret R", "@len ret n")
    + "void api_ioret(int *ret, size_t n);\n"
    + doc("Names", "@lifetime a1 call")
    + "int api_names(int a0, api_cb a1, void *arg);\n"
    + doc("Call", "@nullable cb", "@lifetime cb call", "@errno")
    + f"int api_call(api_cb cb, void *arg, {LOCALS});\n"
    + doc("Sum", "@len xs n")
    + "int api_sum(const int *xs, size_t n, int xs_c, int xs_cb);\n"
    + doc("Outs", "@param[out] x X", "@param[out] ys Y", "@len ys n")
    + "void api_outs(int *x, int *ys, size_t n, int x_out, int ys_out);\n"
    + "typedef int (*api_x_cb)(void *arg, int v);\n"
    + doc("Two", "@lifetime api_x call other call")
    + "int api_two(api_x_cb api_x, void *arg, api_x_cb other, void *oarg);\n"
    + doc("Count", "@len api n")
    + "size_t api_c(const int *api, size_t n);\n"
)

NAMES_C = (
    f"#define LOCALS {LOCALS}\n"
    + """
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
int api_sum(const int *xs, size_t n, int xs_c, int xs_cb)
{ int s = xs_c + xs_cb; for (size_t i = 0; i < n; i++) s += xs[i]; return s; }
void api_outs(int *x, int *ys, size_t n, int x_out, int ys_out)
{ *x = x_out; for (size_t i = 0; i < n; i++) ys[i] = ys_out; }
int api_two(api_x_cb x, void *arg, api_x_cb other, void *oarg)
{ return x(arg, 1) + other(oarg, 2); }
size_t api_c(const int *api, size_t n) { (void)api; return n; }
"""
)


# Parameters named as what a body uses unqualified, or as each other renamed
HIDDEN = (
    "#include <stddef.h>\n#include <stdio.h>\nstruct api_dev;\nstruct api_cb_out;\n"
    "typedef int (*api_cb)(void *arg, int v);\ntypedef unsigned api_u32;\n"
    + doc("Mode")
    + "enum api_mode { api_mode_read = 0, api_mode_write = 1 };\n"
    + doc("Set")
    + "int api_set(int api_mode_read, int ApiMode);\n"
    + doc("Locals")
    + "enum api_e { ret = 1, s, context, h, p, err, tag, field, self, a0 };\n"
    + doc("Count", "@nullable xs", "@len xs n")
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
int api_node_value(api_node n, const struct api_node *m) { return n->v - m->v; }
static struct { unsigned len; unsigned char data[3]; } msg = { 3, { 1, 2, 3 } };
struct api_msg *api_dev_msg(struct api_dev *d)
{ (void)d; return (struct api_msg *)&msg; }
int api_dev_get(struct api_dev *d) { (void)d; return 1; }
int api_dev_get_(struct api_dev *d) { (void)d; return 2; }
int api_take(int x) { return x; }
int api_take_(int x) { return x + 1; }
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


def test_parameters_named_as_what_the_body_uses_build(parse, tmp_path):
    model, _ = parse(HIDDEN)
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub fn msg(&mut self) -> *mut ApiMsg {" in lib  # not a copy


def test_parameters_named_as_locals_of_the_layer_build(parse, tmp_path):
    model, _ = parse(NAMES)
    assert process(model, ["rust"], tmp_path) == []


def test_constructors_and_methods_sharing_a_name_and_as_ptr(parse, tmp_path):
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

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub fn api_bar(x: c_int) -> c_int" in lib


def test_a_function_named_as_a_record_has_its_own_doc(parse, tmp_path):
    model, _ = parse(
        "/** The record */\nstruct api_tag;\n"
        + doc("The function")
        + "int api_tag(int v);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "    /// The function\n    ///\n    /// Calls [`super::api_tag`]." in lib


def test_closure_types_named_as_raw_types(parse, tmp_path):
    model, _ = parse(
        "typedef int (*api_cb)(void *arg, int v);\n"
        "typedef int (*api_cb_fn)(void *arg, int v);\n"
        "typedef int (*api_outer_cb)(void *arg, api_cb_fn inner);\n"
        + doc("Run")
        + "int api_run(api_cb cb, void *arg);\n"
        + doc("Outer")
        + "int api_outer(api_outer_cb cb, void *arg);\n"
    )
    assert process(model, ["rust"], tmp_path) == []


def test_closure_types_named_as_handles(parse, tmp_path):
    model, _ = parse(
        "struct api_api_cb_fn;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_api_cb_fn **h);\n"
        + doc("Visit", "@lifetime cb call")
        + "int api_visit(struct api_api_cb_fn *h, api_cb cb, void *arg);\n"
    )
    assert process(model, ["rust"], tmp_path) == []


def test_handles_named_as_std_types(parse, tmp_path):
    model, _ = parse(
        "struct api_option;\nstruct api_vec;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_option **h);\n"
        + doc("Set", "@nullable name")
        + "void api_set(struct api_option *h, const char *name);\n"
        + doc("Make", "@param[out] v V", "@errno")
        + "int api_make(struct api_vec **v);\n"
        + doc("Fill", "@param[in] vals V", "@len vals n")
        + "void api_fill(struct api_vec *v, const int *vals, int n);\n"
    )
    assert process(model, ["rust"], tmp_path) == []

    lib = (tmp_path / "rust" / "lib.rs").read_text()
    assert "pub struct OptionHandle" in lib and "pub struct VecHandle" in lib


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["rust"], tmp_path) == []
