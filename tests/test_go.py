# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import os
import subprocess

import pytest

from tests.conftest import (
    BITS,
    ESCAPED,
    ESCAPED_VALUE,
    HEADERS,
    PACKED,
    PACKED_PRINTED,
    SKIPPED,
    needs_cc,
    needs_go,
)
from tests.test_rust import (
    BITS_PRINTED,
    BITS_UNION,
    EDGES,
    HANDLE_NAMED_AS_PREFIX,
    HIDDEN,
    IO,
    IO_C,
    KEPT,
    KEPT_C,
    MORE,
    MORE_C,
    NAMES,
    SHARED,
    doc,
)
from yace.compiler import process
from yace.targets.go.target import GO_VERSION, Go

pytestmark = needs_go


def run_go(tmp_path, main: str, impl: str = "", strict: bool = False) -> str:
    """Build and run 'main', the source of a Go program, against the package
    generated into 'tmp_path'; linked with 'impl', the C source of the library,
    or with nothing, by the tag 'api_no_link'. 'strict' checks every pointer
    crossing to C, as GOEXPERIMENT=cgocheck2 does. Returns what it printed."""

    project = tmp_path / "user"
    project.mkdir()
    (project / "go.mod").write_text(
        f"module user\n\ngo {GO_VERSION}\n\nrequire api v0.0.0\n\n"
        f"replace api => {tmp_path / 'go'}\n"
    )
    (project / "main.go").write_text(main)
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOTOOLCHAIN": "local"}
    cmd = ["go", "build", "-buildvcs=false", "-o", str(tmp_path / "user.bin")]
    if impl:
        (tmp_path / "api.c").write_text(impl)
        subprocess.run(
            ["cc", "-shared", "-fPIC", str(tmp_path / "api.c")]
            + ["-o", str(tmp_path / "libapi.so")],
            check=True,
        )
        env["CGO_LDFLAGS"] = f"-L{tmp_path} -Wl,-rpath,{tmp_path}"
    else:
        cmd += ["-tags", "api_no_link"]
    if strict:
        env["GOEXPERIMENT"] = "cgocheck2"
    build = subprocess.run(
        cmd + ["."], cwd=project, capture_output=True, text=True, env=env
    )
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(tmp_path / "user.bin")], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    return run.stdout


def program(body: str, imports=("fmt",)) -> str:
    """A Go program of 'body', in main(), importing the package as 'api'"""

    lines = "".join(f'\t"{name}"\n' for name in imports)
    return (
        f'package main\n\nimport (\n{lines}\n\t"api"\n)\n\nfunc main() {{\n{body}}}\n'
    )


@needs_cc
def test_the_subset_prints_as_the_c_api_does(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["capi", "go"], tmp_path) == []

    for fmt in ("yaml", "json"):
        c_out = (tmp_path / "capi" / f"check.{fmt}").read_text()
        assert (tmp_path / "go" / f"check.{fmt}").read_text() == c_out


# A value of every kind a printer prints, a union, and a field of bits
VALUES = (
    "#include <stdbool.h>\n#include <stddef.h>\n#include <stdint.h>\n"
    "/** E */\nenum api_e { API_E_A = -1, API_E_B = 2, API_E_C = 2 };\n"
    "/** P */\nstruct api_p { int32_t x; int32_t y; };\n"
    "/** Called */\ntypedef void (*api_cb)(void *arg);\n"
    "/** V */\nstruct api_v {\n"
    "\tbool flag; char letter; char high; signed char sc; unsigned char uc;\n"
    "\tint64_t i64; uint64_t u64; size_t size; long l; unsigned long ul;\n"
    "\tfloat f; double d; enum api_e e;\n"
    "\tconst char *label; const char *none; char name[4]; char full[4];\n"
    "\tvoid *ptr; void *nil; api_cb cb; struct api_p at; struct api_p path[2];\n"
    "\tint16_t grid[2][2];\n};\n"
    "/** U */\nunion api_u { uint32_t u; struct api_p p; uint16_t h[2]; };\n"
    "/** G */\nstruct api_g { double d[11]; float f[3]; };\n"
) + BITS

