# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import shutil

from yace.compiler import process
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
 * @arrparam[out] buf Filled in @len_at{len}
 * @param len Of buf
 * @param[in,out] pos Where
 * @param visit Called
 * @param arg For visit
 *
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


def test_errno_on_a_function_returning_a_pointer_is_reported_and_not_applied(parse):
    """h_read returns a pointer, so its @errno is reported and not applied"""

    model, diagnostics = parse(HEADER)
    (annotation,) = [d for d in diagnostics if d.rule == "annotation"]
    assert "h_read" in annotation.message and "@errno" in annotation.message
    assert not functions(model)["h_read"].errno


def test_tags_are_kept_in_the_stored_ir(parse, tmp_path):
    from yace.ir.model import load

    model, _ = parse(HEADER)
    model.save(tmp_path / "api.yaml")
    assert load(tmp_path / "api.yaml") == model


def test_a_borrowed_record_written_through_out_is_not_a_handle(parse):
    _, diagnostics = parse(
        "/** P */\nstruct p { int x; };\n"
        "/**\n * Get\n * @param[out] p P\n */\nint get(const struct p **p);\n"
    )
    assert "handle-lifecycle" not in [d.rule for d in diagnostics]


def test_destroys_applies_to_a_handle_typed_by_a_typedef_of_its_own_name(parse):
    model, diagnostics = parse(
        "typedef struct h h;\n"
        "/**\n * Open\n * @param[out] p P\n * @errno\n */\nint h_open(h **p);\n"
        "/**\n * Close\n * @destroys p\n */\nvoid h_close(h *p);\n"
    )
    assert functions(model)["h_close"].destroys == "p"
    assert "annotation" not in [d.rule for d in diagnostics]


def test_destroys_through_a_typedef_of_another_name_is_reported_and_not_applied(parse):
    model, diagnostics = parse(
        "typedef struct h_s h_t;\n"
        "/**\n * Close\n * @destroys p\n */\nvoid h_close(h_t *p);\n"
    )
    assert functions(model)["h_close"].destroys is None
    (annotation,) = [d for d in diagnostics if d.rule == "annotation"]
    assert "typedef of another name" in annotation.message


def test_the_c_api_header_carries_the_tags_of_the_parsed_header(parse, tmp_path):
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


REAP = """
#include <stdint.h>

struct q;

/**
 * Reap
 *
 * @arrparam[out] done Done @len_at{max} @nwritten_at{n}
 * @param[out] n How many
 *
 * @errno partial
 */
int q_reap(struct q *queue, int *done, uint32_t max, uint32_t *n);
"""


def test_an_out_count_and_a_partial_errno_are_in_the_ir(parse):
    model, diagnostics = parse(REAP)
    assert [d for d in diagnostics if d.rule == "annotation"] == []

    reap = functions(model)["q_reap"]
    params = {p.name: p for p in reap.params}
    assert (params["done"].length, params["done"].count) == ("max", "n")
    assert reap.errno and reap.partial


