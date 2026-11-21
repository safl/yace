# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import array
import ctypes
import errno
import gc
import importlib.util
import inspect
import io
import json
import os
import subprocess
import sys

import pytest
import yaml

from tests.conftest import (
    BITS,
    ERRMSG,
    ERRMSG_C,
    ESCAPED,
    ESCAPED_VALUE,
    HEADERS,
    PACKED,
    PACKED_PRINTED,
    SKIPPED,
    needs_cc,
    needs_cython,
)
from yace.compiler import process
from yace.targets.cython import target as cython_target


def module(tmp_path, name="api"):
    """Execute the source of the generated module 'name' and return its
    namespace."""

    namespace: dict = {}
    path = tmp_path / "python" / f"{name}.py"
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    return namespace


def json_lines(text):
    return [json.loads(line) for line in text.splitlines()]


def compiled(tmp_path, library=None, name="api"):
    """Import the Cython module 'name' generated into 'tmp_path' and return its
    namespace. With 'library', first build the module linking that shared
    library. Without 'library', import the module that the check built, with
    RTLD_LAZY, because that module does not link the library."""

    out = tmp_path / "cython"
    if library is not None:
        log: list = []
        failures = cython_target.build(out, name, log, link=[str(library)])
        assert failures == [], "\n".join(log)
    path = out / f"{name}{cython_target.SUFFIX}"
    spec = importlib.util.spec_from_file_location(name, path)
    flags = sys.getdlopenflags()
    if library is None:
        sys.setdlopenflags(os.RTLD_LAZY)
    try:
        made = importlib.util.module_from_spec(spec)  # loads the shared object
        spec.loader.exec_module(made)
    finally:
        sys.setdlopenflags(flags)
    return vars(made)


@pytest.fixture(params=["python", pytest.param("cython", marks=needs_cython)])
def bind(request, tmp_path, monkeypatch):
    """Return a function that binds a model to the shared library built from
    the C source given, and returns the namespace of the module. The parameter
    selects the target: the ctypes module or the Cython module."""

    from tests.test_rust import library

    target = request.param

    def bind(model, source):
        built = library(tmp_path, source)
        # compiled() builds the Cython module linking the library, so process()
        # skips the check of the Cython target
        assert process(model, [target], tmp_path, check=target == "python") == []
        if target == "python":
            monkeypatch.setenv("API_LIBRARY", str(built))
            return module(tmp_path)
        return compiled(tmp_path, built)

    bind.target = target
    bind.out = tmp_path / target
    return bind


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
    assert "FILE" in ns  # FILE, declared outside the headers, is a stub
    assert "log_it" not in ns  # the Python target binds no variadic function
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
    assert ns["pass_"].__doc__ == 'Ends in a quote, "so" '
    assert ns["Kind"].None_ == 1
    assert str(ns["foo__bar"]()) == "foo__bar:\n  x: 0\n"


def test_a_field_named_as_a_keyword_is_reached_by_its_escaped_name(parse, tmp_path):
    """xNVMe's options have a field 'async'. Without the escaped name, the
    assignment 'opts.async_ = ...' would silently add a Python attribute that
    C never sees."""

    model, _ = parse(
        "/** R */\nstruct api_r {\n\tint async; ///< A\n"
        "\tint class; ///< C\n\tint class_; ///< Taken\n};\n"
    )
    assert process(model, ["python"], tmp_path) == []

    ns = module(tmp_path)
    record = ns["ApiR"]()
    record.async_ = 3
    assert (getattr(record, "async"), record.async_) == (3, 3)
    record.class_ = 4
    assert (getattr(record, "class"), record.class_) == (0, 4)
    assert record.to_dict() == {"async": 3, "class": 0, "class_": 4}
    assert "async_: A" in ns["ApiR"].__doc__