# The C printers, called on the records the Go program fills in
VALUES_C = r"""#include <stdio.h>
#include <libapi.h>
void cb(void *arg) { (void)arg; }
void print_all(const void *v, const void *u, const void *s, const void *g)
{
	for (int flags = API_PR_YAML; flags <= API_PR_JSON; flags++) {
		api_v_fpr(stdout, v, flags);
		api_u_fpr(stdout, u, flags);
		api_status_fpr(stdout, s, flags);
		api_g_fpr(stdout, g, flags);
		api_v_fpr(stdout, NULL, flags);
	}
	int values[] = { -1, 2, 3 };
	for (int i = 0; i < 3; i++) {
		printf("%s\n", api_e_str(values[i]));
	}
	fflush(stdout);
}
"""

VALUES_GO = r"""package main

/*
#cgo CFLAGS: -I${SRCDIR}
#include <stdlib.h>
void cb(void *arg);
void print_all(const void *v, const void *u, const void *s, const void *g);
*/
import "C"

import (
	"fmt"
	"math"
	"os"
	"unsafe"

	"api"
)

func main() {
	var v api.ApiV
	v.Flag, v.Letter, v.High, v.Sc, v.Uc = true, 'y', 0xe9, -2, 250
	v.I64, v.U64, v.Size, v.L, v.Ul = math.MinInt64, math.MaxUint64, 11, -5, 6
	v.F, v.D, v.E = 0.1, -2.5e-5, api.API_E_A
	v.Label = (*byte)(unsafe.Pointer(C.CString("say \"hi\"\t\\ \x7f \xc3\xa9")))
	copy(v.Name[:], "ab")
	copy(v.Full[:], "abcd")
	v.Ptr, v.Cb = C.malloc(1), api.ApiCb(C.cb)
	v.At, v.Path[1], v.Grid[0][1] = api.ApiP{X: -1, Y: 2}, api.ApiP{X: 3, Y: 4}, -5
	var u api.ApiU
	*u.U() = 0xffffffff
	s := api.ApiStatus{Code: 0x8f05, Wide: 0x80000000ffffffff}
	var g api.ApiG
	values := []float64{0.1, -2.5e-5, 1e-4, 123456, 1234567, 1e300,
		math.Copysign(0, -1), 0.5, 99999.95, math.Inf(1), math.Inf(-1)}
	copy(g.D[:], values)
	g.F = [3]float32{0.1, 1e-7, 3.4e38}

	C.print_all(unsafe.Pointer(&v), unsafe.Pointer(&u), unsafe.Pointer(&s),
		unsafe.Pointer(&g))
	fmt.Print("===\n")
	for _, flags := range []int{api.API_PR_YAML, api.API_PR_JSON} {
		for _, fpr := range []func(w *os.File, flags int) error{
			func(w *os.File, flags int) error { return v.Fpr(w, flags) },
			func(w *os.File, flags int) error { return u.Fpr(w, flags) },
			func(w *os.File, flags int) error { return s.Fpr(w, flags) },
			func(w *os.File, flags int) error { return g.Fpr(w, flags) },
			func(w *os.File, flags int) error { return (*api.ApiV)(nil).Fpr(w, flags) },
		} {
			if err := fpr(os.Stdout, flags); err != nil {
				panic(err)
			}
		}
	}
	for _, e := range []api.ApiE{-1, 2, 3} {
		name, ok := e.Name()
		if !ok {
			name = "UNKNOWN"
		}
		fmt.Println(name)
	}
	fmt.Print("===\n")
	fmt.Print(v)
	fmt.Print(s)
}
"""


