from pathlib import Path

import yaml

from yace.ir.cparser import CParser
from yace.targets.idiom import Idioms

FIXTURE = Path(__file__).parent.parent / "examples" / "libfoo"


def calls():
    meta = yaml.safe_load((FIXTURE / "meta.yaml").read_text())
    model, _ = CParser().parse(FIXTURE / "include" / "foo.h", meta)
    return {c.function: c for c in Idioms(model).calls}


def kinds(call):
    return [(a.param, a.kind) for a in call.args]


def test_handles_get_constructors_methods_and_destructors():
    found = calls()
    assert (found["foo_open"].kind, found["foo_open"].handle) == (
        "constructor",
        "foo_handle",
    )
    assert found["foo_close"].kind == "destructor"
    add = found["foo_point_add"]
    assert (add.kind, add.name) == ("method", "point_add")
    assert found["foo_version"].kind == "function"


def test_parameters_are_given_returned_or_hidden():
    found = calls()
    assert kinds(found["foo_open"]) == [("name", "string"), ("handle", "out")]
    assert kinds(found["foo_point_add_many"]) == [
        ("handle", "self"),
        ("points", "sequence"),
        ("npoints", "length"),
    ]
    assert kinds(found["foo_point_copy"]) == [
        ("handle", "self"),
        ("points", "out"),
        ("npoints", "capacity"),
    ]
    assert kinds(found["foo_point_visit"]) == [
        ("handle", "self"),
        ("visit", "callback"),
        ("arg", "context"),
    ]
    assert [o.kind for o in found["foo_figure_fill"].outs] == ["record"]


def test_returns_follow_errno_and_nullability():
    found = calls()
    assert found["foo_point_add"].returns == "nothing" and found["foo_point_add"].errno
    assert found["foo_point_add_many"].returns == "count"
    assert (
        found["foo_point_get"].returns == "pointer" and found["foo_point_get"].nullable
    )
    assert found["foo_name"].returns == "string"


def test_a_callback_without_a_lifetime_is_given_raw(parse):
    model, diagnostics = parse(
        "typedef int (*api_cb)(void *arg, int v);\n"
        "/**\n * Kept\n * @lifetime cb once\n */\nint api_kept(api_cb cb, void *arg);\n"
        "/**\n * Raw\n */\nint api_raw(api_cb cb, void *arg);\n"
    )
    assert "callback-lifetime" in [d.rule for d in diagnostics]
    found = {c.function: c for c in Idioms(model).calls}
    assert kinds(found["api_kept"]) == [("cb", "callback"), ("arg", "context")]
    assert found["api_kept"].args[0].lifetime == "once"
    assert kinds(found["api_raw"]) == [("cb", "value"), ("arg", "value")]


def test_a_callback_without_a_context_is_given_raw(parse):
    model, diagnostics = parse(
        "typedef int (*api_cb)(int v);\n"
        "/**\n * Each\n * @lifetime cb call\n */\nint api_each(api_cb cb);\n"
    )
    assert "callback-context" in [d.rule for d in diagnostics]
    found = {c.function: c for c in Idioms(model).calls}
    assert kinds(found["api_each"]) == [("cb", "value")]


def test_a_callback_type_without_one_context_is_given_raw(parse):
    model, _ = parse(
        "typedef int (*api_cb)(int v);\n"
        "/**\n * Run\n * @lifetime cb once\n */\nint api_run(api_cb cb, void *arg);\n"
    )
    found = {c.function: c for c in Idioms(model).calls}
    assert kinds(found["api_run"]) == [("cb", "value"), ("arg", "value")]


def test_an_inline_callback_is_given_raw(parse):
    model, diagnostics = parse(
        "/**\n * Each\n * @lifetime cb call\n */\n"
        "int api_each(int (*cb)(void *arg, int v), void *arg);\n"
    )
    assert "callback-typedef" in [d.rule for d in diagnostics]
    found = {c.function: c for c in Idioms(model).calls}
    assert kinds(found["api_each"]) == [("cb", "value"), ("arg", "value")]