def test_records_repr_as_their_constructor_is_called(parse, tmp_path):
    model, _ = parse(
        "#include <stdbool.h>\n#include <stdint.h>\n"
        "enum api_e { API_E_A = -1, API_E_B = 2, API_E_C = 2 };\n"
        "typedef enum api_e api_e_t;\n"
        "struct api_p { int32_t x; int32_t y; };\n"
        "struct api_v { bool flag; char letter; double d; enum api_e e;\n"
        "\tapi_e_t es[3]; char name[4]; int16_t grid[2][2]; struct api_p at;\n"
        "\tstruct api_p path[2]; const char *label; void *nil;\n"
        "\tchar names[2][3]; };\n"
        "union api_u { uint32_t u; struct api_p p; };\n" + BITS
    )
    assert process(model, ["python"], tmp_path) == []

    api = module(tmp_path)
    v = api["ApiV"](flag=True, letter=b"y", d=-2.5, e=-1, es=(2, 7, -1), name=b"ab")
    v.grid[1][0] = -5
    v.at.x, v.path[1].y, v.label = 3, 4, b"hi"
    v.names[0].value = b"\t\x7f"
    assert repr(v) == (
        "ApiV(flag=True, letter=b'y', d=-2.5, e=ApiE.API_E_A,"
        " es=[ApiE.API_E_B, 7, ApiE.API_E_A], name=b'ab', grid=[[0, 0], [-5, 0]],"
        " at=ApiP(x=3, y=0), path=[ApiP(x=0, y=0), ApiP(x=0, y=4)],"
        " label=b'hi', nil=None, names=[b'\\t\\x7f', b''])"
    )
    assert repr(api["ApiU"](u=0xFFFFFFFF)) == "ApiU(u=4294967295, p=ApiP(x=-1, y=0))"
    status = api["ApiStatus"](code=0x8F05)
    assert repr(status) == "ApiStatus(code=36613, wide=0)"


def test_a_header_named_as_a_standard_library_module_gets_an_underscore(
    parse, tmp_path
):
    """The header is json.h rather than zlib.h. No interpreter builds json in,
    so the rename comes from sys.stdlib_module_names on every interpreter, while
    zlib is in sys.builtin_module_names on some interpreters and not others."""

    model, _ = parse("/** J */\nstruct json_s { int a; };\n", "json.h")
    assert process(model, ["python"], tmp_path) == []
    assert (tmp_path / "python" / "json_.py").exists()


def test_typedefs_of_their_own_names_add_no_alias_and_fields_named_as_printers_print(
    parse, tmp_path
):
    model, _ = parse(
        "struct api_buf { int len; };\ntypedef struct api_buf api_buf;\n"
        "enum api_kind { API_KIND_A = 1 };\ntypedef enum api_kind api_kind;\n"
        "struct api_rec { int pr, fpr, to_dict; };\n"
        "int api_len(const api_buf *b, api_kind k);\n"
    )
    # process() runs the generated check, which prints ApiRec
    assert process(model, ["python"], tmp_path) == []

    api = module(tmp_path)
    assert api["ApiBuf"]._yace_name == "api_buf" and "api_buf" not in api
    assert str(api["ApiRec"](1, 2, 3)) == "api_rec:\n  pr: 1\n  fpr: 2\n  to_dict: 3\n"


def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["python"], tmp_path)
    assert failures and "sizeof(ValidPoint)" in failures[0]


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


def test_idiomatic_names_never_replace_the_raw_ones(parse, tmp_path):
    model, _ = parse(
        "struct handle;\n"
        "/**\n * @param[out] h H\n * @errno\n */\nint open_it(struct handle **h);\n"
        "/**\n * @destroys h\n */\nvoid close_it(struct handle *h);\n"
        "/**\n * @nullable a\n */\nint mix(int *a, int b);\n"
    )
    assert process(model, ["python"], tmp_path) == []

    ns = module(tmp_path)
    # Without a prefix to strip, an idiomatic name would equal the raw name, so
    # open_it stays the raw function and Handle stays the raw record
    assert ns["open_it"].__doc__ is None or "Calls" not in ns["open_it"].__doc__
    assert "Handle" in ns and issubclass(ns["Handle"], ns["ctypes"].Structure)


def test_a_nullable_parameter_before_a_required_one_has_no_default(parse, tmp_path):
    model, _ = parse(
        "/**\n * Mix\n * @param a A\n * @param b B\n * @nullable a\n */\n"
        "int api_mix(int *a, int b);\n"
    )
    assert process(model, ["python"], tmp_path) == []
    assert "def mix(a, b):" in (tmp_path / "python" / "api.py").read_text()


@needs_cc
def test_handles_are_released_when_collected(parse, bind):
    header = (
        "struct api_h;\n/** P */\nstruct api_p {\n\tint x; ///< X\n};\n"
        "typedef struct api_p api_p_t;\n"
        "/**\n * Open\n * @param[out] h H\n * @errno\n */\n"
        "int api_open(struct api_h **h);\n"
        "/**\n * Close\n * @destroys h\n */\nvoid api_close(struct api_h *h);\n"
        "/**\n * Open ones\n */\nint api_opened(void);\n"
        "/**\n * Get\n * @param[out] p P\n */\nvoid api_get(api_p_t *p);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "static int opened;\nstatic int h;\n"
        "int api_open(struct api_h **p)\n"
        "{ *p = (struct api_h *)&h; opened++; return 0; }\n"
        "void api_close(struct api_h *p) { (void)p; opened--; }\n"
        "int api_opened(void) { return opened; }\n"
        "void api_get(api_p_t *p) { p->x = 3; }\n",
    )
    handle = api["open"]()
    assert api["opened"]() == 1
    del handle
    assert api["opened"]() == 0
    assert api["get"]().x == 3