def test_values_print_as_the_c_printers_print_them(parse, tmp_path):
    model, _ = parse(VALUES)
    assert process(model, ["capi", "go"], tmp_path) == []

    project = tmp_path / "user"
    project.mkdir()
    (project / "go.mod").write_text(
        f"module user\n\ngo {GO_VERSION}\n\nrequire api v0.0.0\n\n"
        f"replace api => {tmp_path / 'go'}\n"
    )
    (project / "main.go").write_text(VALUES_GO)
    (project / "print.c").write_text(VALUES_C)
    for name in ("libapi.h", "api_pp.c"):
        (project / name).write_text((tmp_path / "capi" / name).read_text())
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOTOOLCHAIN": "local"}
    binary = tmp_path / "user.bin"
    build = subprocess.run(
        ["go", "build", "-buildvcs=false", "-tags", "api_no_link"]
        + ["-o", str(binary), "."],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )
    assert build.returncode == 0, build.stderr
    out = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
    c_out, go_out, strings = out.stdout.split("===\n")

    assert '"say \\"hi\\"\\u0009\\\\ \\u007f é"' in c_out
    assert "code: {val: 0x8f05, type: 0x5, delay: 0xf, dnr: 0x1}" in c_out
    assert "high: -23" in c_out or "high: 233" in c_out
    assert go_out == c_out
    v_yaml = c_out[c_out.index("api_v:") : c_out.index("api_u:")]
    s_yaml = c_out[c_out.index("api_status:") : c_out.index("api_g:")]
    assert strings == v_yaml + s_yaml  # String() is the YAML


# A union whose members are an array, a string and a field of bits
UNION = (
    BITS + BITS_UNION + "/** W */\nunion api_w { uint32_t words[2]; char name[8]; };\n"
)


@pytest.mark.parametrize("header", ["valid", "bits", "skipped", "hidden", "union"])
def test_the_package_is_formatted_as_gofmt_formats_it(parse, parser, tmp_path, header):
    if header == "valid":
        model, _ = parser.parse(HEADERS / "valid.h")
    else:
        headers = {"bits": BITS, "skipped": SKIPPED, "hidden": HIDDEN}
        model, _ = parse({**headers, "union": UNION}[header])
    assert process(model, ["go"], tmp_path) == []

    gofmt = subprocess.run(
        ["gofmt", "-l", str(tmp_path / "go")], capture_output=True, text=True
    )
    assert gofmt.returncode == 0, gofmt.stderr
    assert gofmt.stdout == ""


def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["go"], tmp_path)
    assert failures and "building the check failed" in failures[0]
    assert "unsafe.Sizeof(valid.ValidPoint{}) ^ 12" in failures[0]


def test_an_offset_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").fields[1].offset = 40

    failures = process(model, ["go"], tmp_path)
    assert failures and "building the check failed" in failures[0]
    assert "unsafe.Offsetof(valid.ValidPoint{}.Y) ^ 5" in failures[0]


def test_a_prefix_naming_a_package_of_the_standard_library_fails(parser, tmp_path):
    header = tmp_path / "sort.h"
    header.write_text("/** P */\nstruct sort_p { int x; };\n")
    model, _ = parser.parse(header, {"name": "libsort", "prefix": "sort"})

    assert process(model, ["go"], tmp_path) == [
        "go: the module 'sort', named as the prefix, is a package of Go's standard"
        " library, so an import of it is ambiguous"
    ]


def test_a_goroot_without_sources_is_a_failure_not_a_crash(
    parser, tmp_path, monkeypatch
):
    monkeypatch.setenv("GOROOT", str(tmp_path / "no-such-goroot"))
    monkeypatch.chdir(tmp_path)
    model, _ = parser.parse(HEADERS / "valid.h")

    failures = process(model, ["go"], tmp_path / "out")
    assert failures and "GOROOT" in failures[0]


def test_a_pointer_to_an_array_of_no_length_is_not_bound(parse, tmp_path):
    model, _ = parse(doc("F") + "int api_f(int (*p)[]);\n")
    assert process(model, ["go"], tmp_path) == []

    source = (tmp_path / "go" / "api.go").read_text()
    assert "a pointer to an array of no length, which cgo cannot type" in source
    assert "func Api_f(" not in source