WRONG = [
    (
        "/**\n * @arrparam v V @nwritten_at{n}\n * @param[out] n N\n */\n"
        "void f(const int *v, uint32_t v_len, uint32_t *n);",
        "'n' is the count written of 'v', which is not [out]",
        {},
    ),
    (
        "/**\n * @arrparam[out] v V @nwritten_at{n}\n * @param[out] n N\n */\n"
        "void f(int *v, uint32_t *n);",
        "'v' has no 'v_len', nor a @len_at{}",
        {},
    ),
    (
        "/**\n * @arrparam[out] v V @nwritten_at{n}\n * @param[out] n N\n */\n"
        "void f(int *v, uint32_t v_len, int32_t *n);",
        "the count written 'n' of 'v' is not an [out] pointer to an unsigned integer",
        {},
    ),
    (
        "/**\n * @arrparam[out] v V @nwritten_at{n}\n * @param[out] n N\n"
        " * @param[out] v_nwritten W\n */\n"
        "void f(int *v, uint32_t v_len, uint32_t *n, uint32_t *v_nwritten);",
        "@nwritten_at{n} of 'v', but 'v_nwritten' is a parameter too",
        {},
    ),
    (
        "/**\n * @arrparam[out] a A @len_at{c} @nwritten_at{n}\n"
        " * @arrparam[out] b B @len_at{c} @nwritten_at{n}\n * @param[out] n N\n"
        " */\nvoid f(int *a, int *b, uint32_t c, uint32_t *n);",
        "'n' is the count written of two arrays",
        {"a": "n"},
    ),
    (
        "/**\n * @errno always\n */\nint f(void);",
        "@errno takes nothing, or 'partial'",
        {},
    ),
    ("/**\n * @errno partial\n */\nint f(int x);", "but no parameter is [out]", {}),
    (
        "struct h;\n/**\n * @param[out] h H\n * @errno partial\n */\n"
        "int f(struct h **h);",
        "@errno partial, but 'h' is an [out] handle",
        {},
    ),
    (
        "#include <sys/types.h>\n/**\n * @arrparam[out] v V @len_at{c}\n"
        " * @errno partial\n */\nssize_t f(int *v, uint32_t c);",
        "@errno partial, but it returns a count, which a failure does not give",
        {},
    ),
]


def test_a_wrong_out_count_or_partial_errno_is_reported(parse):
    """Each wrong count written or @errno is reported and not applied, except
    that of two arrays given one count written the first keeps it"""

    for source, message, kept in WRONG:
        model, diagnostics = parse("#include <stdint.h>\n" + source)
        found = [d.message for d in diagnostics if d.rule == "annotation"]
        assert any(message in m for m in found), (source, found)
        func = functions(model)["f"]
        assert not func.partial
        assert {p.name: p.count for p in func.params if p.count} == kept


def test_an_out_pointer_to_void_without_a_len_is_reported_and_not_applied(
    parse, tmp_path
):
    """Nothing says how many bytes the function writes through 'p', so the
    bindings cannot return them; 'buf' has a length, and is returned"""

    model, diagnostics = parse(
        "#include <stddef.h>\n"
        "/**\n * Fill\n * @param[out] p P\n * @errno\n */\nint api_fill(void *p);\n"
        "/**\n * Read\n * @arrparam[out] buf B\n * @errno\n */\n"
        "int api_read(void *buf, size_t buf_len);\n"
    )
    found = [d for d in diagnostics if d.rule == "annotation"]
    assert [(d.line, d.message) for d in found] == [
        (
            7,
            "'api_fill': 'p' is [out] but points to void without a length; document"
            " it with @arrparam, its length in bytes",
        )
    ]
    funcs = functions(model)
    assert funcs["api_fill"].params[0].direction == "in"
    assert funcs["api_read"].params[0].direction == "out"

    # With [out] applied, the C++ layer declared a local of type void
    if shutil.which("cc"):
        assert process(model, ["cpp"], tmp_path / "out") == []


RECPARAM = """
#include <stddef.h>
#include <stdint.h>

/**
 * Arguments
 */
struct args {
	uint64_t slba; ///< First
	uint32_t nlb;  ///< Count
};

/**
 * Arguments, by a typedef
 */
typedef struct args args_t;

/**
 * Prepare
 *
 * @param[out] cmd Set to the command
 * @recparam args The arguments
 * @param args_nbytes Size of args
 * @recparam more More arguments @nbytes_at{nmore}
 * @param nmore Size of more
 *
 * @errno
 */
int prep_sized(uint64_t *cmd, const args_t *args, size_t args_nbytes,
               const struct args *more, size_t nmore);

/**
 * Prepare, passing the sizes
 */
static inline int
prep(uint64_t *cmd, const args_t *args, const struct args *more)
{
	return prep_sized(cmd, args, sizeof(*args), more, sizeof(*more));
}
"""


