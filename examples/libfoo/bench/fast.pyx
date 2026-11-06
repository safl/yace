# cython: language_level=3
"""
The Cython ways of the benchmark, through the generated foo.pxd, and the plain
C one, in sum.c; each sums the x of every point of the handle at 'addr',
'rounds' times
"""

from libc.stdint cimport int64_t, uintptr_t

cimport foo as c


cdef extern from *:
    """
    #include "sum.c"
    """
    int64_t bench_sum(const c.foo_handle *handle, size_t rounds) nogil


def at(uintptr_t addr, size_t rounds):
    """foo_at() in a loop of Cython"""

    cdef const c.foo_handle *handle = <const c.foo_handle *>addr
    cdef size_t count = c.foo_count(handle)
    cdef int64_t total = 0
    cdef size_t round, idx
    with nogil:
        for round in range(rounds):
            for idx in range(count):
                total += c.foo_at(handle, idx).x
    return total


cdef int add_x(void *arg, const c.foo_point *point) noexcept nogil:
    (<int64_t *>arg)[0] += point.x
    return 0


def visit(uintptr_t addr, size_t rounds):
    """foo_visit() with a callback of Cython"""

    cdef c.foo_handle *handle = <c.foo_handle *>addr
    cdef int64_t total = 0
    cdef size_t round
    with nogil:
        for round in range(rounds):
            c.foo_visit(handle, add_x, &total)
    return total


def plain(uintptr_t addr, size_t rounds):
    """The loop of foo_at() in C"""

    cdef int64_t total
    with nogil:
        total = bench_sum(<const c.foo_handle *>addr, rounds)
    return total