@needs_cc
def test_pointers_to_arrays_are_given_as_such(parse, tmp_path):
    header = (
        doc("F")
        + "int api_f(int (*p)[4]);\n"
        + doc("G")
        + "int api_g(int p[4], int n);\n"
        + doc("Arr")
        + "typedef int api_arr[4];\n"
        + doc("H")
        + "int api_h(api_arr a);\n"
        + doc("Rec")
        + "struct api_rec { api_arr a; int (*pa)[4]; };\n"
    )
    model, _ = parse(header)
    assert process(model, ["go"], tmp_path) == []

    impl = header + (
        "int api_f(int (*p)[4]) { return (*p)[3]; }\n"
        "int api_g(int p[4], int n) { return p[n]; }\n"
        "int api_h(api_arr a) { return a[1]; }\n"
    )
    main = program(
        "\tarr := [4]int32{1, 2, 3, 4}\n"
        "\trec := api.ApiRec{Pa: &arr}\n"
        "\tfmt.Println(api.Api_f(&arr), api.Api_g(&arr[0], 2), api.Api_h(&arr[0]),"
        " rec.Pa[0])\n"
    )
    assert run_go(tmp_path, main, impl, strict=True) == "4 3 2 1\n"


def test_emitting_is_deterministic(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    first = [p.read_bytes() for p in Go(tmp_path / "a").emit(model)]
    second = [p.read_bytes() for p in Go(tmp_path / "b").emit(model)]
    assert first == second


def test_no_toolchain_is_a_failure_not_a_crash(parser, tmp_path, monkeypatch):
    monkeypatch.setenv("GO", "no-such-go")
    model, _ = parser.parse(HEADERS / "valid.h")

    assert process(model, ["go"], tmp_path) == [
        "go: no Go toolchain ('no-such-go'); set GO"
    ]


def test_string_defines_keep_their_value(parse, tmp_path):
    # A package named in a string is not one the package uses
    model, _ = parse(ESCAPED + '/** P */\n#define API_P "strconv.Itoa cgo.Handle"\n')
    assert process(model, ["go"], tmp_path) == []

    main = program("\tfmt.Print(api.API_S)\n")
    assert run_go(tmp_path, main) == ESCAPED_VALUE


def test_enums_are_integers_with_names(parse, tmp_path):
    model, _ = parse(
        "/** Kinds */\nenum api_kind { API_A = 1, API_B = 2, API_ALSO_B = 2 };\n"
    )
    assert process(model, ["go"], tmp_path) == []

    main = program(
        "\tname, ok := api.ApiKind(7).Name()\n"
        '\tfmt.Println(api.ApiKind(2), api.API_A, api.ApiKind(7), name == "", ok)\n'
    )
    assert run_go(tmp_path, main) == "API_B API_A ApiKind(7) true false\n"


def test_names_are_made_usable(parse, tmp_path):
    model, _ = parse(
        "struct foo_bar { int type; int self; int Type; };\n"
        "struct foo__bar { int x; };\n"
        "int api_r(int func, int len, int unsafe, int Foo_bar);\n"
        "int range(int x);\n"
        "typedef int type;\nint api_t(type x);\n"
        "enum kind { lower = 1 };\n"
        "typedef unsigned api_u32;\n"
        "struct _hidden { int x; };\n"
        "int _hidden_f(int _);\n"
    )
    assert process(model, ["go"], tmp_path) == []

    module = (tmp_path / "go" / "api.go").read_text()
    assert "type Foo_bar struct {" in module and "type Foo__bar struct {" in module
    assert "\tType  int32\n\tSelf  int32\n\tType_ int32\n" in module
    assert (
        "func Api_r(func_ int32, len_ int32, unsafe_ int32, Foo_bar_ int32) int32 {"
        in module
    )
    assert "// Range is not bound: range() is named as a Go keyword" in module
    assert "// Api_t is not bound: api_t() uses the typedef 'type'" in module
    assert "Lower Kind = 1" in module
    assert "type ApiU32 = uint32" in module
    assert "type Hidden struct {" in module
    assert "func X_hidden_f(arg0 int32) int32 {" in module


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["go"], tmp_path) == []


def test_what_cgo_cannot_call_is_not_bound_and_says_so(parse, tmp_path):
    model, _ = parse(
        doc("Log")
        + "int api_log(const char *fmt, ...);\n"
        + "struct api_x;\n"
        + doc("Take")
        + "int api_take(struct api_x x);\n"
    )
    assert process(model, ["go"], tmp_path) == []

    module = (tmp_path / "go" / "api.go").read_text()
    assert "// Api_log is not bound: api_log() is variadic, which cgo cannot call." in (
        module
    )
    assert "func Api_log(" not in module
    assert "// Api_take is not bound: api_take() takes or returns a ApiX" in module