@needs_cc
def test_an_out_pointer_is_returned_and_a_nullable_sequence_may_be_omitted(parse, bind):
    header = (
        "#include <stddef.h>\n/** P */\nstruct api_p {\n\tint x; ///< X\n};\n"
        "/**\n * Get\n * @param[out] p P\n * @errno\n */\n"
        "int api_get(const struct api_p **p);\n"
        "/**\n * Sum\n * @arrparam buf B @len_at{n}\n * @param n N\n"
        " * @nullable buf\n */\nlong api_sum(const int *buf, size_t n);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "static const struct api_p P = {7};\n"
        "int api_get(const struct api_p **p) { *p = &P; return 0; }\n"
        "long api_sum(const int *buf, size_t n)\n"
        "{ long s = 0; for (size_t i = 0; i < n; i++) s += buf[i]; return s; }\n",
    )
    assert api["get"]().x == 7
    assert api["sum"]([1, 2, 3]) == 6
    assert api["sum"]() == 0


@needs_cc
def test_a_string_with_a_length_passes_the_length_of_its_bytes(parse, bind):
    from tests.test_rust import COUNTED, COUNTED_C

    model, _ = parse(COUNTED)
    api = bind(model, COUNTED + COUNTED_C)
    assert api["put"]("é") == 2
    assert api["pair"]("ab", [1, 2]) == ord("b") + 2
    assert list(api["read"](3)) == [0, 1, 2]


@needs_cc
def test_shared_counts_raise_on_unequal_lengths_and_handles_pass_as_arguments(
    parse, bind
):
    from tests.test_rust import MORE, MORE_C

    model, _ = parse(MORE)
    api = bind(model, MORE + MORE_C)
    handle = api["open"]()
    handle.copy(api["make"]())
    assert api["dot"]([1, 2], [3, 4]) == 11
    assert list(api["map"]([1, 2, 3], 3)) == [2, 4, 6]
    for call, args in (("dot", ([1], [1, 2])), ("map", ([1, 2], 3))):
        try:
            api[call](*args)
            raised = False
        except ValueError:
            raised = True
        assert raised, call
    assert handle.label() == "lbl"
    assert api["raw"]() == 16


def test_a_handle_named_as_the_prefix_is_a_class_of_its_own(parse, tmp_path):
    from tests.test_rust import HANDLE_NAMED_AS_PREFIX

    model, _ = parse(HANDLE_NAMED_AS_PREFIX, "prefixed.h")
    model.meta.prefix = "api"
    assert process(model, ["python"], tmp_path / "prefixed") == []
    assert (
        "class ApiHandle(object):"
        in (tmp_path / "prefixed" / "python" / "api.py").read_text()
    )


@needs_cc
def test_void_buffers_are_bytes_and_a_failing_destructor_raises_oserror(parse, bind):
    from tests.test_rust import IO, IO_C

    model, _ = parse(IO)
    api = bind(model, IO + IO_C)
    assert api["write"](b"abcd") == 4
    assert api["read"](8) == b"xyz"
    assert [list(each) for each in api["pair"](3)] == [[0, 1, 2], [0, 10, 20]]
    values = [1, 2, 3]
    api["twice"](values)
    assert values == [2, 4, 6]
    assert api["use"](7, api["default"]()) == 7

    handle = api["open"]()
    copy = handle.clone()
    try:
        copy.close()
        failed = None
    except OSError as err:
        failed = err.errno
    assert failed == 5
    handle.close()


@needs_cc
def test_an_out_count_bounds_the_result_and_the_error_holds_what_was_written(
    parse, bind
):
    from tests.test_rust import REAP, REAP_C

    model, _ = parse(REAP)
    api = bind(model, REAP + REAP_C)
    assert list(api["reap"](0, 4)) == [0, 10, 20]
    assert list(api["reap"](0, 2)) == [0, 10]
    with pytest.raises(BlockingIOError) as failed:
        api["reap"](errno.EAGAIN, 2)
    assert failed.value.errno == errno.EAGAIN
    assert list(failed.value.partial) == [0, 10]


@needs_cc
def test_a_recparam_record_is_passed_with_its_size_by_the_c_name(parse, bind):
    from tests.test_rust import SIZED, SIZED_C

    model, _ = parse(SIZED)
    api = bind(model, SIZED + SIZED_C)
    assert api["prep"](api["ApiArgs"](slba=40, nlb=2)) == 42


