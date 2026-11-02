"""
The check of the Python bindings of libfoo: calls the library through the
generated module and prints what it got back, as YAML documents, or with
argument "json" as JSON objects, each holding what 'expected.yaml' says
"""

import ctypes
import json
import sys

import foo


def document(name, data, as_json):
    if as_json:
        print(json.dumps({name: data}))
        return
    print(f"---\n{name}:")
    for key, value in data.items():
        print(f"  {key}: {json.dumps(value)}")


def record(cls, obj, flags):
    """Print a record with the pretty-printer generated for it"""

    if flags == foo.FOO_PR_YAML:
        print("---")
        cls.pr(obj, flags)
        return
    print(f'{{"{cls._yace_name}": ', end="")
    cls.pr(obj, flags)
    print("}")


def name_of(enum, value):
    try:
        return enum(value).name
    except ValueError:
        return "UNKNOWN"


class Sum(object):
    """A visitor summing the points it visits, stopping after 'stop_after'"""

    def __init__(self, stop_after=0):
        self.x = self.y = self.visited = 0
        self.stop_after = stop_after
        self.callback = foo.FooVisitCb(self.visit)

    def visit(self, arg, point):
        self.x += point.contents.x
        self.y += point.contents.y
        self.visited += 1
        return int(self.visited == self.stop_after)


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

    calls = {"version": foo.foo_version()}
    handle = ctypes.POINTER(foo.FooHandle)()
    calls["open"] = foo.foo_open("points", ctypes.byref(handle))
    calls["open_without_name"] = foo.foo_open(None, ctypes.byref(handle))
    calls["name"] = foo.foo_name(handle)
    points = [foo.FooPoint(1, 2), foo.FooPoint(3, 4), foo.FooPoint(5, 6)]
    calls["added"] = sum(not foo.foo_add(handle, point) for point in points)
    calls["count"] = foo.foo_count(handle)
    every, first_two, with_visitor = Sum(), Sum(stop_after=2), Sum()
    calls["visit"] = foo.foo_visit(handle, every.callback, None)
    calls["visit_sum_x"] = every.x
    calls["visit_sum_y"] = every.y
    calls["visit_stopped"] = foo.foo_visit(handle, first_two.callback, None)
    calls["visit_without_callback"] = foo.foo_visit(handle, foo.FooVisitCb(), None)
    visitor = foo.FooVisitor(visit=with_visitor.callback)
    calls["visit_with"] = foo.foo_visit_with(handle, visitor)
    calls["visit_with_sum_x"] = with_visitor.x
    calls["figure_of_unknown_shape"] = foo.foo_figure_fill(foo.FooFigure(), 3)
    many = (foo.FooPoint * len(points))(*points)
    calls["add_many"] = foo.foo_add_many(handle, many, len(points))
    calls["count_after_add_many"] = foo.foo_count(handle)
    copied = (foo.FooPoint * 4)()
    calls["points_copied"] = foo.foo_points(handle, copied, 4)
    calls["points_sum_x"] = sum(point.x for point in copied)
    counted = []
    done = foo.FooDoneCb(lambda arg, count: counted.append(count))
    calls["submit"] = foo.foo_submit(handle, done, None)
    calls["submit_busy"] = foo.foo_submit(handle, done, None)
    calls["poke"] = foo.foo_poke(handle)
    calls["done_count"] = counted[0]
    calls["poke_again"] = foo.foo_poke(handle)
    document("calls", calls, as_json)

    record(foo.FooPoint, foo.foo_at(handle, 1), flags)
    record(foo.FooPoint, foo.foo_at(handle, 6), flags)

    while not foo.foo_add(handle, points[0]):
        pass
    document(
        "full",
        {
            "count": foo.foo_count(handle),
            "add": foo.foo_add(handle, points[0]),
            "add_many": foo.foo_add_many(handle, many, 1),
        },
        as_json,
    )
    foo.foo_close(handle)
    foo.foo_close(None)

    scalars = foo.FooScalars()
    foo.foo_scalars_fill(scalars)
    record(foo.FooScalars, scalars, flags)

    for shape in (foo.FOO_SHAPE_POINT, foo.FOO_SHAPE_LINE, foo.FOO_SHAPE_POLYGON):
        figure = foo.FooFigure()
        if foo.foo_figure_fill(figure, shape):
            return 1
        record(foo.FooFigure, figure, flags)

    value = foo.FooValue()
    foo.foo_value_set(value, -1)
    record(foo.FooValue, value, flags)

    return 0


if __name__ == "__main__":
    sys.exit(main())
