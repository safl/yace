import gc
import json
import subprocess
import sys

import pytest
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


def test_idiomatic_names_never_replace_the_raw_ones(parse, tmp_path):
    model, _ = parse(
        "struct handle;\n"
        "/**\n * @param[out] h H\n * @errno\n */\nint open_it(struct handle **h);\n"
        "/**\n * @destroys h\n */\nvoid close_it(struct handle *h);\n"
        "/**\n * @nullable a\n */\nint mix(int *a, int b);\n"
    )
    assert process(model, ["python"], tmp_path) == []

    ns = module(tmp_path)
    # Without a prefix to strip, the names are those of the raw functions, and
    # the handle's class that of the raw record: neither gets an idiomatic one
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
def test_handles_are_released_when_collected(parse, tmp_path, monkeypatch):
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
    assert process(model, ["python"], tmp_path) == []

    (tmp_path / "api.c").write_text(
        header + "static int opened;\nstatic int h;\n"
        "int api_open(struct api_h **p)\n"
        "{ *p = (struct api_h *)&h; opened++; return 0; }\n"
        "void api_close(struct api_h *p) { (void)p; opened--; }\n"
        "int api_opened(void) { return opened; }\n"
        "void api_get(api_p_t *p) { p->x = 3; }\n"
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    handle = api["open"]()
    assert api["opened"]() == 1
    del handle
    assert api["opened"]() == 0
    assert api["get"]().x == 3


@needs_cc
def test_pointers_written_and_nullable_sequences(parse, tmp_path, monkeypatch):
    header = (
        "#include <stddef.h>\n/** P */\nstruct api_p {\n\tint x; ///< X\n};\n"
        "/**\n * Get\n * @param[out] p P\n * @errno\n */\n"
        "int api_get(const struct api_p **p);\n"
        "/**\n * Sum\n * @param buf B\n * @param n N\n * @nullable buf\n"
        " * @len buf n\n */\nlong api_sum(const int *buf, size_t n);\n"
    )
    model, _ = parse(header)
    assert process(model, ["python"], tmp_path) == []

    source = tmp_path / "api.c"
    source.write_text(
        header + "static const struct api_p P = {7};\n"
        "int api_get(const struct api_p **p) { *p = &P; return 0; }\n"
        "long api_sum(const int *buf, size_t n)\n"
        "{ long s = 0; for (size_t i = 0; i < n; i++) s += buf[i]; return s; }\n"
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(source), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    assert api["get"]().x == 7
    assert api["sum"]([1, 2, 3]) == 6
    assert api["sum"]() == 0


@needs_cc
def test_shared_counts_handles_given_and_more_returns(parse, tmp_path, monkeypatch):
    from tests.test_rust import HANDLE_NAMED_AS_PREFIX, MORE, MORE_C

    model, _ = parse(MORE)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(MORE + MORE_C)
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    handle = api["open"]()
    handle.copy(api["make"]())
    assert api["dot"]([1, 2], [3, 4]) == 11
    assert api["map"]([1, 2, 3], 3) == [2, 4, 6]
    for call, args in (("dot", ([1], [1, 2])), ("map", ([1, 2], 3))):
        try:
            api[call](*args)
            raised = False
        except ValueError:
            raised = True
        assert raised, call
    assert handle.label() == "lbl"
    assert api["raw"]() == 16

    model, _ = parse(HANDLE_NAMED_AS_PREFIX, "prefixed.h")
    model.meta.prefix = "api"
    assert process(model, ["python"], tmp_path / "prefixed") == []
    assert (
        "class ApiHandle(object):"
        in (tmp_path / "prefixed" / "python" / "api.py").read_text()
    )


@needs_cc
def test_bytes_out_arrays_in_out_sequences_and_destructor_errors(
    parse, tmp_path, monkeypatch
):
    from tests.test_rust import IO, IO_C

    model, _ = parse(IO)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(IO + IO_C)
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    assert api["write"](b"abcd") == 4
    assert api["read"](8) == b"xyz"
    assert api["pair"](3) == ([0, 1, 2], [0, 10, 20])
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
def test_functions_named_as_builtins_do_not_shadow_them(parse, tmp_path, monkeypatch):
    header = (
        "#include <stddef.h>\n/** P */\nstruct api_p {\n\tdouble x; ///< X\n};\n"
        "/**\n * Len\n * @len vals n\n */\nint api_len(const int *vals, size_t n);\n"
        "/**\n * Type\n */\nint api_type(int x);\n"
        "/**\n * Format\n */\nint api_format(int x);\n"
    )
    model, _ = parse(header)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "int api_len(const int *vals, size_t n)\n"
        "{ int s = 0; for (size_t i = 0; i < n; i++) s += vals[i]; return s; }\n"
        "int api_type(int x) { return x; }\nint api_format(int x) { return x; }\n"
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    assert api["len"]([1, 2, 3]) == 6
    assert str(api["ApiP"](x=1.5)) == "api_p:\n  x: 1.5\n"


@needs_cc
def test_shared_names_module_globals_and_callback_strings(parse, tmp_path, monkeypatch):
    header = (
        "typedef void (*api_seen_cb)(void *arg, const char *s);\n"
        "/**\n * Bar\n */\nint bar(int x);\n"
        "/**\n * Bar too\n */\nint api_bar(int x);\n"
        "/**\n * Ctypes\n */\nint api_ctypes(int x);\n"
        "/**\n * Seen\n * @lifetime cb call\n */\n"
        "void api_seen(api_seen_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "int bar(int x) { return x; }\nint api_bar(int x) { return 2 * x; }\n"
        "int api_ctypes(int x) { return x; }\n"
        'void api_seen(api_seen_cb cb, void *arg) { cb(arg, "done"); }\n'
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    assert (api["bar"](3), api["api_bar"](3), api["ctypes_"](4)) == (3, 6, 4)
    seen = []
    api["seen"](seen.append)
    assert seen == ["done"]


@needs_cc
def test_parameters_named_as_what_the_body_uses(parse, tmp_path, monkeypatch):
    from tests.test_rust import HIDDEN, HIDDEN_C

    model, _ = parse(HIDDEN)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(HIDDEN + HIDDEN_C)
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
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
    message = dev.msg()  # a pointer, as its payload follows it
    assert message.contents.len == 3 and api["take_"](1) == 2
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
def test_parameters_named_as_locals_and_constructors_sharing_a_name(
    parse, tmp_path, monkeypatch
):
    from tests.test_rust import NAMES, NAMES_C

    model, _ = parse(NAMES)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(NAMES + NAMES_C)
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
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
    assert api["outs"](2, 4, 5) == (4, [5, 5])


@needs_cc
def test_contexts_given_c_byte_buffers_written_and_records_named_as_functions(
    parse, tmp_path, monkeypatch
):
    header = (
        "#include <stddef.h>\ntypedef int (*api_cb)(void *arg, int v);\n"
        "/** T */\nstruct api_tag;\n"
        "/**\n * Tag\n */\nint api_tag(int v);\n"
        "/**\n * Run\n * @lifetime cb call\n * @errno\n */\n"
        "int api_run(api_cb cb, void *arg);\n"
        "/**\n * Invert\n * @param[in,out] buf B\n * @len buf n\n */\n"
        "void api_invert(void *buf, size_t n);\n"
    )
    model, _ = parse(header)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "#include <errno.h>\nint api_tag(int v) { return v; }\n"
        "int api_run(api_cb cb, void *arg) { return arg ? cb(arg, 2) : -EINVAL; }\n"
        "void api_invert(void *buf, size_t n)\n"
        "{ unsigned char *b = buf; for (size_t i = 0; i < n; i++) b[i] ^= 0xff; }\n"
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    assert api["tag"](4) == 4
    seen = []
    api["run"](lambda v: seen.append(v) or 0)
    assert seen == [2]
    buf = bytearray(b"\x00\x0f")
    api["invert"](buf)
    assert buf == bytearray(b"\xff\xf0")


@needs_cc
def test_kept_closures_are_called_and_released(parse, tmp_path, monkeypatch):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(KEPT + KEPT_C)
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
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
def test_a_kept_callback_given_none_passes_null(parse, tmp_path, monkeypatch):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(KEPT + KEPT_C)
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
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
def test_closures_kept_by_a_handle_nothing_destroys_are_kept(
    parse, tmp_path, monkeypatch
):
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
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(
        header + "static int h;\nstatic api_cb kept;\nstatic void *kept_arg;\n"
        "int api_open(struct api_h **p) { *p = (struct api_h *)&h; return 0; }\n"
        "void api_on(struct api_h *p, api_cb cb, void *arg)\n"
        "{ (void)p; kept = cb; kept_arg = arg; }\n"
        "int api_fire(int v) { return kept(kept_arg, v); }\n"
    )
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    handle = api["open"]()
    handle.on(lambda v: v + 1)
    del handle
    gc.collect()
    assert api["fire"](4) == 5


@needs_cc
def test_a_closed_handle_keeps_no_closure(parse, tmp_path, monkeypatch):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    assert process(model, ["python"], tmp_path) == []
    (tmp_path / "api.c").write_text(KEPT + KEPT_C)
    library = tmp_path / "libapi.so"
    cmd = ["cc", "-shared", "-fPIC", str(tmp_path / "api.c"), "-o", str(library)]
    subprocess.run(cmd, check=True)
    monkeypatch.setenv("API_LIBRARY", str(library))

    api = module(tmp_path)
    handle = api["open"]()
    handle.close()
    with pytest.raises(ValueError):
        handle.on(lambda v: v)
    assert api["_KEPT"] == {}


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["python"], tmp_path) == []