@needs_cc
def test_functions_named_as_builtins_do_not_shadow_them(parse, bind):
    header = (
        "#include <stddef.h>\n/** P */\nstruct api_p {\n\tdouble x; ///< X\n};\n"
        "/**\n * Len\n * @arrparam vals V\n */\n"
        "int api_len(const int *vals, size_t vals_len);\n"
        "/**\n * Type\n */\nint api_type(int x);\n"
        "/**\n * Format\n */\nint api_format(int x);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "int api_len(const int *vals, size_t n)\n"
        "{ int s = 0; for (size_t i = 0; i < n; i++) s += vals[i]; return s; }\n"
        "int api_type(int x) { return x; }\nint api_format(int x) { return x; }\n",
    )
    assert api["len"]([1, 2, 3]) == 6
    assert str(api["ApiP"](x=1.5)) == "api_p:\n  x: 1.5\n"


@needs_cc
def test_a_c_function_named_as_a_builtin_is_called_by_its_name(parse, bind):
    header = (
        "/** P */\nstruct api_p {\n\tint x; ///< X\n};\n"
        "/**\n * Len, without the prefix\n */\nint len(int x);\n"
    )
    model, _ = parse(header)
    api = bind(model, header + "int len(int x) { return x + 1; }\n")
    assert api["len"](3) == 4
    stream = io.StringIO()
    # The printers call the builtin len()
    assert api["ApiP"].fpr(stream, api["ApiP"](x=1)) == len("api_p:\n  x: 1\n")


@needs_cc
def test_shared_and_global_names_bind_and_a_callback_receives_a_str(parse, bind):
    header = (
        "typedef void (*api_seen_cb)(void *arg, const char *s);\n"
        "/**\n * Bar\n */\nint bar(int x);\n"
        "/**\n * Bar too\n */\nint api_bar(int x);\n"
        "/**\n * Ctypes\n */\nint api_ctypes(int x);\n"
        "/**\n * Seen\n * @lifetime cb call\n */\n"
        "void api_seen(api_seen_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "int bar(int x) { return x; }\nint api_bar(int x) { return 2 * x; }\n"
        "int api_ctypes(int x) { return x; }\n"
        'void api_seen(api_seen_cb cb, void *arg) { cb(arg, "done"); }\n',
    )
    assert (api["bar"](3), api["api_bar"](3), api["ctypes_"](4)) == (3, 6, 4)
    seen = []
    api["seen"](seen.append)
    assert seen == ["done"]


@needs_cc
def test_parameters_named_as_what_the_body_uses_pass_their_values_to_c(parse, bind):
    from tests.test_rust import HIDDEN, HIDDEN_C

    model, _ = parse(HIDDEN)
    api = bind(model, HIDDEN + HIDDEN_C)
    assert (api["add"](1), api["got"]()) == (2, 2)
    assert (api["set"](5, 2), api["u8"](1)) == (3, 9)
    assert (api["count"]([1, 2]), api["count"](None)) == (2, -1)
    assert api["foos"](1, 2, 3) == 2 and api["flip"](1) == (1, 2)
    with api["api_th_open_"]() as t:
        assert t.get() == 7
    assert "ApiBuf" in api and "format: 0" in str(api["ApiFrame"]())
    assert api["file"](0) is None and api["file"](1) is not None
    dev = api["api_dev_open_"](1, 2)
    assert dev.me(4) == 4 and api["make"](5)[1] == 5
    assert (dev.peer(dev), dev.peer(None)) == (1, 0)
    # api_msg ends in a flexible array, so msg() returns the record, not a copy
    message = dev.msg()
    assert message.len == 3 and api["take_"](1) == 2
    seen = []
    dev.keep(lambda v: seen.append(v) or 0, 6)
    assert seen == [6] and dev.ptr(9, 2) == 7
    assert api["api_cb_out_open_"]().me(8) == 8
    assert api["run"](lambda v: 10 * v) == 30
    assert api["rerun"](lambda v: v, 5, 1) == 4
    assert api["unsigned"](11) == 11
    assert api["variants"](1, 2, 3, 4) == -2
    assert api["primitives"](1, 2, 3) == 2
    assert api["renamed"](1, 2, 3, 4, 5) == 3


