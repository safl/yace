# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import functools
import os
import re
import subprocess
import sys

import pytest

from tests.conftest import (
    BITS,
    ERRMSG,
    ERRMSG_C,
    HEADERS,
    PACKED,
    PACKED_C,
    PACKED_PRINTED,
    SKIPPED,
    flat,
    needs_cc,
)
from tests.test_rust import BITS_UNION, EDGES, HANDLE_NAMED_AS_PREFIX
from yace import compiler
from yace.compiler import process
from yace.targets.cpp.target import CPP, CXXFLAGS, cxxflags

pytestmark = needs_cc


@pytest.fixture(autouse=True, params=CPP.OPTIONS["std"])
def std(request, monkeypatch):
    """Run every test of this module once for each C++ standard that the layer
    is generated for: process() generates the layer for the standard, and
    CXXFLAGS compiles the programs of the tests as the standard"""

    this = sys.modules[__name__]
    options = {"cpp": {"std": request.param}}
    monkeypatch.setattr(
        this, "process", functools.partial(compiler.process, options=options)
    )
    monkeypatch.setattr(this, "CXXFLAGS", cxxflags(request.param))
    return request.param


def test_the_subset_prints_as_the_c_api_does(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["capi"], tmp_path / "c") == []
    assert process(model, ["cpp"], tmp_path / "cpp") == []

    for fmt in ("yaml", "json"):
        c_out = (tmp_path / "c" / "capi" / f"check.{fmt}").read_text()
        assert (tmp_path / "cpp" / "cpp" / f"check.{fmt}").read_text() == c_out


# VALUES declares a record with a field of every kind the printers print, a
# union, and the record of bit-fields of BITS
VALUES = (
    "#include <stdbool.h>\n#include <stddef.h>\n#include <stdint.h>\n"
    "/** E */\nenum api_e { API_E_A = -1, API_E_B = 2, API_E_C = 2 };\n"
    "/** P */\nstruct api_p { int32_t x; int32_t y; };\n"
    "/** Called */\ntypedef void (*api_cb)(void *arg);\n"
    "/** V */\nstruct api_v {\n"
    "\tbool flag; char letter; signed char sc; unsigned char uc;\n"
    "\tint64_t i64; uint64_t u64; size_t size; float f; double d; enum api_e e;\n"
    "\tconst char *label; const char *none; char name[4]; char full[4];\n"
    "\tvoid *ptr; void *nil; api_cb cb; struct api_p at; struct api_p path[2];\n"
    "\tint16_t grid[2][2]; unsigned int bits : 4; unsigned int : 4;\n"
    "\tunsigned int more : 8;\n};\n"
    "/** U */\nunion api_u { uint32_t u; struct api_p p; };\n"
) + BITS

VALUES_MAIN = r"""#include <cstdio>
#include <cstring>
#include <iostream>
#include <api.hpp>
static void cb(void *) {}
int main() {
	struct api_v v{};
	v.flag = true; v.letter = 'y'; v.sc = -2; v.uc = 250;
	v.i64 = INT64_MIN; v.u64 = UINT64_MAX; v.size = 11; v.f = 0.1f; v.d = -2.5e-5;
	v.e = API_E_A; v.label = "say \"hi\"\t\\ \x7f \xc3\xa9"; v.none = nullptr;
	std::memcpy(v.name, "ab", 3); std::memcpy(v.full, "abcd", 4);
	v.ptr = &v; v.cb = cb; v.at = {-1, 2}; v.path[1] = {3, 4}; v.grid[0][1] = -5;
	v.bits = 9; v.more = 200;
	union api_u u{};
	u.u = 0xffffffff;
	struct api_status s{};
	s.code = 0x8f05; s.wide = 0x80000000ffffffffu;
	for (int flags : {API_PR_YAML, API_PR_JSON}) {
		api_v_fpr(stdout, &v, flags);
		api_u_fpr(stdout, &u, flags);
		api_status_fpr(stdout, &s, flags);
	}
	for (int e : {-1, 2, 3}) {
		std::printf("%s\n", api_e_str(e));
	}
	std::fflush(stdout);
	std::cout << "===\n";
	std::cout << api::yaml(v) << api::yaml(u) << api::yaml(s);
	std::cout << api::json(v) << api::json(u) << api::json(s);
	for (int e : {-1, 2, 3}) {
		std::cout << api::name(static_cast<api::e>(e)).value_or("UNKNOWN") << "\n";
	}
	return 0;
}
"""


def test_values_print_as_the_c_printers_print_them(parse, tmp_path):
    model, _ = parse(VALUES)
    assert process(model, ["cpp"], tmp_path) == []

    (tmp_path / "main.cpp").write_text(VALUES_MAIN)
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    pp = str(tmp_path / "pp.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "capi" / "api_pp.c"), "-o", pp],
        check=True,
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), pp]
        + ["-o", str(program)],
        check=True,
    )
    out = subprocess.run([str(program)], capture_output=True, text=True, check=True)
    c_out, cpp_out = out.stdout.split("===\n")

    assert '"say \\"hi\\"\\u0009\\\\ \\u007f é"' in c_out
    assert "code: {val: 0x8f05, type: 0x5, delay: 0xf, dnr: 0x1}" in c_out
    assert cpp_out == c_out