def test_records_of_arguments_and_their_sizes_are_in_the_ir(parse):
    model, diagnostics = parse(RECPARAM)
    assert [d for d in diagnostics if d.rule == "annotation"] == []

    prep = functions(model)["prep_sized"]
    assert prep.doc.params["more"] == "More arguments"
    sizes = {p.name: p.size for p in prep.params if p.size}
    assert sizes == {"args": "args_nbytes", "more": "nmore"}


def test_arrays_take_their_length_and_count_written_by_name_or_reference(parse):
    model, diagnostics = parse(
        "#include <stddef.h>\n#include <stdint.h>\n"
        "/**\n * Fill\n * @arrparam ids I\n * @arrparam[out] out O\n"
        " * @param[out] out_nwritten N\n */\n"
        "void fill(const uint32_t *ids, size_t ids_len, int *out, uint32_t out_len,\n"
        "          uint32_t *out_nwritten);\n"
        "/**\n * Take\n * @arrparam[out] out O, of\n * @len_at{max} @nwritten_at{n}\n"
        " * @param[out] n N\n */\n"
        "void take(int *out, uint32_t max, uint32_t *n);\n"
    )
    assert [d for d in diagnostics if d.rule == "annotation"] == []

    found = functions(model)
    fill = {p.name: (p.length, p.count) for p in found["fill"].params}
    assert fill["ids"] == ("ids_len", None)
    assert fill["out"] == ("out_len", "out_nwritten")
    take = found["take"]
    assert (take.params[0].length, take.params[0].count) == ("max", "n")
    assert take.doc.params["out"] == "O, of"


WRONG_RECPARAM = [
    (
        "@recparam x X",
        "int f_sized(const struct r *r, size_t r_nbytes);",
        "@recparam names 'x', which is not a parameter",
    ),
    (
        "@recparam r R",
        "int f_sized(struct r *r, size_t r_nbytes);",
        "@recparam names 'r', which is not a pointer to a const struct defined",
    ),
    (
        "@recparam o O",
        "int f_sized(const struct o *o, size_t o_nbytes);",
        "@recparam names 'o', which is not a pointer to a const struct defined",
    ),
    (
        "@recparam u U",
        "int f_sized(const union u *u, size_t u_nbytes);",
        "@recparam names 'u', which is not a pointer to a const struct defined",
    ),
    (
        "@recparam r R\n * @arrparam r R @len_at{c}",
        "int f_sized(size_t c, const struct r *r, size_t r_nbytes);",
        "'r' is documented by both @arrparam and @recparam",
    ),
    (
        "@recparam r R @len_at{c}",
        "int f_sized(size_t c, const struct r *r, size_t r_nbytes);",
        "'r' has @len_at, which is of an @arrparam",
    ),
    (
        "@recparam r R",
        "int f_sized(const struct r *r, size_t n);",
        "'r' has no 'r_nbytes', nor a @nbytes_at{}",
    ),
    (
        "@recparam r R @nbytes_at{m}",
        "int f_sized(const struct r *r, size_t n);",
        "@nbytes_at{m} of 'r' names no parameter",
    ),
    (
        "@recparam r R @nbytes_at{n}",
        "int f_sized(const struct r *r, size_t n, size_t r_nbytes);",
        "@nbytes_at{n} of 'r', but 'r_nbytes' is a parameter too",
    ),
    (
        "@recparam r R",
        "int f_sized(const struct r *r, uint32_t r_nbytes);",
        "the size 'r_nbytes' of 'r' is not a size_t",
    ),
    (
        "@recparam r R\n * @arrparam v V @len_at{r_nbytes}",
        "int f_sized(const int *v, const struct r *r, size_t r_nbytes);",
        "the size 'r_nbytes' of 'r' is the length of an array too",
    ),
    (
        "@param r R @nbytes_at{n}",
        "int f_sized(const struct r *r, size_t n);",
        "'r' has @nbytes_at, but is documented by @param",
    ),
    (
        "@recparam r R",
        "int f_whole(const struct r *r, size_t r_nbytes);",
        "@recparam, but the name does not end in '_sized'",
    ),
    (
        "@recparam a A\n * @recparam b B",
        "int g_sized(const struct r *a, size_t a_nbytes, const struct r *b,"
        " size_t b_nbytes);",
        "@recparam, but the headers have no static inline 'g' that passes the size",
    ),
    (
        "@recparam[out] r R",
        "int f_sized(const struct r *r, size_t r_nbytes);",
        "@recparam names 'r', which is not [in]",
    ),
    (
        "@recparam a A\n * @recparam b B",
        "int f_sized(const struct r *a, size_t a_nbytes, const struct r *b,"
        " uint32_t b_nbytes);",
        "the size 'b_nbytes' of 'b' is not a size_t",
    ),
    (
        "@recparam r R",
        "int _sized(const struct r *r, size_t r_nbytes);",
        "@recparam, but the name has nothing before '_sized'",
    ),
]