@needs_cc
def test_constructors_sharing_a_name_and_parameters_named_as_locals_bind(parse, bind):
    from tests.test_rust import NAMES, NAMES_C

    model, _ = parse(NAMES)
    api = bind(model, NAMES + NAMES_C)
    handle = api["api_h_open_"]()
    assert api["api_g_open_"]() is not None
    assert handle.me(3) == 3
    assert (api["ctx"](1, 2), api["outret"]()) == (3, 7)
    values = [1, 2]
    api["ioret"](values)
    assert values == [2, 3]
    assert api["names"](5, lambda v: 10 * v) == 50

    seen, locals_ = [], list(range(1, 14))
    api["call"](lambda v: seen.append(v) or 0, *locals_)
    api["call"](None, *locals_)
    api["once"](lambda v: seen.append(v + 1) or 0, *locals_)
    handle.keep(lambda v: seen.append(v + 2) or 0, *locals_)
    handle.keep(None, *locals_)
    assert seen == [91, 92, 93]
    assert api["two"](lambda v: 10 * v, lambda v: v) == 12
    assert api["c"]([1, 2, 3]) == 3
    assert api["sum"]([1, 2], 10, 20) == 33
    count, values = api["outs"](2, 4, 5)
    assert (count, list(values)) == (4, [5, 5])


@needs_cc
def test_a_callback_gets_a_non_null_context_and_an_in_out_bytearray_is_written(
    parse, bind
):
    header = (
        "#include <stddef.h>\ntypedef int (*api_cb)(void *arg, int v);\n"
        "/** T */\nstruct api_tag;\n"
        "/**\n * Tag\n */\nint api_tag(int v);\n"
        "/**\n * Run\n * @lifetime cb call\n * @errno\n */\n"
        "int api_run(api_cb cb, void *arg);\n"
        "/**\n * Invert\n * @arrparam[in,out] buf B @len_at{n}\n */\n"
        "void api_invert(void *buf, size_t n);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "#include <errno.h>\nint api_tag(int v) { return v; }\n"
        "int api_run(api_cb cb, void *arg) { return arg ? cb(arg, 2) : -EINVAL; }\n"
        "void api_invert(void *buf, size_t n)\n"
        "{ unsigned char *b = buf; for (size_t i = 0; i < n; i++) b[i] ^= 0xff; }\n",
    )
    assert api["tag"](4) == 4
    seen = []
    api["run"](lambda v: seen.append(v) or 0)
    assert seen == [2]
    buf = bytearray(b"\x00\x0f")
    api["invert"](buf)
    assert buf == bytearray(b"\xff\xf0")


@needs_cc
def test_a_void_pointer_array_has_the_length_of_its_bytes(parse, bind):
    """A buffer of elements wider than a byte is passed whole, its length in
    bytes, not in elements"""

    header = (
        "#include <stddef.h>\n"
        "/**\n * Sum\n * @arrparam buf B @len_at{n}\n */\n"
        "size_t api_sum(const void *buf, size_t n);\n"
        "/**\n * Invert\n * @arrparam[in,out] buf B @len_at{n}\n */\n"
        "size_t api_invert(void *buf, size_t n);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "size_t api_sum(const void *buf, size_t n)\n"
        "{ const unsigned char *b = buf; size_t s = 0;\n"
        "  for (size_t i = 0; i < n; i++) s += b[i]; return s; }\n"
        "size_t api_invert(void *buf, size_t n)\n"
        "{ unsigned char *b = buf; for (size_t i = 0; i < n; i++) b[i] ^= 0xff;\n"
        "  return n; }\n",
    )
    words = array.array("I", [1, 2])
    assert api["sum"](words) == 3
    assert api["invert"](words) == 2 * words.itemsize
    assert list(words) == [0xFFFFFFFE, 0xFFFFFFFD]


@needs_cc
def test_kept_closures_are_called_and_released(parse, bind):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    api = bind(model, KEPT + KEPT_C)
    seen = []
    handle = api["open"]()
    handle.on(lambda v: seen.append(v) or 0)
    handle.submit(None)
    handle.submit(lambda v: seen.append(100 * v) or 0)
    failed = []
    for call in (handle.on, handle.submit):
        try:
            call(lambda v: seen.append(1000 * v) or 0)
        except OSError as err:
            failed.append(err.errno)
    assert failed == [16, 16] and len(api["_KEPT"]) == 2
    assert len(handle._keys) == 1
    assert handle.poke() == 1
    handle.fire(5)
    assert seen == [700, 5] and len(api["_KEPT"]) == 1
    handle.close()
    assert api["_KEPT"] == {}


@needs_cc
def test_a_kept_callback_given_none_passes_null(parse, bind):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    api = bind(model, KEPT + KEPT_C)
    handle = api["open"]()
    handle.on(None)
    assert api["_KEPT"] == {}
    try:
        handle.fire(1)
        failed = None
    except OSError as err:
        failed = err.errno
    assert failed == 22


