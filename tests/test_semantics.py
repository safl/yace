# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

from yace.ir import decls

HEADER = """
#include <stddef.h>
#include <sys/types.h>

struct h;

typedef int (*visit_cb)(void *arg, int value);

/**
 * Open
 *
 * @param[in] name The name
 * @param[out] handle Set to the handle
 *
 * @errno
 */
int h_open(const char *name, struct h **handle);

/**
 * Close
 *
 * @param handle The handle
 *
 * @nullable handle
 * @destroys handle
 */
void h_close(struct h *handle);

/**
 * Read
 *
 * @param handle The handle
 * @param[out] buf Filled in
 * @param len Of buf
 * @param[in,out] pos Where
 * @param visit Called
 * @param arg For visit
 *
 * @len buf len
 * @nullable return visit
 * @lifetime visit call
 * @errno
 */
const int *h_read(struct h *handle, int *buf, size_t len, size_t *pos,
                  visit_cb visit, void *arg);
"""


def functions(model) -> dict:
    return {e.name: e for e in model.entities if isinstance(e, decls.Function)}


def test_tags_are_in_the_ir(parse):
    model, diagnostics = parse(HEADER)
    assert [d.rule for d in diagnostics if d.rule != "missing-doc"] == ["annotation"]

    funcs = functions(model)
    open_, close, read = funcs["h_open"], funcs["h_close"], funcs["h_read"]
    assert open_.errno and open_.params[1].direction == "out"
    assert open_.params[0].direction == "in"
    assert close.destroys == "handle" and close.params[0].nullable
    params = {p.name: p for p in read.params}
    assert params["buf"].direction == "out" and params["buf"].length == "len"
    assert params["pos"].direction == "inout"
    assert params["visit"].nullable and read.nullable
    assert params["arg"].context == "visit"
    assert params["visit"].lifetime == "call"


def test_a_returned_pointer_is_not_an_errno(parse):
    """h_read returns a pointer, so its @errno is reported, and not applied"""

    model, diagnostics = parse(HEADER)
    (annotation,) = [d for d in diagnostics if d.rule == "annotation"]
    assert "h_read" in annotation.message and "@errno" in annotation.message
    assert not functions(model)["h_read"].errno


def test_tags_survive_the_stored_ir(parse, tmp_path):
    from yace.ir.model import load

    model, _ = parse(HEADER)
    model.save(tmp_path / "api.yaml")
    assert load(tmp_path / "api.yaml") == model


def test_a_borrowed_record_written_through_out_is_no_handle(parse):
    _, diagnostics = parse(
        "/** P */\nstruct p { int x; };\n"
        "/**\n * Get\n * @param[out] p P\n */\nint get(const struct p **p);\n"
    )
    assert "handle-lifecycle" not in [d.rule for d in diagnostics]


def test_a_handle_by_a_typedef_of_its_own_name_is_destroyed(parse):
    model, diagnostics = parse(
        "typedef struct h h;\n"
        "/**\n * Open\n * @param[out] p P\n * @errno\n */\nint h_open(h **p);\n"
        "/**\n * Close\n * @destroys p\n */\nvoid h_close(h *p);\n"
    )
    assert functions(model)["h_close"].destroys == "p"
    assert "annotation" not in [d.rule for d in diagnostics]


def test_destroying_through_a_typedef_of_another_name_says_so(parse):
    model, diagnostics = parse(
        "typedef struct h_s h_t;\n"
        "/**\n * Close\n * @destroys p\n */\nvoid h_close(h_t *p);\n"
    )
    assert functions(model)["h_close"].destroys is None
    (annotation,) = [d for d in diagnostics if d.rule == "annotation"]
    assert "typedef of another name" in annotation.message


def test_the_c_api_says_what_the_header_says(parse, tmp_path):
    from yace.targets.capi.target import CAPI

    model, _ = parse(HEADER)
    CAPI(tmp_path).emit(model)
    again, _ = parse((tmp_path / "capi" / "libapi.h").read_text(), "again.h")

    for name, func in functions(model).items():
        other = functions(again)[name]
        assert [
            (p.direction, p.nullable, p.length, p.context, p.lifetime)
            for p in func.params
        ] == [
            (p.direction, p.nullable, p.length, p.context, p.lifetime)
            for p in other.params
        ]
        assert (func.errno, func.destroys, func.nullable) == (
            other.errno,
            other.destroys,
            other.nullable,
        )