def test_a_recparam_not_of_the_record_arguments_shape_is_reported(parse):
    """Each @recparam whose record, size or function does not have the shape of
    the pattern is reported once, also for a function of two, and no size is
    recorded"""

    for tag, decl, message in WRONG_RECPARAM:
        source = (
            "#include <stddef.h>\n#include <stdint.h>\n"
            "/**\n * R\n */\nstruct r {\n\tint x; ///< X\n};\n"
            "/**\n * U\n */\nunion u {\n\tint x; ///< X\n};\n"
            "struct o;\n"
            "/**\n * F\n */\nstatic inline int f(void) { return 0; }\n"
            f"/**\n * F\n *\n * {tag}\n */\n{decl}\n"
        )
        model, diagnostics = parse(source)
        found = [d.message for d in diagnostics if d.rule == "annotation"]
        assert sum(message in m for m in found) == 1, (decl, found)
        assert not any("@param names" in m for m in found), (decl, found)
        (func,) = functions(model).values()
        assert [p.name for p in func.params if p.size] == []


def test_two_records_of_one_size_are_reported_and_no_size_is_kept(parse):
    model, diagnostics = parse(
        "#include <stddef.h>\n"
        "/**\n * R\n */\nstruct r {\n\tint x; ///< X\n};\n"
        "/**\n * F\n */\nstatic inline int f(void) { return 0; }\n"
        "/**\n * F\n *\n * @recparam a A @nbytes_at{n}\n"
        " * @recparam b B @nbytes_at{n}\n */\n"
        "int f_sized(const struct r *a, const struct r *b, size_t n);\n"
    )
    found = [d.message for d in diagnostics if d.rule == "annotation"]
    assert found == ["'f_sized': the size 'n' is the size of two records"]
    assert [p.size for p in functions(model)["f_sized"].params] == [None] * 3