@needs_cc
def test_closures_kept_by_a_handle_whose_destructor_fails_are_kept(
    parse, tmp_path, monkeypatch
):
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
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "static int h;\n"
        "int api_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }\n"
        "int api_close(struct api_h *p) { (void)p; return -5; }\n"
        "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ (void)p; (void)cb; (void)arg; }\n"
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    for close in (lambda h: h.close(), lambda h: h.__del__()):
        handle = api["open"]()
        handle.on(lambda v: v)
        try:
            close(handle)
        except OSError:
            pass
        handle._handle = None
    assert len(api["_KEPT"]) == 2


@needs_cc
def test_closures_kept_by_a_handle_nothing_destroys_are_kept(parse, bind):
    from tests.test_rust import doc

    header = (
        "struct api_h;\ntypedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("On", "@lifetime cb handle")
        + "void api_on(struct api_h *h, api_cb cb, void *arg);\n"
        + doc("Fire")
        + "int api_fire(int v);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "static int h;\nstatic api_cb kept;\nstatic void *kept_arg;\n"
        "int api_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }\n"
        "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ (void)p; kept = cb; kept_arg = arg; }\n"
        "int api_fire(int v) { return kept(kept_arg, v); }\n",
    )
    handle = api["open"]()
    handle.on(lambda v: v + 1)
    del handle
    gc.collect()
    assert api["fire"](4) == 5


@needs_cc
def test_a_closed_handle_keeps_no_closure(parse, bind):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    api = bind(model, KEPT + KEPT_C)
    handle = api["open"]()
    handle.close()
    with pytest.raises(ValueError):
        handle.on(lambda v: v)
    assert api["_KEPT"] == {}


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["python"], tmp_path) == []


def test_a_field_of_bits_prints_its_parts(parse, tmp_path):
    model, _ = parse(BITS)
    assert process(model, ["python"], tmp_path) == []

    api = module(tmp_path)
    status = api["ApiStatus"](0x8A05, 0x8000000100000002)
    assert str(status) == (
        "api_status:\n"
        "  code: {val: 0x8a05, type: 0x5, delay: 0xa, dnr: 0x1}\n"
        "  wide: {val: 0x8000000100000002, low: 0x2, top: 0x1}\n"
    )
    assert status.to_dict() == {
        "code": {"val": 0x8A05, "type": 5, "delay": 10, "dnr": 1},
        "wide": {"val": 0x8000000100000002, "low": 2, "top": 1},
    }


def test_the_parts_of_a_field_of_bits_are_properties(parse, tmp_path):
    model, _ = parse(
        BITS + "/** K */\nstruct api_k {\n"
        "\tuint8_t class; ///< Class, see API_K_CLASS_*\n"
        "\tuint8_t to; ///< To, see API_K_TO_*\n};\n"
        "/** Hi; bits 7:4 of 'class' */\n#define API_K_CLASS_HI 0xf0\n"
        "/** Dict; bit 0 of 'to' */\n#define API_K_TO_DICT 0x1\n"
    )
    assert process(model, ["python"], tmp_path) == []

    api = module(tmp_path)
    status = api["ApiStatus"](0x8A05, 0x8000000100000002)
    assert (status.code_type, status.code_delay, status.code_dnr) == (5, 10, 1)
    assert (status.wide_low, status.wide_top) == (2, 1)
    status.code_delay = 3
    status.code_dnr = 0
    assert status.code == 0x0305 and status.code_type == 5
    status.wide_top = 0
    status.wide_low = 0xFFFFFFFF
    assert status.wide == 0x1FFFFFFFF
    with pytest.raises(ValueError, match="code_delay is 4 bits, not 16"):
        status.code_delay = 16
    with pytest.raises(ValueError):
        status.code_type = -1
    assert status.code == 0x0305
    assert api["ApiStatus"].code_type.__doc__ == "Kind; bits 2:0 of 'code'"

    k = api["ApiK"]()
    k.class_hi = 0xA
    k.to_dict_ = 1
    assert getattr(k, "class") == 0xA0 and k.to == 1
    assert k.to_dict() == {
        "class": {"val": 0xA0, "hi": 0xA},
        "to": {"val": 1, "dict": 1},
    }


def test_only_the_python_target_is_emitted(parse, tmp_path):
    from tests.test_cython import SPELLED

    model, _ = parse(SPELLED)
    assert process(model, ["python"], tmp_path / "out", check=False) == []
    assert [path.name for path in (tmp_path / "out").iterdir()] == ["python"]


