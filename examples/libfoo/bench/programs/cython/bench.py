# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Runs the Cython benchmark, as built by setup.py beside it: fast, the loops in
Cython calling C through foo.pxd, and the idiomatic loops of the Python
benchmark through foo, the Cython module of the bindings, by
handle.point_get() and by handle.point_visit() with a function

  python bench.py ROUNDS REPEAT
"""

import json
import sys
import time

import fast
import foo


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


def run(way, sum_of, handle, points, rounds, repeat):
    best, total = None, 0
    for _ in range(repeat):
        start = time.perf_counter_ns()
        total = sum_of(handle, rounds)
        elapsed = time.perf_counter_ns() - start
        best = elapsed if best is None else min(best, elapsed)
    ns = best / (rounds * points)
    result = {"target": "cython-idiomatic", "way": way, "ns": round(ns, 3)}
    print(json.dumps({**result, "sum": total}))


def main():
    rounds, repeat = (int(arg) for arg in sys.argv[1:3])
    fast.main(rounds, repeat)

    points = [foo.FooPoint(idx, -idx) for idx in range(foo.FOO_POINTS_MAX)]
    with foo.open("bench") as handle:
        handle.point_add_many(points)
        run("calls", idiomatic_calls, handle, len(points), rounds, repeat)
        run("callback", idiomatic_callback, handle, len(points), rounds, repeat)


if __name__ == "__main__":
    main()
