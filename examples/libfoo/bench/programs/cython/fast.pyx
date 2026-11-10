# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# cython: language_level=3
"""
The benchmark in Cython through the generated foo.pxd, as the C one: by
foo_point_get() and by foo_point_visit() with a callback of Cython, both in
loops without the GIL
"""

import json
import time

from libc.stdint cimport int64_t

cimport foo as c


cdef int64_t calls(const c.foo_handle *handle, size_t rounds) noexcept nogil:
    cdef size_t count = c.foo_point_count(handle)
    cdef int64_t total = 0
    cdef size_t each, idx
    for each in range(rounds):
        for idx in range(count):
            total += c.foo_point_get(handle, idx).x
    return total


cdef int add_x(void *arg, const c.foo_point *point) noexcept nogil:
    (<int64_t *>arg)[0] += point.x
    return 0


cdef int64_t callback(c.foo_handle *handle, size_t rounds) noexcept nogil:
    cdef int64_t total = 0
    cdef size_t each
    for each in range(rounds):
        c.foo_point_visit(handle, add_x, &total)
    return total


cdef run(c.foo_handle *handle, str way, size_t rounds, size_t repeat):
    cdef int64_t total = 0
    cdef bint by_calls = way == "calls"
    best = None
    for _ in range(repeat):
        start = time.perf_counter_ns()
        with nogil:
            if by_calls:
                total = calls(handle, rounds)
            else:
                total = callback(handle, rounds)
        elapsed = time.perf_counter_ns() - start
        best = elapsed if best is None else min(best, elapsed)
    ns = best / (rounds * c.foo_point_count(handle))
    print(json.dumps({"target": "cython", "way": way, "ns": round(ns, 3), "sum": total}))


def main(size_t rounds, size_t repeat):
    """Print the time per point of each way, and its sum, as JSON lines"""

    cdef c.foo_handle *handle = NULL
    cdef c.foo_point points[c.FOO_POINTS_MAX]
    cdef int idx
    if c.foo_open(b"bench", &handle):
        raise OSError("foo_open() failed")
    for idx in range(c.FOO_POINTS_MAX):
        points[idx].x = idx
        points[idx].y = -idx
    if c.foo_point_add_many(handle, points, c.FOO_POINTS_MAX) != c.FOO_POINTS_MAX:
        raise OSError("foo_point_add_many() failed")
    run(handle, "calls", rounds, repeat)
    run(handle, "callback", rounds, repeat)
    c.foo_close(handle)