def test_a_packed_record_is_laid_out_and_printed_as_in_c(parse, tmp_path):
    model, _ = parse(
        PACKED + "/** B */\nstruct __attribute__((packed)) api_b {\n"
        "\tuint8_t a : 4; ///< A\n\tuint32_t b : 20; ///< B\n};\n"
    )
    assert process(model, ["python"], tmp_path) == []

    api = module(tmp_path)
    packed, point = api["ApiK"], api["ApiP"]
    assert (ctypes.sizeof(packed), ctypes.alignment(packed)) == (35, 1)
    offsets = [getattr(packed, name).offset for name in ("value", "at", "pair")]
    assert offsets == [1, 5, 29]
    assert (ctypes.sizeof(api["ApiKu"]), ctypes.alignment(api["ApiKu"])) == (8, 1)
    # ctypes packs bit-fields only as MSVC does, so ApiB holds its bits as bytes
    assert [name for name, *_ in api["ApiB"]._fields_] == ["_bits"]

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


@needs_cc
def test_a_record_the_caller_may_write_is_not_copied(parse, bind):
    from tests.test_rust import POOL, POOL_C

    model, _ = parse(POOL)
    api = bind(model, POOL + POOL_C)
    queue = api["open"]()
    cmd_ = queue.get()
    cmd_.opc = 7
    queue.put(cmd_)
    peeked = queue.peek()
    again = queue.get()
    assert again.opc == 7 and peeked.opc == 7
    again.opc = 9
    assert cmd_.opc == 9 and peeked.opc == 7
    queue.close()


@needs_cc
def test_functions_converting_no_argument_are_the_ctypes_functions(
    parse, tmp_path, monkeypatch
):
    header = (
        "/** P */\nstruct api_p {\n\tint x; ///< X\n};\n"
        "/**\n * Add\n */\nint api_add(int a, int b);\n"
        "/**\n * Find\n * @nullable\n */\nstruct api_p *api_find(int x);\n"
        "/**\n * Name\n */\nconst char *api_name(void);\n"
        "/**\n * Len\n */\nint api_len(const char *s);\n"
    )
    model, _ = parse(header)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "#include <string.h>\nstatic struct api_p p = {7};\n"
        "int api_add(int a, int b) { return a + b; }\n"
        "struct api_p *api_find(int x) { return x == 7 ? &p : NULL; }\n"
        'const char *api_name(void) { return "api"; }\n'
        "int api_len(const char *s) { return (int)strlen(s); }\n"
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    stub = api["api_add"]
    assert stub(1, 2) == 3
    for name in ("api_add", "api_find", "api_name"):
        assert isinstance(api[name], ctypes._CFuncPtr), name
        assert api[name].__doc__.startswith(name.split("_")[1].capitalize())
    assert str(inspect.signature(api["api_add"])) == "(a, b, /)"
    assert api["api_find"](7).contents.x == 7
    assert api["api_find"](1) is None
    assert api["api_name"]() == "api"
    with pytest.raises(TypeError):
        stub(a=1, b=2)

    assert not isinstance(api["api_len"], ctypes._CFuncPtr)
    assert api["api_len"]("four") == 4
    assert api["api_len"](s="four") == 4


@needs_cc
@pytest.mark.parametrize("named", [True, False])
def test_the_oserror_holds_the_message_of_the_function_the_meta_names(
    parse, bind, named
):
    import os

    model, _ = parse(ERRMSG, meta={"errmsg": "api_errmsg"} if named else {})
    api = bind(model, ERRMSG + ERRMSG_C)
    handle = api["open"]("name")
    failed = []
    for call in [
        lambda: api["open"]("/run/api.sock"),
        api["quiet"],
        handle.close,
        lambda: api["reap"](2),
    ]:
        with pytest.raises(OSError) as raised:
            call()
        failed.append((raised.value.errno, raised.value.strerror))
    assert list(raised.value.partial) == [7]

    messages = ["no socket at /run/api.sock", "", "still in use", "reaped 1 of 3"]
    assert failed == [
        (code, message if named and message else os.strerror(code))
        for code, message in zip([2, 5, 16, 11], messages)
    ]


def test_a_length_or_capacity_its_type_cannot_hold_raises_overflowerror(parse, bind):
    """ctypes and a C cast would truncate 300 to 44 in a uint8_t"""

    from tests.test_rust import doc

    header = (
        "#include <stdint.h>\n"
        + doc("Count", "@arrparam vals V")
        + "int api_count(const int *vals, uint8_t vals_len);\n"
        + doc("Fill", "@arrparam[out] vals V")
        + "void api_fill(int *vals, uint8_t vals_len);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "int api_count(const int *v, uint8_t n) { (void)v; return n; }\n"
        "void api_fill(int *v, uint8_t n) { while (n--) v[n] = 1; }\n",
    )
    assert api["count"](list(range(255))) == 255
    assert list(api["fill"](255)) == [1] * 255
    with pytest.raises(OverflowError):
        api["count"](list(range(300)))
    with pytest.raises(OverflowError):
        api["fill"](300)