def test_a_struct_ending_in_a_flexible_array_has_its_layout(parse, tmp_path):
    model, _ = parse(
        "#include <stdint.h>\n"
        + doc("Message")
        + "struct api_msg { uint8_t len; uint64_t data[]; };\n"
    )
    assert process(model, ["go"], tmp_path) == []

    module = (tmp_path / "go" / "api.go").read_text()
    assert "// 'data', a flexible array, follows it in memory: Go" in module


@needs_cc
def test_raw_functions_call_c(parse, tmp_path):
    header = (
        "#include <stddef.h>\n#include <stdint.h>\n"
        + doc("P")
        + "struct api_p { int32_t x; int32_t y; };\n"
        + doc("Sum")
        + "long api_sum(const struct api_p *p, size_t n, char *name);\n"
        + doc("Get")
        + "struct api_p *api_get(void);\n"
        + doc("Swap")
        + "struct api_p api_swap(struct api_p p);\n"
    )
    model, _ = parse(header)
    assert process(model, ["go"], tmp_path) == []

    impl = header + (
        "long api_sum(const struct api_p *p, size_t n, char *name)\n"
        "{\n\tlong s = 0;\n\tfor (size_t i = 0; i < n; i++) s += p[i].x * p[i].y;\n"
        "\tname[0] = 'S';\n\treturn s;\n}\n"
        "static struct api_p one = { 7, 8 };\n"
        "struct api_p *api_get(void) { return &one; }\n"
        "struct api_p api_swap(struct api_p p)"
        " { struct api_p q = { p.y, p.x }; return q; }\n"
    )
    main = program(
        "\tps := []api.ApiP{{X: 1, Y: 2}, {X: 3, Y: 4}}\n"
        '\tname := []byte("s\\x00")\n'
        "\tsum := api.Api_sum(&ps[0], uintptr(len(ps)), &name[0])\n"
        "\tfmt.Println(sum, string(name[:1]), *api.Api_get(),"
        " api.Api_swap(api.ApiP{X: 1, Y: 2}).X)\n"
    )
    assert run_go(tmp_path, main, impl, strict=True) == (
        "14 S api_p:\n  x: 7\n  y: 8\n 2\n"
    )


def test_unions_are_read_and_written_through_their_members(parse, tmp_path):
    model, _ = parse(
        "#include <stdint.h>\n"
        + doc("Point")
        + "struct api_p { int16_t x; int16_t y; };\n"
        + doc("Either")
        + "union api_u { uint32_t u; int32_t i; struct api_p p; uint8_t b[4]; };\n"
    )
    assert process(model, ["go"], tmp_path) == []

    main = program(
        "\tvar u api.ApiU\n\t*u.I() = -1\n\tu.P().X = 0\n"
        '\tfmt.Printf("%#x %d %d\\n", *u.U(), u.P().Y, u.B()[3])\n'
    )
    assert run_go(tmp_path, main) == "0xffff0000 -1 255\n"


def test_a_field_of_bits_prints_its_parts(parse, tmp_path):
    model, _ = parse(BITS)
    assert process(model, ["go"], tmp_path) == []

    main = program(
        "\ts := api.ApiStatus{Code: 0x8a05, Wide: 0x8000000100000002}\n"
        "\tfmt.Print(s)\n"
        "\tif err := s.Fpr(os.Stdout, api.API_PR_JSON); err != nil {\n"
        "\t\tpanic(err)\n\t}\n",
        imports=("fmt", "os"),
    )
    assert run_go(tmp_path, main) == BITS_PRINTED


