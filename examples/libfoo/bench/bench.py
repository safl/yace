"""
What the .pxd brings: the x of every point of a handle, filled by
foo_point_add_many(), summed in six ways, from the idiomatic ctypes layer to
plain C, 'rounds' times over, as a handle holds FOO_POINTS_MAX points. Prints
the time per point of each, the best of 'repeat' runs, and the sum, which all
six must agree on; with --json, as JSON lines.

Needs the bindings, foo, on PYTHONPATH, FOO_LIBRARY set, and fast built, see
setup.py: python bench.py ROUNDS [--repeat N] [--json]
"""

import argparse
import ctypes
import json
import time

import fast
import foo


def idiomatic(handle, rounds):
    count = handle.point_count()
    total = 0
    for _ in range(rounds):
        for idx in range(count):
            total += handle.point_get(idx).x
    return total


def raw(handle, rounds):
    ptr = handle._handle
    count = foo.foo_point_count(ptr)
    total = 0
    for _ in range(rounds):
        for idx in range(count):
            total += foo.foo_point_get(ptr, idx).contents.x
    return total


def visit(handle, rounds):
    found = [0]

    def add_x(arg, point):
        found[0] += point.contents.x
        return 0

    callback = foo.FooVisitCb(add_x)
    for _ in range(rounds):
        foo.foo_point_visit(handle._handle, callback, None)
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rounds", type=int)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    handle = foo.open("bench")
    handle.point_add_many(
        [foo.FooPoint(idx, -idx) for idx in range(foo.FOO_POINTS_MAX)]
    )
    addr = ctypes.cast(handle._handle, ctypes.c_void_p).value
    points = args.rounds * handle.point_count()

    ways = [
        (
            "ctypes, idiomatic handle.point_get()",
            lambda: idiomatic(handle, args.rounds),
        ),
        ("ctypes, raw foo_point_get()", lambda: raw(handle, args.rounds)),
        (
            "ctypes, foo_point_visit() calling Python",
            lambda: visit(handle, args.rounds),
        ),
        (
            "Cython, foo_point_get() through the .pxd",
            lambda: fast.point_get(addr, args.rounds),
        ),
        (
            "Cython, foo_point_visit() calling Cython",
            lambda: fast.point_visit(addr, args.rounds),
        ),
        ("C, foo_point_get()", lambda: fast.plain(addr, args.rounds)),
    ]
    for name, way in ways:
        best = None
        for _ in range(args.repeat):
            start = time.perf_counter_ns()
            total = way()
            elapsed = time.perf_counter_ns() - start
            best = elapsed if best is None else min(best, elapsed)
        per_point = best / points
        if args.json:
            print(json.dumps({"way": name, "ns": per_point, "sum": total}))
        else:
            print(f"{name:40} {per_point:10.1f} ns/point  sum {total}")
    handle.close()


if __name__ == "__main__":
    main()