def test_the_layer_builds_for_every_kind_of_parameter(parse, tmp_path):
    model, _ = parse(EDGES)
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    # A constructor is a function of the namespace, not a member of the class
    assert "\th open(" not in hpp
    assert "inline h\nopen(const char *name)" in hpp
    assert "std::size_t each(F &&cb);" in flat(hpp)
    assert "std::size_t each(std::nullptr_t);" in flat(hpp)
    assert "int step(size_t &pos);" in flat(hpp)
    assert "void inline_(int (*fn)(void *ctx), void *ctx);" in flat(hpp)
    assert "void close();" in flat(hpp)


def test_a_handle_named_as_the_prefix_builds(parse, tmp_path):
    model, _ = parse(HANDLE_NAMED_AS_PREFIX)
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    assert "namespace api_cpp {" in hpp and "class api_handle {" in hpp


def test_names_that_are_keywords_are_usable(parse, tmp_path):
    model, _ = parse(
        "/** Kinds */\nenum api_kind { API_KIND_DEFAULT = 1, API_KIND_NEW = 2 };\n"
        "/** A record */\nstruct api_class { int x; };\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    assert "default_ = ::API_KIND_DEFAULT," in hpp
    assert "using class_ = struct ::api_class;" in hpp


def test_closing_twice_calls_c_once(parse, tmp_path):
    header = (
        "struct api_h;\n"
        "/**\n * Open\n * @param[out] h H\n * @errno\n */\n"
        "int api_open(struct api_h **h);\n"
        "/// Close, which a comment's end, */, does not end\n/// @errno\n"
        "/// @destroys h\nint api_close(struct api_h *h);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cpp"], tmp_path) == []

    (tmp_path / "api.c").write_text(
        header + "#include <stdlib.h>\nstatic int opened;\n"
        "int api_open(struct api_h **h) { *h = (struct api_h *)&opened; return 0; }\n"
        "int api_close(struct api_h *h) { if (!h) abort(); return 0; }\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <utility>\n#include <api.hpp>\nint main() {\n"
        "\tauto a = api::open();\n\ta.close();\n\ta.close();\n"
        "\tauto b = api::open();\n\tauto c = std::move(b);\n\tb.close();\n"
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    assert subprocess.run([str(program)]).returncode == 0


def test_shared_counts_handles_as_arguments_and_constructors_without_errno_work(
    parse, tmp_path
):
    from tests.test_rust import MORE, MORE_C

    model, _ = parse(MORE)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(MORE + MORE_C)
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <stdexcept>\n#include <vector>\n"
        "#include <api.hpp>\nint main() {\n"
        "\tauto h = api::open();\n\tauto m = api::make();\n\th.copy(*m);\n"
        "\tstd::vector<int> a = {1, 2}, b = {3, 4}, c = {1}, o(2);\n"
        "\tint thrown = 0;\n"
        "\ttry {\n\t\tapi::dot(a, c);\n\t} catch (const std::invalid_argument &) {\n"
        "\t\tthrown += 1;\n\t}\n"
        "\ttry {\n\t\tapi::map(c, o);\n\t} catch (const std::invalid_argument &) {\n"
        "\t\tthrown += 1;\n\t}\n"
        '\tstd::printf("%ld %d %d %s\\n", api::dot(a, b), api::map(a, o)[1], thrown,'
        " h.label());\n"
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "11 4 2 lbl\n"


def test_a_record_named_as_a_function_and_a_method_named_get_build(parse, tmp_path):
    model, _ = parse(
        "struct api_h;\n"
        "/**\n * Open\n * @param[out] h H\n * @errno\n */\n"
        "int api_open(struct api_h **h);\n"
        "/**\n * Get\n */\nint api_h_get(const struct api_h *h);\n"
        "/** V */\nstruct api_version {\n\tint major; ///< M\n};\n"
        "/** Version */\nconst char *api_version(void);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    assert "int get() const;" in flat(hpp) and "using version =" not in hpp


def test_an_out_count_bounds_the_result_and_the_error_holds_what_was_written(
    parse, tmp_path
):
    from tests.test_rust import REAP, REAP_C

    model, _ = parse(REAP)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(REAP + REAP_C)
    (tmp_path / "main.cpp").write_text(
        "#include <cerrno>\n#include <cstdio>\n#include <api.hpp>\nint main() {\n"
        "\tstd::vector<int32_t> buf(4);\n"
        "\tauto done = api::reap(0, buf);\n"
        "\ttry {\n\t\tapi::reap(EAGAIN, {buf.data(), 2});\n"
        "\t} catch (const api::partial_error<decltype(done)> &e) {\n"
        '\t\tstd::printf("%zu %d %d %zu %d\\n", done.size(), done[2],\n'
        "\t\t\t    e.code().value() == EAGAIN, e.value.size(), e.value[1]);\n"
        "\t}\n\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "3 20 1 2 10\n"


def test_a_recparam_record_is_passed_with_its_size_by_the_c_name(parse, tmp_path):
    from tests.test_rust import SIZED, SIZED_C

    model, _ = parse(SIZED)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(SIZED + SIZED_C)
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <api.hpp>\nint main() {\n"
        "\tapi::args args{40, 2};\n"
        '\tstd::printf("%ju\\n", static_cast<uintmax_t>(api::prep(args)));\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "42\n"


def test_byte_buffers_two_callbacks_clones_and_an_out_named_retval_work(
    parse, tmp_path
):
    from tests.test_rust import IO, IO_C, doc

    header = (
        IO
        + "typedef int (*api_cb)(void *arg, int v);\n"
        + doc("Run", "@nullable done", "@lifetime progress call done call")
        + "int api_run(api_cb progress, void *parg, api_cb done, void *darg);\n"
        + doc("Get", "@param[out] retval R")
        + "void api_get(int *retval);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + IO_C + "int api_run(api_cb p, void *pa, api_cb d, void *da)\n"
        "{\n\tint r = p(pa, 1);\n\treturn d ? r + d(da, 2) : r;\n}\n"
        "void api_get(int *retval) { *retval = 42; }\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <cstddef>\n#include <cstdio>\n#include <vector>\n"
        "#include <api.hpp>\nint main() {\n"
        "\tstd::vector<std::byte> out(4);\n"
        "\tstd::vector<std::byte> in(8);\n"
        "\tauto read = api::read(in);\n"
        "\tstd::vector<int32_t> a(3), b(3);\n"
        "\tapi::pair(a, b);\n"
        "\tint both = api::run([](int v) { return v; },\n"
        "\t\t\t    [](int v) { return 10 * v; });\n"
        "\tint one = api::run([](int v) { return v; }, nullptr);\n"
        "\tauto h = api::open();\n\tauto copy = h.clone();\n"
        '\tstd::printf("%zu %zu %d %d %d %d %d\\n", api::write(out), read.size(),'
        " b[2], both, one, api::get(), copy.native_handle() != nullptr);\n"
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "4 3 20 21 1 42 1\n"


def test_a_class_returned_before_it_is_defined_builds(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_h;\nstruct api_x;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Spawn", "@param[out] out O", "@errno")
        + "int api_spawn(struct api_h *h, struct api_x **out);\n"
        + doc("Id")
        + "int api_x_id(const struct api_x *x);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []


def test_parameters_named_ret_and_functions_sharing_a_name_build(parse, tmp_path):
    from tests.test_rust import SHARED, doc

    model, _ = parse(SHARED + doc("Echo", "@errno") + "int api_echo(int ret);\n")
    assert process(model, ["cpp"], tmp_path) == []


def test_parameters_named_as_what_the_body_uses_build(parse, tmp_path):
    from tests.test_rust import HIDDEN

    model, _ = parse(HIDDEN)
    assert process(model, ["cpp"], tmp_path) == []


def test_parameters_named_as_locals_of_the_layer_build(parse, tmp_path):
    from tests.test_rust import NAMES

    model, _ = parse(NAMES)
    assert process(model, ["cpp"], tmp_path) == []


def test_a_function_given_by_name_as_a_callback_is_called(parse, tmp_path):
    from tests.test_rust import doc

    header = (
        "typedef int (*api_cb)(void *arg, int v);\n"
        + doc("Run", "@lifetime cb call")
        + "int api_run(api_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "int api_run(api_cb cb, void *arg) { return cb(arg, 21); }\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <api.hpp>\n"
        "static int twice(int v) { return 2 * v; }\n"
        'int main() {\n\tstd::printf("%d %d\\n", api::run(twice),'
        " api::run([](int v) { return v; }));\n\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "42 21\n"


def test_a_function_named_as_a_record_builds(parse, tmp_path):
    model, _ = parse("/** R */\nstruct api_tag;\n/** F */\nint api_tag(int v);\n")
    assert process(model, ["cpp"], tmp_path) == []
    assert (
        "/**\n * F\n */\ninline int\ntag(int v)"
        in (tmp_path / "cpp" / "api.hpp").read_text()
    )


def test_methods_named_as_their_class_or_its_deleter_build(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_h;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Close", "@destroys h")
        + "void api_close(struct api_h *h);\n"
        + doc("H")
        + "int api_h_h(struct api_h *h, int v);\n"
        + doc("Deleter")
        + "int api_h_deleter(struct api_h *h, int v);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []


def test_a_class_named_as_a_c_typedef_it_uses_builds(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_api_cb_fn;\ntypedef int (*api_cb_fn)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_api_cb_fn **h);\n"
        + doc("Visit")
        + "int api_visit(struct api_api_cb_fn *h, api_cb_fn cb, void *arg);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []


def test_names_that_would_hide_c_names_or_namespace_types_are_renamed_or_left_out(
    parse, tmp_path
):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        "/** P */\nstruct pt {\n\tint x; ///< X\n};\n"
        "/** K */\nenum api_kind { API_KIND_A = 1 };\n"
        "/** E */\nenum api_api_cb { API_API_CB_A = 1 };\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Use")
        + "int api_use(const struct pt *p);\n"
        + doc("Cb")
        + "int api_api_cb(int x);\n"
        + doc("Kind")
        + "int api_kind(int x);\n"
        + doc("H")
        + "int api_h(int x);\n"
        + doc("Run", "@lifetime cb call")
        + "int api_run(api_cb cb, void *arg);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    assert "using pt =" not in hpp and "enum class api_cb_" in hpp
    assert "\nkind_(int x)" in hpp and "\nh_(int x)" in hpp


def test_names_the_namespace_declares_or_uses_are_renamed(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_name;\n"
        "/** Y */\nstruct api_yaml {\n\tint x; ///< X\n};\n"
        "/** D */\nstruct api_detail {\n\tint x; ///< X\n};\n"
        "/** S */\nstruct api_std {\n\tint x; ///< X\n};\n"
        "/** E */\nenum api_json { API_JSON_A = 1 };\n"
        "/** J */\nint api_json(const struct api_yaml *y);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_name **h);\n"
        + doc("Get")
        + "const char *api_get(void);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    assert "using yaml_ = struct ::api_yaml;" in hpp and "\njson__(" in hpp
    assert "class name_handle" in hpp and "enum class json_" in hpp


def test_methods_named_as_classes_and_callbacks_as_template_parameters_build(
    parse, tmp_path
):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_h;\nstruct api_q;\n"
        "typedef int (*api_done_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Make", "@param[out] q Q", "@errno")
        + "int api_make(struct api_q **q);\n"
        + doc("Q")
        + "void api_h_q(struct api_h *h, struct api_q *q);\n"
        + doc("Go", "@lifetime cb call")
        + "int api_h_go(struct api_h *h, api_done_cb cb, void *arg);\n"
        + doc("Run", "@lifetime F call")
        + "int api_run(api_done_cb F, void *arg);\n"
        + doc("Walk", "@nullable cb", "@lifetime cb call")
        + "void api_walk(int F, api_done_cb cb, void *arg);\n"
        + "struct api_F;\n"
        + doc("Each", "@lifetime cb call")
        + "int api_h_F(struct api_h *h, api_done_cb cb, void *arg);\n"
        + doc("Start", "@param[out] f F", "@lifetime cb call", "@errno")
        + "int api_start(api_done_cb cb, void *arg, struct api_F **f);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    assert "q_(" in hpp and "class F_" in hpp
    assert "walk(int F_, std::nullptr_t)" in hpp
    (tmp_path / "main.cpp").write_text(
        "#include <api.hpp>\n"
        "void use() { api::F f = api::start([](int v) { return v; }); }\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    subprocess.run(
        ["c++", *CXXFLAGS, *include, "-fsyntax-only", str(tmp_path / "main.cpp")],
        check=True,
    )


def test_a_record_named_as_a_template_parameter_builds(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "typedef int (*api_done_cb)(void *arg, int v);\n"
        "/** R */\nstruct F {\n\tint x; ///< X\n};\n"
        + doc("Use", "@lifetime cb call")
        + "int api_use(const struct F *p, api_done_cb cb, void *arg);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []


def test_kept_callables_are_called_and_released(parse, tmp_path):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(KEPT + KEPT_C)
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <memory>\n#include <system_error>\n"
        "#include <api.hpp>\nint main() {\n"
        "\tauto seen = std::make_shared<int>(0);\n"
        "\tauto h = api::open();\n"
        "\th.on([seen](int v) { *seen += v; return 0; });\n"
        "\th.submit(nullptr);\n"
        "\th.submit([seen](int v) { *seen += 100 * v; return 0; });\n"
        "\tint failed = 0;\n"
        "\ttry {\n\t\th.submit([seen](int v) { *seen += 1000 * v; return 0; });\n"
        "\t} catch (const std::system_error &) {\n\t\tfailed += 1;\n\t}\n"
        "\ttry {\n\t\th.on([seen](int v) { *seen += 10 * v; return 0; });\n"
        "\t} catch (const std::system_error &) {\n\t\tfailed += 1;\n\t}\n"
        '\tstd::printf("%d %ld\\n", failed, seen.use_count());\n'
        '\tstd::printf("%ld\\n", (long)h.poke());\n'
        "\th.fire(5);\n"
        '\tstd::printf("%d %ld\\n", *seen, seen.use_count());\n'
        "\th.close();\n"
        '\tstd::printf("%ld\\n", seen.use_count());\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "2 3\n1\n705 2\n1\n"


def test_a_failed_call_without_a_nullable_callback_frees_the_others(parse, tmp_path):
    from tests.test_rust import doc

    header = (
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Two", "@nullable second", "@lifetime first once second once", "@errno")
        + "int api_two(struct api_h *h, api_cb first, void *farg, api_cb second,"
        " void *sarg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "static int h;\n"
        "int api_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }\n"
        "int api_two(struct api_h *p, api_cb f, void *fa, api_cb s, void *sa)\n"
        "{\n\t(void)p; (void)f; (void)fa; (void)s; (void)sa;\n\treturn -22;\n}\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <memory>\n#include <system_error>\n"
        "#include <api.hpp>\nint main() {\n"
        "\tauto seen = std::make_shared<int>(0);\n"
        "\tauto h = api::open();\n"
        "\ttry {\n\t\th.two([seen](int v) { return v + *seen; }, nullptr);\n"
        "\t} catch (const std::system_error &) {\n\t}\n"
        '\tstd::printf("%ld\\n", seen.use_count());\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "1\n"


def test_callables_kept_by_a_handle_whose_destructor_fails_are_kept(parse, tmp_path):
    from tests.test_rust import doc

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
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "static int h;\n"
        "int api_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }\n"
        "int api_close(struct api_h *p) { (void)p; return -5; }\n"
        "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ (void)p; (void)cb; (void)arg; }\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <memory>\n#include <system_error>\n"
        "#include <api.hpp>\nint main() {\n"
        "\tauto seen = std::make_shared<int>(0);\n"
        "\tauto h = api::open();\n"
        "\th.on([seen](int v) { return v + *seen; });\n"
        "\ttry {\n\t\th.close();\n\t} catch (const std::system_error &) {\n\t}\n"
        "\t{\n\t\tauto g = api::open();\n"
        "\t\tg.on([seen](int v) { return v + *seen; });\n"
        "\t\tauto a = api::open();\n"
        "\t\ta.on([seen](int v) { return v + *seen; });\n"
        "\t\ta = api::open();\n\t}\n"
        '\tstd::printf("%ld\\n", seen.use_count());\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "4\n"


def test_callables_kept_by_a_handle_nothing_destroys_are_kept(parse, tmp_path):
    from tests.test_rust import doc

    header = (
        "/** H */\nstruct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("On", "@lifetime cb handle")
        + "void api_on(struct api_h *h, api_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ (void)p; (void)cb; (void)arg; }\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <memory>\n#include <api.hpp>\n"
        "static int raw;\nint main() {\n"
        "\tauto seen = std::make_shared<int>(0);\n"
        "\t{\n\t\tapi::h h(reinterpret_cast<struct ::api_h *>(&raw));\n"
        "\t\th.on([seen](int v) { return v + *seen; });\n\t}\n"
        '\tstd::printf("%ld\\n", seen.use_count());\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "2\n"


def test_a_handle_moved_over_is_destroyed_before_its_callables(parse, tmp_path):
    from tests.test_rust import doc

    header = (
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Close", "@destroys h")
        + "void api_close(struct api_h *h);\n"
        + doc("On", "@lifetime cb handle")
        + "void api_on(struct api_h *h, api_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "#include <stdlib.h>\n"
        "struct api_h { api_cb cb; void *arg; };\n"
        "int api_open(struct api_h **p) { *p = calloc(1, sizeof **p); return 0; }\n"
        "void api_close(struct api_h *p) { if (p->cb) p->cb(p->arg, 1); free(p); }\n"
        "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ p->cb = cb; p->arg = arg; }\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <memory>\n#include <api.hpp>\nint main() {\n"
        "\tauto seen = std::make_shared<int>(0);\n"
        "\tauto a = api::open();\n"
        "\ta.on([seen](int v) { *seen += v; return 0; });\n"
        "\ta = api::open();\n"
        '\tstd::printf("%d %ld\\n", *seen, seen.use_count());\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, "-fsanitize=address", *include]
        + [str(tmp_path / "main.cpp"), api_o, "-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout == "1 1\n"


def test_a_pointer_to_a_record_of_another_header_is_returned(parser, tmp_path):
    (tmp_path / "other.h").write_text("struct other_doc;\n")
    (tmp_path / "api.h").write_text(
        '#include "other.h"\n/** Open */\nstruct other_doc *api_open(void);\n'
    )
    model, _ = parser.parse(tmp_path / "api.h")
    assert process(model, ["cpp"], tmp_path / "out", include=[tmp_path]) == []
    hpp = (tmp_path / "out" / "cpp" / "api.hpp").read_text()
    assert "return ret;" in hpp


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["cpp"], tmp_path) == []


def test_the_parts_of_a_field_of_bits_are_functions(parse, tmp_path):
    model, _ = parse(
        BITS + BITS_UNION + "/** Named as a part */\nstruct api_code_type { int x; };\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <stdexcept>\n#include <api.hpp>\n"
        "int main() {\n"
        "\tapi::status s = {0x8a05, 0x8000000100000002ULL};\n"
        '\tstd::printf("%u %u %u %llu %llu\\n", (unsigned)api::code_type_(s),'
        " (unsigned)api::code_delay(s), (unsigned)api::code_dnr(s),"
        " (unsigned long long)api::wide_low(s),"
        " (unsigned long long)api::wide_top(s));\n"
        "\tapi::set_code_delay(s, 3);\n\tapi::set_code_dnr(s, 0);\n"
        "\tapi::set_wide_top(s, 0);\n\tapi::set_wide_low(s, 0xffffffffu);\n"
        '\tstd::printf("%#x %#llx\\n", (unsigned)s.code, (unsigned long long)s.wide);\n'
        "\ttry {\n\t\tapi::set_code_delay(s, 16);\n"
        "\t} catch (const std::out_of_range &) {\n"
        '\t\tstd::printf("thrown\\n");\n\t}\n'
        "\tapi::u u = {};\n\tapi::set_type_hi(u, 0xabcd);\n"
        '\tstd::printf("%#x %#x\\n", (unsigned)u.type, (unsigned)api::type_hi(u));\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), "-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == ("5 10 1 2 1\n0x305 0x1ffffffff\nthrown\n0xabcd0000 0xabcd\n")


@needs_cc
def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["cpp"], tmp_path)
    assert failures and "sizeof(valid_point)" in failures[0]


def test_an_offset_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").fields[1].offset = 40

    failures = process(model, ["cpp"], tmp_path)
    assert failures and "offsetof(valid_point, y)" in failures[0]


def test_a_packed_record_prints_through_copies(parse, tmp_path):
    model, _ = parse(PACKED)
    assert process(model, ["cpp"], tmp_path) == []

    # C++17 has no designated initializers
    positional = re.sub(r"\.\w+ = ", "", PACKED_C)
    (tmp_path / "main.cpp").write_text(
        "#include <iostream>\n#include <api.hpp>\n"
        f"int main() {{\n\tapi::k k = {positional};\n"
        "\tapi::set_type_low(k, 0xa);\n"
        "\tstd::cout << api::yaml(k) << api::json(k);\n\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), "-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == PACKED_PRINTED


def test_a_record_the_caller_may_write_is_not_copied(parse, tmp_path):
    from tests.test_rust import POOL, POOL_C

    model, _ = parse(POOL)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(POOL + POOL_C)
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <system_error>\n#include <api.hpp>\n"
        "int main() {\n"
        "\tauto q = api::open();\n"
        "\tstruct ::api_cmd *c = q.get();\n"
        "\tc->opc = 7;\n"
        "\tq.put(*c);\n"
        "\tauto peeked = q.peek();\n"
        "\tstruct ::api_cmd *d = q.get();\n"
        '\tstd::printf("%d %d %d\\n", d == c, d->opc, peeked.opc);\n'
        "\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, "-fsanitize=address", *include]
        + [str(tmp_path / "main.cpp"), api_o, "-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout == "1 7 7\n"


def test_the_layer_names_the_span_of_its_standard(parse, tmp_path, std):
    from tests.test_rust import IO

    model, _ = parse(IO)
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    cc_log = (tmp_path / "cpp" / "cc.log").read_text()
    assert f"-std={std} " in cc_log
    if std == "c++20":
        assert "#include <span>\n" in hpp and "class span" not in hpp
        assert "write(std::span<const std::byte> buf)" in hpp
        assert " * Generated for C++20.\n" in hpp
    else:
        assert "#include <span>" not in hpp and "std::span<" not in hpp
        assert "template <class T> class span {" in hpp
        assert "write(detail::span<const std::byte> buf)" in hpp
        assert " * Generated for C++17 and later.\n" in hpp


def test_the_layer_for_cpp17_builds_as_cpp20_too(parse, tmp_path, std):
    from tests.test_rust import IO

    model, _ = parse(IO)
    assert process(model, ["cpp"], tmp_path) == []
    if std != "c++17":
        pytest.skip("the layer for C++20 needs C++20")

    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    check = str(tmp_path / "cpp" / "api_check.cpp")
    subprocess.run(
        ["c++", *cxxflags("c++20"), *include, "-fsyntax-only", check], check=True
    )


def test_a_span_is_given_as_a_container_an_array_or_a_pointer_and_a_length(
    parse, tmp_path
):
    """The calls of main.cpp compile alike against std::span and against the
    span of the layer for C++17"""

    from tests.test_rust import doc

    header = (
        "#include <stddef.h>\n#include <stdint.h>\n"
        + doc("Sum", "@len v n")
        + "int64_t api_sum(const int32_t *v, size_t n);\n"
        + doc("Fill", "@param[out] v V", "@len v n", "@errno")
        + "int64_t api_fill(int32_t *v, size_t n);\n"
    )
    model, _ = parse(header)
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "int64_t api_sum(const int32_t *v, size_t n)\n"
        "{\n\tint64_t sum = 0;\n\twhile (n--)\n\t\tsum += v[n];\n\treturn sum;\n}\n"
        "int64_t api_fill(int32_t *v, size_t n)\n"
        "{\n\tfor (size_t i = 0; i < n && i < 3; i++)\n\t\tv[i] = (int32_t)i + 1;\n"
        "\treturn n < 3 ? (int64_t)n : 3;\n}\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <array>\n#include <cstdio>\n#include <vector>\n"
        "#include <api.hpp>\nint main() {\n"
        "\tstd::vector<int32_t> vec = {1, 2, 3};\n"
        "\tconst std::vector<int32_t> cvec = {4, 5};\n"
        "\tstd::array<int32_t, 2> arr = {6, 7};\n"
        "\tint32_t raw[4] = {8, 9, 10, 11};\n"
        '\tstd::printf("%ld %ld %ld %ld %ld %ld %ld\\n", (long)api::sum(vec),\n'
        "\t\t    (long)api::sum(cvec), (long)api::sum(arr), (long)api::sum(raw),\n"
        "\t\t    (long)api::sum({raw + 1, 2}), (long)api::sum({}),\n"
        "\t\t    (long)api::sum(std::vector<int32_t>{20, 22}));\n"
        "\tauto filled = api::fill(raw);\n"
        "\tlong sum = 0;\n"
        "\tfor (auto v : filled) {\n\t\tsum += v;\n\t}\n"
        "\tauto part = api::fill({vec.data(), 2});\n"
        '\tstd::printf("%zu %ld %d %d %zu %d %zu %d %zu %d\\n", filled.size(), sum,\n'
        "\t\t    filled[2], filled.empty(), part.size(), part.back(),\n"
        "\t\t    filled.first(2).size(), filled.last(1).front(),\n"
        "\t\t    filled.subspan(1).size(), filled.subspan(1, 1)[0]);\n"
        "\treturn api::sum(filled) == 6 ? 0 : 1;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.returncode == 0
    assert run.stdout == "6 9 13 38 19 0 42\n3 6 3 0 2 2 2 3 2 2\n"


ERRMSG_MAIN = r"""#include <cstdio>
#include <system_error>
#include <vector>
#include <api.hpp>
static void show(const std::system_error &e) {
	std::printf("%d %s\n", e.code().value(), e.what());
}
int main() {
	try {
		api::open("/run/api.sock");
	} catch (const std::system_error &e) {
		show(e);
	}
	try {
		api::quiet();
	} catch (const std::system_error &e) {
		show(e);
	}
	auto h = api::open("name");
	try {
		h.close();
	} catch (const std::system_error &e) {
		show(e);
	}
	std::vector<int32_t> buf(2);
	try {
		api::reap(buf);
	} catch (const api::partial_error<decltype(api::reap(buf))> &e) {
		show(e);
		std::printf("%zu %d\n", e.value.size(), e.value[0]);
	}
	return 0;
}
"""


@pytest.mark.parametrize("named", [True, False])
def test_the_exception_holds_the_message_of_the_function_the_meta_names(
    parse, tmp_path, named
):
    model, diagnostics = parse(ERRMSG, meta={"errmsg": "api_errmsg"} if named else {})
    assert [d for d in diagnostics if d.rule == "meta"] == []
    assert process(model, ["cpp"], tmp_path) == []

    (tmp_path / "api.c").write_text(ERRMSG + ERRMSG_C)
    (tmp_path / "main.cpp").write_text(ERRMSG_MAIN)
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    failed = [
        (2, "api_open", "no socket at /run/api.sock"),
        (5, "api_quiet", ""),
        (16, "api_close", "still in use"),
        (11, "api_reap", "reaped 1 of 3"),
    ]
    # The message, or the text of the errno where there is none, and not both:
    # a library's message may end in the text of the errno, as strerror() gives
    expected = [
        f"{code} {function}: " + (message if named and message else os.strerror(code))
        for code, function, message in failed
    ]
    assert run.stdout.splitlines() == expected + ["1 7"]


def test_the_message_is_read_before_a_callable_is_destroyed(parse, tmp_path):
    """The callable of main.cpp calls api_quiet() when destroyed, which fails
    and clears the message of the library. The layer destroys the callable of a
    call that failed, and the exception holds the message of that call"""

    from tests.test_rust import doc

    header = (
        "struct api_h;\ntypedef void (*api_cb)(void *arg);\n"
        "/** The message of the call that failed last */\n"
        "const char *api_errmsg(void);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Later", "@lifetime cb once", "@errno")
        + "int api_later(api_cb cb, void *arg);\n"
        + doc("On", "@lifetime cb handle", "@errno")
        + "int api_on(struct api_h *h, api_cb cb, void *arg);\n"
        + doc("Quiet", "@errno")
        + "int api_quiet(void);\n"
    )
    model, _ = parse(header, meta={"errmsg": "api_errmsg"})
    assert process(model, ["cpp"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "#include <stdio.h>\nstatic char msg[32];\nstatic int handle;\n"
        "const char *api_errmsg(void) { return msg; }\n"
        "int api_open(struct api_h **h) { *h = (struct api_h *)&handle; return 0; }\n"
        "int api_later(api_cb cb, void *arg)\n"
        '{\n\t(void)cb; (void)arg;\n\tsnprintf(msg, sizeof(msg), "later is busy");\n'
        "\treturn -16;\n}\n"
        "int api_on(struct api_h *h, api_cb cb, void *arg)\n"
        "{\n\t(void)h; (void)cb; (void)arg;\n"
        '\tsnprintf(msg, sizeof(msg), "on is busy");\n'
        "\treturn -16;\n}\n"
        "int api_quiet(void) { msg[0] = 0; return -5; }\n"
    )
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <system_error>\n#include <api.hpp>\n"
        "struct noisy {\n\t~noisy() { (void)::api_quiet(); }\n"
        "\tvoid operator()() const {}\n};\n"
        "int main() {\n\tauto h = api::open();\n"
        "\ttry {\n\t\tapi::later(noisy{});\n"
        "\t} catch (const std::system_error &e) {\n"
        '\t\tstd::printf("%s\\n", e.what());\n'
        "\t}\n"
        "\ttry {\n\t\th.on(noisy{});\n"
        "\t} catch (const std::system_error &e) {\n"
        '\t\tstd::printf("%s\\n", e.what());\n'
        "\t}\n\treturn 0;\n}\n"
    )
    include = ["-I", str(tmp_path / "cpp"), "-I", str(tmp_path / "capi")]
    api_o = str(tmp_path / "api.o")
    subprocess.run(
        ["cc", *include, "-c", str(tmp_path / "api.c"), "-o", api_o], check=True
    )
    program = tmp_path / "main"
    subprocess.run(
        ["c++", *CXXFLAGS, *include, str(tmp_path / "main.cpp"), api_o]
        + ["-o", str(program)],
        check=True,
    )
    run = subprocess.run([str(program)], capture_output=True, text=True)
    assert run.stdout == "api_later: later is busy\napi_on: on is busy\n"


def test_a_destructor_documented_errno_says_what_it_throws(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_h;\nstruct api_q;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Close", "@return 0, or -EIO where the write failed", "@destroys h")
        + "int api_close(struct api_h *h);\n"
        + doc("Make", "@param[out] q Q", "@errno")
        + "int api_make(struct api_q **q);\n"
        + doc("Drop", "@return 0, or -EIO", "@destroys q", "@errno")
        + "int api_drop(struct api_q *q);\n"
    )
    assert process(model, ["cpp"], tmp_path, check=False) == []

    hpp = flat((tmp_path / "cpp" / "api.hpp").read_text())
    # api_close() has no @errno: close() ignores what it returns, and never throws
    assert "/** * Close */ void close();" in hpp
    assert (
        "/** * Drop * * @throws std::system_error api_drop() returns: 0, or -EIO */"
        " void drop();" in hpp
    )


def test_a_constructor_named_as_a_keyword_keeps_the_name_of_its_handle(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_req;\nstruct api_h;\n"
        + doc("New", "@param[out] r R", "@errno")
        + "int api_req_new(struct api_req **r);\n"
        + doc("Free", "@destroys r")
        + "void api_req_free(struct api_req *r);\n"
        + doc("Delete")
        + "int api_req_delete(struct api_req *r);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_h_open(struct api_h **h);\n"
        + doc("Switch")
        + "int api_switch(int v);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    assert "inline req\nreq_new()" in hpp and "inline h\nopen()" in hpp
    # A method is in the class of its handle, and a function has no handle
    assert "int delete_();" in flat(hpp) and "inline int\nswitch_(int v)" in hpp


def test_a_handle_given_is_const_where_the_c_parameter_points_to_const(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_h;\nstruct api_q;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Make", "@param[out] q Q", "@errno")
        + "int api_make(struct api_q **q);\n"
        + doc("Start")
        + "int api_start(struct api_h *h, struct api_q *q);\n"
        + doc("Peek")
        + "int api_peek(struct api_h *h, const struct api_q *q);\n"
        + doc("Maybe", "@nullable q r")
        + "int api_maybe(struct api_h *h, struct api_q *q, const struct api_q *r);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    hpp = flat((tmp_path / "cpp" / "api.hpp").read_text())
    assert "int start(q &q_);" in hpp and "int peek(const q &q_);" in hpp
    assert "int maybe(q *q_, const q *r);" in hpp


def test_the_comment_says_what_the_signature_has_for_a_parameter_it_folds(
    parse, tmp_path
):
    from tests.test_rust import doc

    model, _ = parse(
        "#include <stdint.h>\n"
        + doc(
            "List from 'offset', until 'remaining' is 0",
            "",
            "'count' may be less than 'max'.",
            "",
            "@param offset The entries to skip",
            "@param[out] entries The entries, as many as 'count'",
            "@param max The room in 'entries'",
            "@param[out] count The entries written",
            "@param[out] remaining The entries after those",
            "@param[out] total The total",
            "@return 0, or a negative errno",
            "@note Not thread-safe.",
            "@len entries max",
            "@len entries count",
            "@errno",
        )
        + "int api_list(uint64_t offset, int32_t *entries, uint32_t max,"
        " uint32_t *count, uint64_t *remaining, uint64_t *total);\n"
        + doc("Sum of the 'n' values", "@len v n")
        + "int api_sum(const int32_t *v, uint32_t n);\n"
        + doc("Get", "@param[out] value The value")
        + "void api_get(int *value);\n"
    )
    assert process(model, ["cpp"], tmp_path) == []

    # Each comment on one line, without the ' * ' that starts a line of it
    hpp = (tmp_path / "cpp" / "api.hpp").read_text()
    hpp = re.sub(r"\s+", " ", re.sub(r"\s+\*(?=\s)", " ", hpp))
    # 'total' is returned too, and no text names it
    assert (
        " @note Not thread-safe. In this signature: 'max' is the size of"
        " 'entries'; 'count' is the size of the part of 'entries' returned;"
        " 'remaining' is returned. @param offset" in hpp
    )
    assert (
        "/** Sum of the 'n' values @note In this signature: 'n' is the size of"
        " 'v'. */ inline int sum(" in hpp
    )
    assert "/** Get */ inline int get()" in hpp