def test_the_parts_of_a_field_of_bits_are_methods(parse, tmp_path):
    model, _ = parse(
        BITS + BITS_UNION + "/** C */\nstruct api_c {\n"
        "\tuint8_t status; ///< Status, see API_C_STATUS_*\n"
        "\tuint8_t StatusFlags; ///< Named as a getter in Go\n};\n"
        "/** Flags; bits 7:6 of 'status' */\n#define API_C_STATUS_FLAGS 0xc0\n"
    )
    assert process(model, ["go"], tmp_path) == []

    main = program(
        "\ts := api.ApiStatus{Code: 0x8a05, Wide: 0x8000000100000002}\n"
        "\tfmt.Println(s.CodeType(), s.CodeDelay(), s.CodeDnr(), s.WideLow(),"
        " s.WideTop())\n"
        "\ts.SetCodeDelay(3)\n\ts.SetCodeDnr(0)\n"
        "\ts.SetWideTop(0)\n\ts.SetWideLow(0xffffffff)\n"
        '\tfmt.Printf("%#x %#x\\n", s.Code, s.Wide)\n'
        "\tvar u api.ApiU\n\tu.SetTypeHi(0xabcd)\n"
        '\tfmt.Printf("%#x %#x\\n", *u.Type(), u.TypeHi())\n'
        "\tvar c api.ApiC\n\tc.SetStatusFlags(2)\n"
        '\tfmt.Printf("%#x %d %d\\n", c.Status, c.StatusFlags_(), c.StatusFlags)\n'
        "\tdefer func() { fmt.Println(recover()) }()\n"
        "\ts.SetCodeDelay(16)\n"
    )
    assert run_go(tmp_path, main) == (
        "5 10 1 2 1\n0x305 0x1ffffffff\n0xabcd0000 0xabcd\n0x80 2 0\n"
        "ApiStatus.SetCodeDelay: 16 does not fit\n"
    )


def test_the_idiomatic_layer_builds_for_every_kind_of_parameter(parse, tmp_path):
    model, _ = parse(EDGES)
    assert process(model, ["go"], tmp_path) == []

    module = (tmp_path / "go" / "api.go").read_text()
    assert "type ApiCbFunc func(p *ApiP, n int32) int32" in module
    assert "func Open(name *string) (*H, error) {" in module
    assert "func (h *H) Each(cb ApiCbFunc) (int, error) {" in module
    assert "func (h *H) Submit(cb ApiCbFunc) error {" in module
    assert "// C keeps 'cb' until it has been called, once." in module
    assert "// C keeps 'cb' until the handle is destroyed." in module
    assert "func (h *H) Inline(fn unsafe.Pointer, ctx unsafe.Pointer) error {" in module
    assert "func (h *H) Step(pos *uintptr) (int32, error) {" in module
    assert "func (h *H) Raw(p *ApiP, opaque unsafe.Pointer) int32 {" in module
    assert "func (h *H) Other() *ApiH {" in module
    assert "func (h *H) Close() error {" in module
    assert "func Base(path string) string {" in module


@needs_cc
def test_shared_counts_handles_given_and_constructors_without_errno(parse, tmp_path):
    model, _ = parse(MORE)
    assert process(model, ["go"], tmp_path) == []

    module = (tmp_path / "go" / "api.go").read_text()
    assert "func Make() *H {" in module
    assert "if len(b) != len(a) {" in module
    assert "if len(in) != len(out) {" in module

    main = program(
        "\th, err := api.Open()\n\tif err != nil {\n\t\tpanic(err)\n\t}\n"
        "\tdefer h.Close()\n"
        "\tif err := h.Copy(api.Make()); err != nil {\n\t\tpanic(err)\n\t}\n"
        "\ta := []int32{1, 2}\n\tb := []int32{3, 4}\n"
        "\tmapped, err := api.Map(a, make([]int32, 2))\n"
        "\tif err != nil {\n\t\tpanic(err)\n\t}\n"
        "\tlabel, _ := h.Label()\n"
        "\tfmt.Println(api.Dot(a, b), mapped[1], *label)\n"
        "\tdefer func() { fmt.Println(recover()) }()\n"
        "\tapi.Dot(a, b[:1])\n"
    )
    assert run_go(tmp_path, main, MORE + MORE_C) == (
        "11 4 108\napi_dot: 'b' does not have the count 'n'\n"
    )