WRONG_ARRPARAM = [
    (
        "@param v V\n * @len v n",
        "void f(const int *v, size_t n);",
        "@len is removed; document the array with @arrparam",
    ),
    (
        "@arrparam x X",
        "void f(const int *v, size_t v_len);",
        "@arrparam names 'x', which is not a parameter",
    ),
    (
        "@arrparam v V",
        "void f(int v, size_t v_len);",
        "@arrparam names 'v', which is not a pointer",
    ),
    (
        "@arrparam v V @nbytes_at{n}",
        "void f(const int *v, size_t v_len, size_t n);",
        "'v' has @nbytes_at, which is of a @recparam",
    ),
    (
        "@arrparam v V",
        "void f(const int *v, int v_len);",
        "the length 'v_len' of 'v' is not an unsigned integer",
    ),
    (
        "@arrparam v V @len_at{n}",
        "void f(const int *v, size_t n, size_t v_len);",
        "@len_at{n} of 'v', but 'v_len' is a parameter too",
    ),
    (
        "@param v V @len_at{n}",
        "void f(const int *v, size_t n);",
        "'v' has @len_at, but is documented by @param",
    ),
    (
        "@param[out] v V @nwritten_at{n}",
        "void f(int *v, uint32_t *n);",
        "'v' has @nwritten_at, but is documented by @param",
    ),
    (
        "@arrparam v V @len_at{n} and @len_at{m}",
        "void f(const int *v, size_t n, size_t m);",
        "'v' has @len_at twice",
    ),
    (
        "@arrparam v V\n * @len_at n",
        "void f(const int *v, size_t n);",
        "@len_at names no parameter; name it in braces",
    ),
    (
        "@arrparam v V\n * @param n N\n *\n * @len_at{n}",
        "void f(const int *v, size_t n);",
        "@len_at{n} is not in the text of an @arrparam or @recparam",
    ),
    (
        "@return R @len_at{n}",
        "int f(const int *v, size_t n);",
        "@len_at{n} is not in the text of an @arrparam or @recparam",
    ),
    (
        "@arrparam[out] v V",
        "void f(const int *v, size_t v_len);",
        "'v' is [out] but points to const, which the function cannot write",
    ),
    (
        "@param[in,out] v V",
        "void f(const int *v);",
        "'v' is [inout] but points to const, which the function cannot write",
    ),
    (
        "@arrparam[out] a A\n * @arrparam[out] a_nwritten W",
        "void f(int *a, size_t a_len, size_t *a_nwritten, size_t a_nwritten_len);",
        "the count written 'a_nwritten' of 'a' is an @arrparam",
    ),
    (
        "@param v V @len_at{n}\n * @arrparam v W",
        "void f(const int *v, size_t n);",
        "'v' is documented twice, by @arrparam or @recparam and another tag",
    ),
    (
        "@arrparam v V @len_at{n}\n * @arrparam v W @len_at{m}",
        "void f(const int *v, size_t n, size_t m);",
        "'v' has @len_at twice",
    ),
]


def test_an_arrparam_or_marker_in_the_comment_of_no_function_is_reported(parse):
    _, diagnostics = parse(
        "/**\n * A point @len_at{x}\n */\nstruct api_point {\n"
        "\tint x; ///< The x @nbytes_at{y}\n\tint y; ///< The y\n};\n"
        "/**\n * A callback\n *\n * @arrparam vals The values @len_at{n}\n"
        " * @param n Count @nwritten_at\n * @param ctx Context\n */\n"
        "typedef void (*api_cb)(const int *vals, unsigned n, void *ctx);\n"
        "/**\n * Outer\n */\nstruct api_outer {\n"
        "\tstruct {\n\t\tint a; ///< A @len_at{b}\n\t} in; ///< In\n};\n"
    )
    found = sorted((d.message, d.line) for d in diagnostics if d.rule == "annotation")
    assert found == [
        ("'api_cb': @arrparam vals is in the comment of no function", 15),
        ("'api_cb': @len_at{n} is in the comment of no function", 15),
        ("'api_cb': @nwritten_at is in the comment of no function", 15),
        ("'api_outer_in': @len_at{b} is in the comment of no function", 20),
        ("'api_point': @len_at{x} is in the comment of no function", 4),
        ("'api_point': @nbytes_at{y} is in the comment of no function", 4),
    ]


def test_a_context_documented_as_an_array_keeps_no_length_nor_count(parse):
    model, diagnostics = parse(
        "#include <stdint.h>\n"
        "/**\n * C\n */\ntypedef void (*api_cb)(void *arg, int v);\n"
        "/**\n * Run\n * @arrparam[out] arg A\n * @param[out] arg_nwritten W\n"
        " * @lifetime cb call\n */\n"
        "void api_run(api_cb cb, void *arg, uint32_t arg_len,\n"
        "             uint32_t *arg_nwritten);\n"
    )
    found = [d.message for d in diagnostics if d.rule == "annotation"]
    assert found == [
        "'api_run': 'arg' is the context of 'cb', which the binding passes; a"
        " context is no @arrparam"
    ]
    arg = functions(model)["api_run"].params[1]
    assert (arg.length, arg.count) == (None, None)


def test_an_arrparam_or_marker_out_of_place_is_reported_once(parse):
    for tag, decl, message in WRONG_ARRPARAM:
        source = (
            "#include <stddef.h>\n#include <stdint.h>\n"
            f"/**\n * F\n *\n * {tag}\n */\n{decl}\n"
        )
        _, diagnostics = parse(source)
        found = [d.message for d in diagnostics if d.rule == "annotation"]
        assert sum(message in m for m in found) == 1, (decl, found)


