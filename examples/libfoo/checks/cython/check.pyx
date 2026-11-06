# cython: language_level=3
"""
The check of the .pxd of libfoo: Cython code cimporting the C API through the
generated foo.pxd, calling the library directly and printing what it got back,
as YAML documents, or with "json" as JSON objects, each holding what
'expected.yaml' says. Records are printed by the check itself, from their C
fields; the C API's printers are not part of the library.
"""

import json

from libc.stddef cimport size_t
from libc.stdint cimport int64_t, uint32_t
from libc.string cimport memset

cimport foo as c

SHAPES = {
    c.FOO_SHAPE_NONE: "FOO_SHAPE_NONE",
    c.FOO_SHAPE_POINT: "FOO_SHAPE_POINT",
    c.FOO_SHAPE_LINE: "FOO_SHAPE_LINE",
    c.FOO_SHAPE_POLYGON: "FOO_SHAPE_POLYGON",
}
OPTIONS = {
    c.FOO_OPTION_CLOSED: "FOO_OPTION_CLOSED",
    c.FOO_OPTION_FILLED: "FOO_OPTION_FILLED",
}


def document(name, data, as_json):
    if as_json:
        print(json.dumps({name: data}))
        return
    print(f"---\n{name}:")
    for key, value in data.items():
        print(f"  {key}: {json.dumps(value)}")  # JSON is also YAML


def record(name, data, as_json):
    if data is None:
        print(json.dumps({name: None}) if as_json else f"---\n{name}:")
    else:
        document(name, data, as_json)


cdef str string(const char *chars):
    return None if chars == NULL else chars.decode()


cdef float_(double value):
    """A float, as C's printf() prints it with "%g\""""

    return float(format(value, "g"))


cdef dict point(const c.foo_point *obj):
    return {"x": obj.x, "y": obj.y}


cdef dict status(const c.foo_status *obj):
    return {
        "code": {
            "val": obj.code,
            "pending": (obj.code & c.FOO_STATUS_CODE_PENDING) >> 0,
            "points": (obj.code & c.FOO_STATUS_CODE_POINTS) >> 4,
            "full": (obj.code & c.FOO_STATUS_CODE_FULL) >> 15,
        },
        "max": obj.max,
    }


cdef dict scalars(const c.foo_scalars *obj):
    return {
        "flag": obj.flag,
        "letter": obj.letter,
        "schar": obj.schar,
        "uchar": obj.uchar,
        "s": obj.s,
        "us": obj.us,
        "i": obj.i,
        "ui": obj.ui,
        "l": obj.l,
        "ul": obj.ul,
        "ll": obj.ll,
        "ull": obj.ull,
        "f": float_(obj.f),
        "d": float_(obj.d),
        "i8": obj.i8,
        "i16": obj.i16,
        "i32": obj.i32,
        "i64": obj.i64,
        "u8": obj.u8,
        "u16": obj.u16,
        "u32": obj.u32,
        "u64": obj.u64,
        "iptr": obj.iptr,
        "uptr": obj.uptr,
        "size": obj.size,
        "ssize": obj.ssize,
        "diff": obj.diff,
    }


cdef dict figure(const c.foo_figure *obj):
    return {
        "shape": obj.shape,
        "options": obj.options,
        "origin": point(&obj.origin),
        "corners": [point(&obj.corners[idx]) for idx in range(4)],
        "ncorners": obj.ncorners,
        "name": string(obj.name),
        "grid": [[obj.grid[row][col] for col in range(3)] for row in range(2)],
        "label": string(obj.label),
        "scale": float_(obj.scale),
        "area": float_(obj.area),
    }


cdef dict wire(const c.foo_wire *obj):
    # A copy, as a packed field may not be aligned for its address to be taken
    cdef c.foo_point at = obj.at

    return {
        "kind": obj.kind,
        "length": obj.length,
        "at": point(&at),
        "pair": [obj.pair[idx] for idx in range(2)],
    }


cdef struct totals:
    int64_t x
    int64_t y
    size_t stop_after
    size_t visited


cdef int summarize(void *arg, const c.foo_point *point) noexcept nogil:
    cdef totals *found = <totals *>arg

    found.x += point.x
    found.y += point.y
    found.visited += 1
    return found.visited == found.stop_after


cdef void watch_added(void *arg, const c.foo_point *point) noexcept nogil:
    summarize(arg, point)


cdef void count_done(void *arg, size_t count) noexcept nogil:
    (<size_t *>arg)[0] = count