@needs_cc
def test_bytes_out_arrays_sharing_a_count_and_clones(parse, tmp_path):
    header = IO + doc("Get", "@param[out] retval R") + "void api_get(int *retval);\n"
    model, _ = parse(header)
    assert process(model, ["go"], tmp_path) == []

    main = program(
        "\tread, err := api.Read(make([]byte, 8))\n"
        "\tif err != nil {\n\t\tpanic(err)\n\t}\n"
        "\th, _ := api.Open()\n\tclone, _ := h.Clone()\n"
        "\ta, b := api.Pair(make([]int32, 3), make([]int32, 3))\n"
        "\tv := []int32{1, 2}\n\tapi.Twice(v)\n"
        '\tfmt.Println(api.Write([]byte("abcd")), string(read), api.Get(),'
        " clone.Ptr() == h.Ptr(), a[2], b[2], v)\n"
        "\tfmt.Println(h.Close(), clone.Close(), api.Use(1, nil))\n"
    )
    impl = header + IO_C + "void api_get(int *retval) { *retval = 42; }\n"
    assert run_go(tmp_path, main, impl) == (
        "4 xyz 42 false 2 20 [2 4]\n<nil> api_close: input/output error -1\n"
    )


@needs_cc
def test_closures_are_kept_as_long_as_their_lifetime_says(parse, tmp_path):
    model, _ = parse(KEPT)
    assert process(model, ["go"], tmp_path) == []

    main = program(
        "\tsum := int32(0)\n"
        "\th, err := api.Open()\n\tif err != nil {\n\t\tpanic(err)\n\t}\n"
        "\tdefer h.Close()\n"
        "\tadd := func(v int32) int32 {\n\t\tsum += v\n\t\treturn 0\n\t}\n"
        "\tif err := h.On(add); err != nil {\n\t\tpanic(err)\n\t}\n"
        "\ttaken := h.On(add)\n"
        "\tif err := h.Submit(nil); err != nil {\n\t\tpanic(err)\n\t}\n"
        "\tif err := h.Submit(func(v int32) int32 {\n"
        "\t\tsum += 100 * v\n\t\treturn 0\n\t}); err != nil {\n\t\tpanic(err)\n\t}\n"
        "\tbusy := h.Submit(add)\n"
        "\tn, err := h.Poke()\n\tif err != nil {\n\t\tpanic(err)\n\t}\n"
        "\tif err := h.Fire(5); err != nil {\n\t\tpanic(err)\n\t}\n"
        "\tfmt.Println(errors.Is(taken, syscall.EBUSY),\n"
        '\t\tbusy.Error() == "api_submit: "+syscall.EBUSY.Error(), n, sum)\n',
        imports=("errors", "fmt", "syscall"),
    )
    assert run_go(tmp_path, main, KEPT + KEPT_C, strict=True) == "true true 1 705\n"


@needs_cc
def test_a_string_with_a_count_is_counted_from_the_string(parse, tmp_path):
    header = (
        "#include <stddef.h>\n"
        + doc("Write", "@nullable buf", "@len buf n")
        + "int api_write(const char *buf, size_t n);\n"
        + doc("Put", "@len buf n")
        + "int api_put(const char *buf, size_t n);\n"
    )
    model, _ = parse(header)
    assert process(model, ["go"], tmp_path) == []

    impl = header + (
        "int api_write(const char *buf, size_t n) { return buf ? (int)n : -1; }\n"
        "int api_put(const char *buf, size_t n) { return buf[n - 1]; }\n"
    )
    main = program(
        '\ttext := "abc"\n'
        '\tfmt.Println(api.Write(&text), api.Write(nil), api.Put("hello"))\n'
    )
    assert run_go(tmp_path, main, impl, strict=True) == "3 -1 111\n"