BUFFERS = """
#include <stddef.h>

/** D */
struct dev;

/**
 * Allocate
 * @param dev D
 * @param nbytes N
 * @nullable return
 */
void *b_buf_alloc(const struct dev *dev, size_t nbytes);

/**
 * Resize
 * @param dev D
 * @param buf B
 * @param nbytes N
 * @nullable return
 */
void *b_buf_realloc(const struct dev *dev, void *buf, size_t nbytes);

/**
 * Free
 * @param dev D
 * @param buf B
 */
void b_buf_free(const struct dev *dev, void *buf);

/**
 * Allocate, aligned
 * @param alignment A
 * @param nbytes N
 */
void *b_virt_alloc(size_t alignment, size_t nbytes);

/**
 * Free
 * @param buf B
 */
void b_virt_free(void *buf);

/**
 * Register
 * @param dev D
 * @param vaddr V
 * @param nbytes N
 * @errno
 */
int b_buf_register(const struct dev *dev, void *vaddr, size_t nbytes);

/**
 * Unregister
 * @param dev D
 * @param vaddr V
 * @errno
 */
int b_buf_unregister(const struct dev *dev, void *vaddr);
"""


def test_the_buffer_pattern_is_recognised_by_its_names(parse):
    """xNVMe's buffers: an allocation freed and resized with the device it was
    allocated with, one without a device, and a registration"""

    model, diagnostics = parse(BUFFERS, meta={"prefix": "b"})
    assert "buffer-lifecycle" not in [d.rule for d in diagnostics]
    found = {
        name: (f.memory.role, f.memory.stem, f.memory.ptr, f.memory.nbytes)
        for name, f in functions(model).items()
        if f.memory
    }
    assert found == {
        "b_buf_alloc": ("alloc", "b_buf", None, "nbytes"),
        "b_buf_realloc": ("realloc", "b_buf", "buf", "nbytes"),
        "b_buf_free": ("free", "b_buf", "buf", None),
        "b_virt_alloc": ("alloc", "b_virt", None, "nbytes"),
        "b_virt_free": ("free", "b_virt", "buf", None),
        "b_buf_register": ("register", "b_buf", "vaddr", "nbytes"),
        "b_buf_unregister": ("unregister", "b_buf", "vaddr", None),
    }


def test_a_buffer_nothing_releases_is_reported_and_not_marked(parse):
    header = (
        "#include <stddef.h>\n"
        "/**\n * A\n * @param nbytes N\n */\nvoid *c_one_alloc(size_t nbytes);\n"
        "/**\n * A\n * @param n N\n */\nvoid *c_two_alloc(size_t n);\n"
        "/**\n * A\n * @param nbytes N\n */\nvoid *c_three_alloc(size_t nbytes);\n"
        "/**\n * F\n * @param buf B\n * @param flags F\n */\n"
        "void c_three_free(void *buf, int flags);\n"
        "/**\n * R\n * @param p P\n * @param nbytes N\n */\n"
        "int c_four_register(void *p, size_t nbytes);\n"
        "/**\n * R\n * @param p P\n * @param nbytes N\n * @errno\n */\n"
        "int c_five_register(void *p, size_t nbytes);\n"
    )
    model, diagnostics = parse(header, meta={"prefix": "c"})
    messages = [d.message for d in diagnostics if d.rule == "buffer-lifecycle"]
    assert messages == [
        "'c_one_alloc' allocates a buffer, which no 'c_one_free' frees",
        "'c_two_alloc' returns a buffer, but has no size_t 'nbytes'",
        "'c_three_free' does not free a buffer: it takes one void *, and its other"
        " parameters are those of 'c_three_alloc'",
        "'c_four_register' registers a buffer, but is not documented @errno",
        "'c_five_register' registers a buffer, which no 'c_five_unregister'"
        " unregisters",
    ]
    assert not any(f.memory for f in functions(model).values())
