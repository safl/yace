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
    assert (found["foo_add"].kind, found["foo_add"].name) == ("method", "add")
    assert found["foo_version"].kind == "function"


def test_parameters_are_given_returned_or_hidden():
    found = calls()
    assert kinds(found["foo_open"]) == [("name", "string"), ("handle", "out")]
    assert kinds(found["foo_add_many"]) == [
        ("handle", "self"),
        ("points", "sequence"),
        ("npoints", "length"),
    ]
    assert kinds(found["foo_points"]) == [
        ("handle", "self"),
        ("points", "out"),
        ("npoints", "capacity"),
    ]
    assert kinds(found["foo_visit"]) == [
        ("handle", "self"),
        ("visit", "callback"),
        ("arg", "context"),
    ]
    assert [o.kind for o in found["foo_figure_fill"].outs] == ["record"]


def test_returns_follow_errno_and_nullability():
    found = calls()
    assert found["foo_add"].returns == "nothing" and found["foo_add"].errno
    assert found["foo_add_many"].returns == "count"
    assert found["foo_at"].returns == "pointer" and found["foo_at"].nullable
    assert found["foo_name"].returns == "string"