@needs_cc
def test_nullable_slices_strings_to_callbacks_and_names_of_the_layer(parse, tmp_path):
    header = (
        "#include <stddef.h>\ntypedef void (*api_seen_cb)(void *arg, const char *s);\n"
        + doc("Ret")
        + "int api_ret(int ret, int ret_val);\n"
        + doc("Sum", "@nullable v", "@len v n")
        + "int api_sum(const int *v, size_t n);\n"
        + doc("Seen", "@lifetime cb call")
        + "void api_seen(api_seen_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["go"], tmp_path) == []

    impl = header + (
        "int api_ret(int ret, int ret_val) { return ret - ret_val; }\n"
        "int api_sum(const int *v, size_t n)\n"
        "{\n\tint s = 0;\n\tif (!v) return -1;\n"
        "\tfor (size_t i = 0; i < n; i++) s += v[i];\n\treturn s;\n}\n"
        'void api_seen(api_seen_cb cb, void *arg) { cb(arg, "hi"); }\n'
    )
    main = program(
        '\tseen := ""\n\tapi.Seen(func(s string) { seen = s })\n'
        "\tfmt.Println(api.Ret(5, 3), api.Sum([]int32{1, 2, 3}), api.Sum(nil), seen)\n"
    )
    assert run_go(tmp_path, main, impl, strict=True) == "2 6 -1 hi\n"


def test_names_of_the_layer_are_made_distinct(parse, tmp_path):
    model, _ = parse(
        HANDLE_NAMED_AS_PREFIX + SHARED + doc("Ptr") + "int api_ptr(struct api *h);\n"
    )
    assert process(model, ["go"], tmp_path) == []

    module = (tmp_path / "go" / "api.go").read_text()
    assert "type ApiHandle struct {" in module
    assert "func (h *ApiHandle) Ptr_() int32 {" in module
    assert "func ApiBar(x int32) int32 {" in module and "func Bar_(x int32)" in module


def test_parameters_named_as_locals_of_the_layer_build(parse, tmp_path):
    model, _ = parse(NAMES)
    assert process(model, ["go"], tmp_path) == []


def test_parameters_named_as_what_the_body_uses_build(parse, tmp_path):
    model, _ = parse(HIDDEN)
    assert process(model, ["go"], tmp_path) == []


def test_a_call_without_an_idiomatic_form_says_so(parse, tmp_path):
    model, _ = parse(
        doc("R")
        + "struct api_r { int x; };\n"
        + doc("Now", "@param[out] tv T")
        + "void api_now(struct api_r *tv);\n"
    )
    model.find("api_r").fields = []  # as for a record defined elsewhere
    assert process(model, ["go"], tmp_path) == []

    module = (tmp_path / "go" / "api.go").read_text()
    assert (
        "// api_now() has no idiomatic form, as what api_now() writes has no"
        " fields to return; see Api_now." in module
    )


def test_a_packed_record_is_its_bytes_read_and_written_by_methods(parse, tmp_path):
    model, _ = parse(
        PACKED + "/** Q */\nstruct __attribute__((packed)) api_q {\n"
        "\tuint8_t t; ///< T\n\tstruct api_k many[2]; ///< Many\n};\n"
    )
    assert process(model, ["go"], tmp_path) == []

    out = run_go(
        tmp_path,
        program(
            "\tvar k api.ApiK\n\tk.SetTag(1)\n\tk.SetValue(0xdeadbeef)\n"
            "\tk.SetAt(api.ApiP{X: -2, Y: 3})\n"
            "\tk.SetPath([2]api.ApiP{{X: 4, Y: 5}, {X: 6, Y: 7}})\n"
            "\tk.SetPair([2]uint16{8, 9})\n\tk.SetType(0x10)\n\tk.SetTypeLow(0xa)\n"
            "\tk.Fpr(os.Stdout, api.API_PR_YAML)\n\tk.Fpr(os.Stdout, api.API_PR_JSON)\n"
            "\tvar u api.ApiKu\n\tu.SetP(api.ApiP{X: 1, Y: 2})\n"
            "\tfmt.Println(k.At().Y, k.TypeLow(), u.N() == 1|2<<32, unsafe.Sizeof(k),"
            " unsafe.Alignof(u))\n"
            "\tvar q api.ApiQ\n\tq.SetMany([2]api.ApiK{1: k})\n"
            "\tfmt.Println(q.Many()[1].At().X, q.Many()[1].TypeLow())\n",
            ("fmt", "os", "unsafe"),
        ),
        strict=True,
    )
    assert out == PACKED_PRINTED + "3 10 true 35 1\n-2 10\n"