def main(fmt):
    cdef c.foo_handle *handle = NULL
    cdef c.foo_point points[3]
    cdef c.foo_point copied[4]
    cdef totals every, first_two, with_visitor, watched
    cdef c.foo_visitor visitor
    cdef c.foo_scalars scalars_
    cdef c.foo_figure figure_
    cdef c.foo_status status_
    cdef c.foo_value value
    cdef c.foo_wire wire_
    cdef size_t done_count = 0
    cdef uint32_t shape

    as_json = fmt == "json"
    points[0] = c.foo_point(1, 2)
    points[1] = c.foo_point(3, 4)
    points[2] = c.foo_point(5, 6)
    memset(&every, 0, sizeof(every))
    memset(&first_two, 0, sizeof(first_two))
    memset(&with_visitor, 0, sizeof(with_visitor))
    memset(&watched, 0, sizeof(watched))
    first_two.stop_after = 2
    visitor.visit = summarize
    visitor.arg = &with_visitor

    document(
        "defines",
        {
            "FOO_NAME": string(c.FOO_NAME),
            "FOO_MAGIC": c.FOO_MAGIC,
            "FOO_VERSION_MAJOR": c.FOO_VERSION_MAJOR,
            "FOO_VERSION_MINOR": c.FOO_VERSION_MINOR,
            "FOO_VERSION_PATCH": c.FOO_VERSION_PATCH,
            "FOO_POINTS_MAX": c.FOO_POINTS_MAX,
            "FOO_DEFAULT_SHAPE_SIDES": c.FOO_DEFAULT_SHAPE_SIDES,
        },
        as_json,
    )
    document(
        "enums",
        {
            "foo_shape": [SHAPES.get(v, "UNKNOWN") for v in (-1, 0, 1, 2, 3)],
            "foo_option": [OPTIONS.get(v, "UNKNOWN") for v in (1, 2, 3)],
        },
        as_json,
    )

    calls = {"version": string(c.foo_version())}
    calls["open"] = c.foo_open(b"points", &handle)
    if handle == NULL:
        return 1
    calls["open_without_name"] = c.foo_open(NULL, &handle)
    calls["name"] = string(c.foo_name(handle))
    calls["watch"] = c.foo_point_watch(handle, watch_added, &watched)
    calls["watch_busy"] = c.foo_point_watch(handle, watch_added, &watched)
    calls["added"] = sum([not c.foo_point_add(handle, &points[idx]) for idx in range(3)])
    calls["count"] = c.foo_point_count(handle)
    calls["visit"] = c.foo_point_visit(handle, summarize, &every)
    calls["visit_sum_x"] = every.x
    calls["visit_sum_y"] = every.y
    calls["visit_stopped"] = c.foo_point_visit(handle, summarize, &first_two)
    calls["visit_without_callback"] = c.foo_point_visit(handle, NULL, NULL)
    calls["visit_with"] = c.foo_point_visit_with(handle, &visitor)
    calls["visit_with_sum_x"] = with_visitor.x
    calls["figure_of_unknown_shape"] = c.foo_figure_fill(&figure_, 3)
    calls["add_many"] = c.foo_point_add_many(handle, points, 3)
    calls["count_after_add_many"] = c.foo_point_count(handle)
    calls["watched"] = watched.visited
    calls["watched_sum_x"] = watched.x
    calls["points_copied"] = c.foo_point_copy(handle, copied, 4)
    calls["points_sum_x"] = sum([copied[idx].x for idx in range(4)])
    calls["submit"] = c.foo_count_submit(handle, count_done, &done_count)
    calls["submit_busy"] = c.foo_count_submit(handle, count_done, &done_count)
    calls["complete"] = c.foo_count_complete(handle)
    calls["done_count"] = done_count
    calls["complete_again"] = c.foo_count_complete(handle)
    document("calls", calls, as_json)

    for idx in (1, 6):
        found = c.foo_point_get(handle, idx)
        record("foo_point", None if found == NULL else point(found), as_json)

    while not c.foo_point_add(handle, &points[0]):
        pass
    document(
        "full",
        {
            "count": c.foo_point_count(handle),
            "add": c.foo_point_add(handle, &points[0]),
            "add_many": c.foo_point_add_many(handle, points, 1),
            "watched": watched.visited,
        },
        as_json,
    )
    c.foo_status_get(handle, &status_)
    record("foo_status", status(&status_), as_json)
    parts = status(&status_)["code"]
    document("status", {k: parts[k] for k in ("pending", "points", "full")}, as_json)
    memset(&status_, 0, sizeof(status_))
    status_.code |= (5 << 4) & c.FOO_STATUS_CODE_POINTS
    status_.code |= c.FOO_STATUS_CODE_PENDING
    status_.max = c.FOO_POINTS_MAX
    record("foo_status", status(&status_), as_json)
    c.foo_close(handle)
    c.foo_close(NULL)

    c.foo_scalars_fill(&scalars_)
    record("foo_scalars", scalars(&scalars_), as_json)
    for shape in range(c.FOO_SHAPE_POINT, c.FOO_SHAPE_POLYGON + 1):
        if c.foo_figure_fill(&figure_, shape):
            return 1
        record("foo_figure", figure(&figure_), as_json)
    c.foo_value_set(&value, -1)
    record(
        "foo_value", {"i": value.i, "u": value.u, "point": point(&value.point)}, as_json
    )
    c.foo_wire_fill(&wire_)
    record("foo_wire", wire(&wire_), as_json)
    return 0