def test_an_out_array_of_handles_is_returned_as_its_pointers(parse, bind):
    from tests.test_idiom import HANDLES

    model, _ = parse(HANDLES)
    api = bind(
        model,
        HANDLES + "static char objs[4];\n"
        "int api_open(struct api_o **o) { *o = (struct api_o *)objs; return 0; }\n"
        "void api_close(struct api_o *o) { (void)o; }\n"
        "void api_fill(struct api_o **os, size_t n)\n"
        "{ while (n--) os[n] = (struct api_o *)&objs[n]; }\n",
    )
    found = api["fill"](4)
    assert len(found) == 4 and all(found)


REAPED = (
    "#include <stddef.h>\n#include <stdint.h>\n"
    "/** C */\nstruct api_c { uint32_t id; int status; };\n"
    "/**\n * Reap\n * @arrparam[out] cs Cs @nwritten_at{n}\n * @param[out] n N\n */\n"
    "void api_reap(struct api_c **cs, uint32_t cs_len, uint32_t *n);\n"
    "/**\n * Submit\n */\nint api_submit(struct api_c *c);\n"
    "/**\n * Get\n */\nstruct api_c *api_get(void);\n"
)


def test_an_out_array_of_record_pointers_is_returned_as_views(parse, bind):
    """The records are the library's, so a view of one is given back to C as
    the same record, as a command context is resubmitted"""

    model, _ = parse(REAPED)
    api = bind(
        model,
        REAPED + "static struct api_c cs[3] = {{1, 0}, {2, 0}, {3, 0}};\n"
        "void api_reap(struct api_c **out, uint32_t cap, uint32_t *n)\n"
        "{ *n = 0; while (*n < cap && *n < 2) { out[*n] = &cs[*n]; (*n)++; } }\n"
        "int api_submit(struct api_c *c) { return (int)(c - cs); }\n"
        "struct api_c *api_get(void) { return &cs[2]; }\n",
    )
    found = api["reap"](4)
    assert [c.id for c in found] == [1, 2]
    found[1].status = 7
    assert [api["submit"](c) for c in found] == [0, 1]
    assert api["reap"](4)[1].status == 7
    got = api["get"]()
    got.status = 9
    assert (got.id, api["submit"](got), api["get"]().status) == (3, 2, 9)
    if bind.target == "cython":
        stub = (bind.out / "api.pyi").read_text()
        assert "def reap(cs_len: int) -> list[ApiC | None]:" in stub


def test_an_out_array_of_pointers_to_const_records_is_returned_as_copies(parse, bind):
    """The caller may not write a const record, so writing what is returned
    does not write the record of the library"""

    header = (
        "#include <stdint.h>\n"
        "/** C */\nstruct api_c { uint32_t id; int status; };\n"
        "/**\n * List\n * @arrparam[out] cs Cs\n */\n"
        "void api_list(const struct api_c **cs, uint32_t cs_len);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "static const struct api_c cs[2] = {{1, 0}, {2, 0}};\n"
        "void api_list(const struct api_c **out, uint32_t cap)\n"
        "{ for (uint32_t i = 0; i < cap; i++) out[i] = i < 2 ? &cs[i] : 0; }\n",
    )
    found = api["list"](3)
    assert [c and c.id for c in found] == [1, 2, None]
    found[0].status = 7
    assert api["list"](1)[0].status == 0


def test_a_const_record_ending_in_a_flexible_array_is_returned_as_a_view(parse, bind):
    """A copy would not hold the elements, so the record is the library's,
    returned alone and in an [out] array, and C is given back the same record"""

    header = (
        "#include <stdint.h>\n"
        "/** F */\nstruct api_f { uint32_t len; uint8_t data[]; };\n"
        "/**\n * Get\n */\nconst struct api_f *api_get(void);\n"
        "/**\n * List\n * @arrparam[out] fs Fs\n */\n"
        "void api_list(const struct api_f **fs, uint32_t fs_len);\n"
        "/**\n * Same\n */\nint api_same(const struct api_f *f);\n"
    )
    model, _ = parse(header)
    api = bind(
        model,
        header + "static struct { uint32_t len; uint8_t d[4]; } f = {4, {0}};\n"
        "#define F ((const struct api_f *)&f)\n"
        "const struct api_f *api_get(void) { return F; }\n"
        "void api_list(const struct api_f **out, uint32_t cap)\n"
        "{ while (cap--) out[cap] = F; }\n"
        "int api_same(const struct api_f *p) { return p == F; }\n",
    )
    got = api["get"]()
    listed = api["list"](2)
    assert (got.len, api["same"](got)) == (4, 1)
    assert [(f.len, api["same"](f)) for f in listed] == [(4, 1), (4, 1)]
