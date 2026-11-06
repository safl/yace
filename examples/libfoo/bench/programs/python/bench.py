"""
The benchmark through the ctypes bindings, as the C one: through the raw
layer, by foo.foo_point_get() and by foo.foo_point_visit() with a FooVisitCb,
and through the idiomatic layer, by handle.point_get() and by
handle.point_visit() with a function.

Needs the bindings, foo, on PYTHONPATH and FOO_LIBRARY set:

  python bench.py ROUNDS REPEAT
"""

import ctypes
import json
import sys
import time

import foo


def raw_calls(handle, rounds):
    count = foo.foo_point_count(handle)
    total = 0
    for _ in range(rounds):
        for idx in range(count):
            total += foo.foo_point_get(handle, idx).contents.x
    return total


def raw_callback(handle, rounds):
    found = [0]

    def add_x(arg, point):
        found[0] += point.contents.x
        return 0

    callback = foo.FooVisitCb(add_x)
    for _ in range(rounds):
        foo.foo_point_visit(handle, callback, None)
    return found[0]


def idiomatic_calls(handle, rounds):
    count = handle.point_count()
    total = 0
    for _ in range(rounds):
        for idx in range(count):
            total += handle.point_get(idx).x
    return total


def idiomatic_callback(handle, rounds):
    found = [0]

    def add_x(point):
        found[0] += point.x
        return 0

    for _ in range(rounds):
        handle.point_visit(add_x)
    return found[0]


def run(target, way, sum_of, handle, points, rounds, repeat):
    best, total = None, 0
    for _ in range(repeat):
        start = time.perf_counter_ns()
        total = sum_of(handle, rounds)
        elapsed = time.perf_counter_ns() - start
        best = elapsed if best is None else min(best, elapsed)
    ns = best / (rounds * points)
    print(json.dumps({"target": target, "way": way, "ns": round(ns, 3), "sum": total}))


def main():
    rounds, repeat = (int(arg) for arg in sys.argv[1:3])
    points = [foo.FooPoint(idx, -idx) for idx in range(foo.FOO_POINTS_MAX)]
    count = len(points)

    raw = ctypes.POINTER(foo.FooHandle)()
    assert foo.foo_open("bench", ctypes.byref(raw)) == 0
    array = (foo.FooPoint * count)(*points)
    assert foo.foo_point_add_many(raw, array, count) == count
    run("python-raw", "calls", raw_calls, raw, count, rounds, repeat)
    run("python-raw", "callback", raw_callback, raw, count, rounds, repeat)
    foo.foo_close(raw)

    with foo.open("bench") as handle:
        handle.point_add_many(points)
        run("python-idiomatic", "calls", idiomatic_calls, handle, count, rounds, repeat)
        run(
            "python-idiomatic",
            "callback",
            idiomatic_callback,
            handle,
            count,
            rounds,
            repeat,
        )


if __name__ == "__main__":
    main()
