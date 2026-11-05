"""
The check of the idiomatic Python layer of libfoo: as check.py, through handles,
exceptions and returned values rather than raw calls. An OSError is printed as
the negative errno the C function returned, so the documents printed are those
of 'expected.yaml', as for the raw layer.
"""

import sys

import foo
from check import document, name_of, record, statuses


def errno_of(call, *args):
    """What 'call' returns, 0 for nothing, or the negative errno it raises"""

    try:
        ret = call(*args)
    except OSError as exc:
        return -exc.errno
    return 0 if ret is None else ret


def main():
    as_json = len(sys.argv) > 1 and sys.argv[1] == "json"
    flags = foo.FOO_PR_JSON if as_json else foo.FOO_PR_YAML

    document(
        "defines",
        {
            name: getattr(foo, name)
            for name in [
                "FOO_NAME",
                "FOO_MAGIC",
                "FOO_VERSION_MAJOR",
                "FOO_VERSION_MINOR",
                "FOO_VERSION_PATCH",
                "FOO_POINTS_MAX",
                "FOO_DEFAULT_SHAPE_SIDES",
            ]
        },
        as_json,
    )
    document(
        "enums",
        {
            "foo_shape": [name_of(foo.FooShape, v) for v in (-1, 0, 1, 2, 3)],
            "foo_option": [name_of(foo.FooOption, v) for v in (1, 2, 3)],
        },
        as_json,
    )

    points = [foo.FooPoint(1, 2), foo.FooPoint(3, 4), foo.FooPoint(5, 6)]
    calls = {"version": foo.version()}
    with foo.open("points") as handle:
        calls["open"] = 0
        calls["open_without_name"] = errno_of(foo.open, None)
        calls["name"] = handle.name()
        calls["added"] = sum(errno_of(handle.add, p) == 0 for p in points)
        calls["count"] = handle.count()

        seen = []
        calls["visit"] = handle.visit(lambda point: seen.append(point.x) or 0)
        calls["visit_sum_x"] = sum(seen)
        ys = []
        handle.visit(lambda point: ys.append(point.y) or 0)
        calls["visit_sum_y"] = sum(ys)
        calls["visit_stopped"] = handle.visit(lambda point: point.x == 3)
        calls["visit_without_callback"] = errno_of(handle.visit, None)
        with_visitor = []
        callback = foo.FooVisitCb(lambda arg, p: with_visitor.append(p.contents.x) or 0)
        calls["visit_with"] = handle.visit_with(foo.FooVisitor(visit=callback))
        calls["visit_with_sum_x"] = sum(with_visitor)
        calls["figure_of_unknown_shape"] = errno_of(foo.figure_fill, 3)
        calls["add_many"] = handle.add_many(points)
        calls["count_after_add_many"] = handle.count()
        copied = handle.points(4)
        calls["points_copied"] = len(copied)
        calls["points_sum_x"] = sum(point.x for point in copied)
        counted = []
        calls["submit"] = errno_of(handle.submit, counted.append)
        calls["submit_busy"] = errno_of(handle.submit, counted.append)
        calls["poke"] = handle.poke()
        calls["done_count"] = counted[0]
        calls["poke_again"] = handle.poke()
        document("calls", calls, as_json)

        record(foo.FooPoint, handle.at(1), flags)
        record(foo.FooPoint, handle.at(6), flags)

        while errno_of(handle.add, points[0]) == 0:
            pass
        document(
            "full",
            {
                "count": handle.count(),
                "add": errno_of(handle.add, points[0]),
                "add_many": errno_of(handle.add_many, points[:1]),
            },
            as_json,
        )
        statuses(handle.status_get(), flags, as_json)
    handle.close()  # closing again does nothing

    record(foo.FooScalars, foo.scalars_fill(), flags)
    for shape in (foo.FOO_SHAPE_POINT, foo.FOO_SHAPE_LINE, foo.FOO_SHAPE_POLYGON):
        record(foo.FooFigure, foo.figure_fill(shape), flags)
    record(foo.FooValue, foo.value_set(-1), flags)

    return 0


if __name__ == "__main__":
    sys.exit(main())
