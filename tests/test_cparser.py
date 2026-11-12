# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import platform
import shutil
import subprocess

import pytest

from tests.conftest import (
    ESCAPED,
    ESCAPED_VALUE,
    FLEXIBLE,
    HEADERS,
    PACKED,
    SKIPPED,
    needs_cc,
)
from yace.compiler import process
from yace.ir import cparser, decls, types
from yace.ir.cparser import CParser, MissingHeader


def rules(diagnostics):
    return sorted({d.rule for d in diagnostics})


def test_the_subset_gives_no_diagnostics(parser):
    model, diagnostics = parser.parse(HEADERS / "valid.h")
    assert [str(d) for d in diagnostics] == []

    names = [getattr(e, "name", None) for e in model.entities]
    for name in (
        "VALID_NAME",
        "VALID_SHIFTED",
        "valid_opt",
        "valid_handle",
        "valid_point",
        "valid_visit_cb",
        "valid_all",
        "valid_either",
        "valid_open",
        "valid_fill",
    ):
        assert name in names


def test_types_of_the_subset(parser):
    model, _ = parser.parse(HEADERS / "valid.h")
    fields = {f.name: f.typ for f in model.find("valid_all").fields}

    assert fields["letter"] == types.Builtin(name="char")
    assert fields["schar"] == types.Builtin(name="signed char")
    assert fields["u64"] == types.Builtin(name="uint64_t")
    assert fields["size"] == types.Builtin(name="size_t")
    assert fields["grid"] == types.Array(
        of=types.Array(of=types.Builtin(name="int32_t"), length=3), length=2
    )
    assert fields["at"] == types.Record(tag="struct", name="valid_point")
    assert types.is_string(fields["label"])
    assert fields["ref"] == types.Pointer(
        to=types.Record(tag="struct", name="valid_point", const=True)
    )
    assert fields["visit"] == types.TypedefRef(name="valid_visit_cb")

    visit = model.find("valid_visit_cb").typ
    assert [p.name for p in visit.to.params] == ["arg", "value"]

    handle = model.find("valid_handle")
    assert isinstance(handle, decls.Struct) and handle.fields == []


def test_values_and_docs(parser):
    model, _ = parser.parse(HEADERS / "valid.h")

    assert model.find("VALID_NAME").value == decls.StrLiteral(value="valid")
    assert model.find("VALID_MAGIC").value == decls.IntLiteral(value=0xACDC, base=16)
    assert model.find("VALID_SHIFTED").value.value == 16
    assert model.find("VALID_ALIAS").value.value == 42
    assert [m.value for m in model.find("valid_opt").members] == [1, 2, -1]

    open_ = model.find("valid_open")
    assert open_.doc.brief == "Open a handle"
    assert set(open_.doc.params) == {"path", "handle"}
    assert model.find("VALID_MAX").doc.brief == "A decimal constant"


def test_layout_is_recorded(parser):
    model, _ = parser.parse(HEADERS / "valid.h")
    point = model.find("valid_point")
    assert (point.size, point.align) == (8, 4)
    assert [f.offset for f in point.fields] == [0, 32]


VIOLATIONS = [
    ("anonymous-record", "struct s { union { int a; float b; }; int c; };"),
    ("anonymous-record", "typedef struct { int x; } point;"),
    ("anonymous-record", "struct s { struct { int x; } at; };"),
    ("anonymous-record", "enum { A = 1, B = 2 };"),
    ("nested-record", "struct outer { struct inner { int a; } in; };"),
    ("bitfield", "struct s { unsigned int a : 3; };"),
    ("flexible-array", "#include <stddef.h>\nstruct s { size_t n; int data[]; };"),
    ("array-parameter", "int f(int values[4]);"),
    ("variadic-function", "int f(const char *fmt, ...);"),
    ("record-by-value", "struct p { int x; };\nint f(struct p at);"),
    ("record-by-value", "struct p { int x; };\nstruct p f(void);"),
    ("enum-in-signature", "enum e { A };\nint f(enum e opt);"),
    ("typedef", "typedef unsigned int handle;"),
    ("callback-name", "typedef int (*visitor)(int value);"),
    ("callback-param-name", "typedef int (*visit_cb)(int);"),
    ("function-like-macro", "#define TWICE(x) ((x) * 2)"),
    ("macro-value", "#define RATIO 1.5"),
    ("unsupported-type", "long double f(void);"),
    ("unsupported-declaration", "extern int counter;"),
    ("unsupported-declaration", "static inline int f(void) { return 1; }"),
    ("external-type", "#include <stdio.h>\nint f(FILE *stream);"),
    ("missing-doc", "int f(void);"),
    ("doc-comment", "/** Stray */\n/** F */\nint f(void);"),
    ("doc-comment", "/** Stray */\n/// F\nint f(void);"),
    ("doc-comment", "/** Stray */ /** F */\nint f(void);"),
    ("param-name", "/** F */\nint f(int, const char *);"),
    ("callback-typedef", "/** F */\nint f(int (*cb)(void *a, int v), void *a);"),
    ("callback-typedef", "/** S */\nstruct s {\n\tvoid (*h[2])(void *a); ///< H\n};"),
    ("callback-typedef", "/** F */\nint (*f(void))(void *a);"),
    ("callback-typedef", "/** F */\nint f(int (**cb)(void *a), void *a);"),
    ("callback-typedef", "/** O */\ntypedef int (*o_cb)(void *a, int (*in)(void *b));"),
    ("enum-value", "/** E */\nenum e { E_BIG = 0x80000000 };"),
    ("cxx-keyword", "/** S */\nstruct s { int class; };"),
    ("attribute", "/** F */\n__attribute__((warn_unused_result)) int f(void);"),
    ("attribute", "struct __attribute__((aligned(8))) s { char c; int i; };"),
    ("parse-error", "int f(unknown_t x);"),
    ("string-return", "char *f(void);"),
    ("callback-context", "typedef int (*visit_cb)(int value);"),
    ("callback-context", "typedef int (*v_cb)(void *a, void *b);"),
    ("callback-context", "typedef int (*v_cb)(void *arg);\nint f(v_cb visit);"),
    ("callback-context", "int f(int (*cb)(void *a, void *b), void *arg);"),
    (
        "annotation",
        "#include <stddef.h>\ntypedef int (*v_cb)(void *a);\n"
        "/**\n * @len ctx n\n */\nint f(v_cb cb, void *ctx, size_t n);",
    ),
    ("annotation", "/**\n * @param[out] x X\n */\nint f(int x);"),
    (
        "annotation",
        "/**\n * F\n * @len p n p m\n */\nint f(const int *p, int n, int m);",
    ),
    ("annotation", "/**\n * @lifetime x call\n */\nint f(int x);"),
    (
        "annotation",
        "typedef int (*v_cb)(void *a);\n/**\n * @lifetime cb\n */\n"
        "int f(v_cb cb, void *a);",
    ),
    (
        "annotation",
        "typedef int (*v_cb)(void *a);\n/**\n * @lifetime cb ever\n */\n"
        "int f(v_cb cb, void *a);",
    ),
    (
        "annotation",
        "typedef int (*v_cb)(void *a);\n/**\n * @lifetime cb handle\n */\n"
        "int f(v_cb cb, void *a);",
    ),
    ("callback-lifetime", "typedef int (*v_cb)(void *a);\nint f(v_cb cb, void *a);"),
    (
        "annotation",
        "typedef int (*v_cb)(void *a);\n/**\n * @lifetime cb call cb once\n */\n"
        "int f(v_cb cb, void *a);",
    ),
    (
        "annotation",
        "#include <stdio.h>\ntypedef int (*v_cb)(void *a);\n"
        "/**\n * @lifetime cb handle\n */\nint f(FILE *s, v_cb cb, void *a);",
    ),
    ("annotation", "/**\n * @param[inout] x X\n */\nint f(int *x);"),
    ("annotation", "struct h;\n/**\n * @param[out] h H\n */\nint f(struct h *h);"),
    ("annotation", "struct h;\n/**\n * @destroys h\n */\nvoid f(struct h *h, int x);"),
    ("annotation", "/**\n * @param y Y\n */\nint f(int x);"),
    ("annotation", "/**\n * @nullable x\n */\nint f(int x);"),
    ("annotation", "/**\n * @nullable return\n */\nint f(void);"),
    ("annotation", "/**\n * @len p\n */\nint f(int *p);"),
    ("annotation", "/**\n * @len p n\n */\nint f(int *p, float n);"),
    (
        "annotation",
        "/**\n * @len cb n\n */\nint f(int (*cb)(void *a, int v), void *a, int n);",
    ),
    ("annotation", "/**\n * @errno\n */\nunsigned int f(void);"),
    ("annotation", "/**\n * @destroys x\n */\nvoid f(int *x);"),
    (
        "handle-lifecycle",
        "struct h;\n/**\n * @param[out] h H\n */\nint f(struct h **h);",
    ),
]


@pytest.mark.parametrize("rule,source", VIOLATIONS, ids=[v[0] for v in VIOLATIONS])
def test_each_rule_is_reported(parse, rule, source):
    _, diagnostics = parse(source)
    assert rule in rules(diagnostics), [str(d) for d in diagnostics]


def test_diagnostics_say_where(parse):
    _, diagnostics = parse("/** doc */\nstruct s { unsigned int a : 3; };\n")
    (bitfield,) = [d for d in diagnostics if d.rule == "bitfield"]
    assert (bitfield.file, bitfield.line) == ("api.h", 2)


def test_anonymous_member_is_hoisted_with_its_offset(parse):
    model, _ = parse(
        "#include <stdint.h>\n"
        "struct s { uint32_t tag; union { uint64_t i; double f; }; };\n"
    )
    hoisted = model.find("s_anon0")
    outer = model.find("s")

    assert isinstance(hoisted, decls.Union)
    assert [f.name for f in outer.fields] == ["tag", "anon0"]
    assert outer.fields[1].typ == types.Record(tag="union", name="s_anon0")
    assert outer.fields[1].offset == 64
    assert outer.size == 16
    assert model.entities.index(hoisted) < model.entities.index(outer)


def test_nested_record_is_hoisted_before_its_user(parse):
    model, _ = parse("struct outer { struct inner { int a; } in; int b; };")
    names = [e.name for e in model.entities]
    assert names == ["inner", "outer"]


def test_typedef_names_an_anonymous_record(parse):
    model, _ = parse("typedef struct { int x; } point;\nint f(const point *p);")
    assert model.find("point").fields[0].name == "x"
    assert model.find("f").params[0].typ == types.Pointer(
        to=types.Record(tag="struct", name="point", const=True)
    )
    assert not any(isinstance(e, decls.Typedef) for e in model.entities)


def test_typedef_of_an_array(parse):
    model, _ = parse(
        "#include <stdint.h>\ntypedef uint8_t mac[6];\nstruct addr { mac m; };"
    )
    assert model.find("mac").typ == types.Array(
        of=types.Builtin(name="uint8_t"), length=6
    )
    assert model.find("addr").size == 6


def test_plain_char_stays_char(parse):
    model, diagnostics = parse("int f(char *buf, unsigned long len);")
    assert model.find("f").params[0].typ == types.Pointer(to=types.Builtin(name="char"))
    assert "unsupported-type" not in rules(diagnostics)


def test_anonymous_enum_members_become_constants(parse):
    model, _ = parse("enum { LOW = 1, HIGH = 2 };")
    assert [(e.name, e.value.value) for e in model.entities] == [
        ("LOW", 1),
        ("HIGH", 2),
    ]


def test_include_guard_and_empty_macros_are_ignored(parse):
    model, diagnostics = parse("#ifndef API_H\n#define API_H\n#endif\n")
    assert model.entities == []
    assert diagnostics == []


def test_defines_keep_values_beyond_a_long(parse):
    model, diagnostics = parse(
        "/** B */\n#define API_BIG 0xFFFFFFFFFFFFFFFF\n"
        "/** N */\n#define API_NEG (-5)\n/** W */\n#define API_WIDE 0x80000000\n"
    )
    assert diagnostics == []
    assert model.find("API_BIG").value.value == 2**64 - 1
    assert model.find("API_NEG").value.value == -5
    assert model.find("API_WIDE").value.value == 2**31


def test_string_defines_keep_bytes_that_are_not_utf8(parse):
    from yace.targets.capi.target import string_literal

    model, _ = parse('/** S */\n#define API_S "a\\376b"\n')
    assert string_literal(model.find("API_S").value.value) == '"a\\376b"'


def test_function_pointers_in_parameters_keep_their_names(parse):
    model, _ = parse(
        "/** O */\ntypedef void (*api_outer_cb)(void (*inner)(int y), void *arg);\n"
    )
    inner = model.find("api_outer_cb").typ.to.params[0]
    assert inner.name == "inner" and inner.typ.to.params[0].name == "y"


def test_a_record_typedef_with_two_names_keeps_both(parse):
    model, diagnostics = parse(
        "/** S */\ntypedef struct { int a; } one_t, two_t;\n"
        "/** F */\nvoid f(two_t *p);\n"
    )
    assert model.find("one_t") is not None and model.find("two_t") is not None
    assert model.find("f").params[0].typ.to.name == "two_t"
    assert "typedef" in [d.rule for d in diagnostics]


def test_names_of_cxx_and_attributes_are_reported_where_they_are(parse):
    _, diagnostics = parse(
        "/** R */\nstruct api_rec {\n\tint class; ///< C\n};\n"
        "/** F */\nint api_f(void) __attribute__((deprecated));\n"
    )
    found = {d.rule: (d.line, d.message) for d in diagnostics}
    assert found["cxx-keyword"][0] == 3
    assert found["attribute"] == (
        6,
        "'api_f' has the attribute 'deprecated'; it is ignored",
    )


def test_a_record_with_a_flexible_array_in_an_array_or_struct(parse):
    model, diagnostics = parse(FLEXIBLE)
    found = [d.message for d in diagnostics if d.rule == "flexible-array"]
    nested = (
        "which has a flexible array member: ISO C allows such a record neither"
        " in an array nor in a struct"
    )
    assert found == [
        "field 'd' of 'api_fin' is a flexible array",
        "field 'd' of 'api_fwide' is a flexible array",
        f"field 'in' of 'api_fout' is an array of 'struct api_fin', {nested};"
        " the field is left out",
        f"field 'in' of 'api_falign' is an array of 'struct api_fwide', {nested};"
        " leaving the field out would change the alignment of 'api_falign',"
        " which is skipped",
        f"field 'in' of 'api_fmember' is a 'struct api_fin', {nested};"
        " 'api_fmember' is skipped",
        f"field 'e' of 'api_farr' is an array of 'union api_feither', {nested};"
        " 'api_farr' is skipped",
    ]
    out = model.find("api_fout")
    assert [f.name for f in out.fields] == ["n"]
    assert (out.size, out.align) == (4, 4)
    assert [f.name for f in model.find("api_feither").fields] == ["in", "n"]
    for name in ("api_falign", "api_fmember", "api_farr", "api_fuse"):
        assert model.find(name) is None


def test_a_packed_record_is_recorded_as_packed(parse):
    model, diagnostics = parse(
        PACKED + "/** A */\nstruct api_a {\n\tuint8_t c; ///< C\n"
        "\tuint32_t i; ///< I\n} __attribute__((__packed__));\n"
        "/** S */\nstruct __attribute__((aligned(8))) api_s {\n\tint i; ///< I\n};\n"
    )
    assert [str(d).split(": ", 1)[1] for d in diagnostics] == [
        "attribute: 'api_s' has the attribute 'aligned'; it is ignored"
    ]

    k = model.find("api_k")
    assert (k.packed, k.size, k.align) == (True, 35, 1)
    assert [f.offset // 8 for f in k.fields] == [0, 1, 5, 13, 29, 33]
    assert [model.find(n).packed for n in ("api_p", "api_ku", "api_a")] == [
        False,
        True,
        True,
    ]
    assert (model.find("api_ku").size, model.find("api_ku").align) == (8, 1)


def test_a_rejected_lifetime_is_reported_once(parse):
    _, diagnostics = parse(
        "/** C */\ntypedef int (*api_cb)(void *a);\n"
        "/**\n * F\n * @lifetime cb handle\n */\nint api_f(api_cb cb, void *a);\n"
    )
    assert [d.rule for d in diagnostics] == ["annotation"]


def test_defines_documented_with_exclamation_marks(parse):
    _, diagnostics = parse("//! Line\n#define API_A 1\n/*! Block */\n#define API_B 2\n")
    assert diagnostics == []


def test_forward_declaration_of_a_defined_record_is_not_opaque(parse):
    model, _ = parse("struct s;\nstruct s { int a; };")
    assert [(e.name, len(e.fields)) for e in model.entities] == [("s", 1)]


def test_a_typedef_of_another_type_by_its_records_name_is_that_type(parse):
    model, diagnostics = parse(
        "struct node { int v; };\ntypedef struct node *node;\n"
        "int f(node n);\ntypedef struct node node_t;\n"
    )
    assert [e.name for e in model.entities] == ["node", "f", "node_t"]
    assert model.find("f").params[0].typ == types.Pointer(
        to=types.Record(tag="struct", name="node")
    )
    (typedef,) = [
        d for d in diagnostics if d.rule == "typedef" and "'node'" in d.message
    ]
    assert "its type is used in its place" in typedef.message


def test_an_array_typedef_by_its_records_name_is_that_array(parse):
    model, _ = parse(
        "struct node { int v; };\ntypedef struct node node[2];\n"
        "struct holder { node n; const node c; };\n"
    )
    record = types.Record(tag="struct", name="node")
    held = {f.name: f.typ for f in model.find("holder").fields}
    assert held["n"] == types.Array(of=record, length=2)
    assert held["c"] == types.Array(
        of=record.model_copy(update={"const": True}), length=2
    )


def test_a_typedef_of_its_own_record_is_that_record_where_used(parse):
    model, diagnostics = parse(
        "typedef struct h h;\ntypedef enum e { E_A = 1 } e;\nint f(const h *p, e v);"
    )
    params = model.find("f").params
    assert params[0].typ == types.Pointer(
        to=types.Record(tag="struct", name="h", const=True)
    )
    assert params[1].typ == types.EnumRef(name="e")
    assert [e.name for e in model.entities if isinstance(e, decls.Typedef)] == [
        "h",
        "e",
    ]
    assert "typedef" not in rules(diagnostics)


def test_the_uses_of_a_skipped_typedef_are_skipped(parse):
    model, diagnostics = parse(
        "typedef struct { int b; } *p;\nstruct s { p at; };\nint f(p v);\nint g(void);"
    )
    assert [e.name for e in model.entities] == ["g"]
    assert any("'f'" in d.message and "skipped" in d.message for d in diagnostics)
    assert any("'s'" in d.message and "skipped" in d.message for d in diagnostics)


def test_the_uses_of_a_skipped_record_are_skipped(parse):
    model, diagnostics = parse(
        "struct r { long double x; };\ntypedef struct { long double x; } a;\n"
        "int f(struct r *v);\nint g(a *v);\nint h(void);"
    )
    assert [e.name for e in model.entities] == ["h"]
    for name in ("'f'", "'g'"):
        assert any(name in d.message and "skipped" in d.message for d in diagnostics)


def test_a_typedef_of_its_own_record_and_the_record_share_a_doc(parse):
    for text in (
        "/** A handle */\ntypedef struct h h;\n",
        "/** A handle */\nstruct h;\ntypedef struct h h;\n",
    ):
        model, diagnostics = parse(text)
        assert [e.doc.brief for e in model.entities] == ["A handle", "A handle"]
        assert "missing-doc" not in rules(diagnostics)


def test_what_uses_a_skipped_record_before_it_is_skipped_too(parse):
    model, diagnostics = parse(SKIPPED)
    names = [e.name for e in model.entities]
    assert names == [
        "sys/time.h",
        "pthread.h",
        "sys/types.h",
        "stdint.h",
        "stdarg.h",
        "setjmp.h",
        "api_inner",
        "api_inner_a",
        "api_nest",
        "api_host",
        "api_flags",
        "api_flags_b",
        "api_now",
        "api_z",
        "api_m",
        "api_m_b",
        "api_o",
        "api_holder",
        "api_proc",
        "api_seek",
        "api_bytes",
        "api_many",
        "api_mix",
        "api_packed",
        "api_mix_b",
        "api_pk1",
        "api_pk2",
        "api_chars",
        "api_pk",
        "api_jump",
        "api_fin",
        "api_fwide",
        "api_feither",
        "api_fout",
    ]
    skipped = ["api_before", "api_after", "api_t", "api_t_n", "api_lock", "api_lock_n"]
    for name in skipped + ["api_tick_cb", "api_pad", "api_pad_n"]:
        assert any(
            f"'{name}'" in d.message and "skipped" in d.message for d in diagnostics
        )
    flags = model.find("api_flags")
    assert [(f.name, f.bits) for f in flags.fields] == [("a", 4), ("", 4), ("b", 8)]
    assert model.find("api_o").doc.brief == "O"
    assert any("'va_list', which no binding passes" in d.message for d in diagnostics)
    assert isinstance(model.find("api_jump").params[0].typ, types.Pointer)


def test_typedefs_from_another_header_are_their_types(parser, tmp_path):
    (tmp_path / "other.h").write_text(
        "#include <sys/types.h>\nstruct other_doc;\n"
        "typedef struct other_doc *other_doc_ptr;\n"
        "typedef int (*other_compar_fn)(const void *a, const void *b);\n"
        "typedef unsigned char other_uuid[16];\n"
    )
    (tmp_path / "api.h").write_text(
        '#include "other.h"\nstruct api_rec { other_doc_ptr doc; other_compar_fn cmp;'
        " other_uuid id; pid_t pid; };\n"
    )
    model, _ = parser.parse(tmp_path / "api.h")
    doc, cmp, uid, pid = [f.typ for f in model.find("api_rec").fields]
    assert doc == types.Pointer(to=types.Record(tag="struct", name="other_doc"))
    assert isinstance(cmp, types.Pointer) and isinstance(cmp.to, types.FunctionType)
    assert uid == types.Array(of=types.Builtin(name="unsigned char"), length=16)
    assert pid == types.Builtin(name="int")


def test_a_record_defined_nested_lacks_a_doc_once(parse):
    _, diagnostics = parse(
        "/** O */\nstruct o { struct i { int a; } in; };\n"
        "struct f;\n/** H */\nstruct h { struct f { int a; } at; };\n"
    )
    missing = [d.message for d in diagnostics if d.rule == "missing-doc"]
    assert missing == ["struct 'i' has no doc", "struct 'f' has no doc"]


def test_an_enum_from_another_header_is_its_integer(parser, tmp_path):
    (tmp_path / "other.h").write_text("enum other_e { OTHER_A, OTHER_B };\n")
    (tmp_path / "api.h").write_text(
        '#include "other.h"\nstruct api_a { enum other_e e; int n; };\n'
        "int api_f(enum other_e e);\n"
    )
    model, _ = parser.parse(tmp_path / "api.h")
    assert model.find("api_a").fields[0].typ == types.Builtin(name="unsigned int")
    assert model.find("api_f").params[0].typ == types.Builtin(name="unsigned int")


def test_string_defines_hold_the_value_of_the_literal(parse):
    model, _ = parse(ESCAPED)
    assert model.find("API_S").value.value == ESCAPED_VALUE


def test_a_doc_mentioning_a_doc_comment_is_one(parse):
    _, diagnostics = parse("/**\n * F, which a /** opens\n */\nint f(void);")
    assert "doc-comment" not in [d.rule for d in diagnostics]


def headers(tmp_path, **sources):
    """Write each source as '<name>.h' in 'tmp_path'; returns their paths"""

    paths = []
    for name, source in sources.items():
        path = tmp_path / f"{name}.h"
        path.write_text(source)
        paths.append(path)
    return paths


# An API of two headers: 'api_b.h' includes 'api_a.h' and uses what it declares
API_A = (
    "#ifndef API_A_H\n#define API_A_H\n#include <stdint.h>\n"
    "/** Length */\n#define API_LEN 4\n"
    "/** A */\nstruct api_a {\n\tuint32_t n; ///< N\n};\n#endif\n"
)
API_B = (
    '#ifndef API_B_H\n#define API_B_H\n#include "api_a.h"\n'
    "/** Twice */\n#define API_TWICE (API_LEN * 2)\n"
    "/**\n * B\n *\n * @param a A\n * @return N\n */\n"
    "uint32_t api_b(struct api_a *a);\n"
    "#endif\n"
)


def test_the_headers_given_are_one_api(parser, tmp_path):
    model, diagnostics = parser.parse(headers(tmp_path, api_a=API_A, api_b=API_B))

    assert [str(d) for d in diagnostics] == []
    names = {"stdint.h", "API_LEN", "api_a", "API_TWICE", "api_b"}
    assert {e.name for e in model.entities} == names
    ordered = [e.name for e in model.entities if e.name in ("api_a", "api_b")]
    assert ordered == ["api_a", "api_b"]
    assert model.find("API_TWICE").value.value == 8
    assert model.find("API_TWICE").doc.brief == "Twice"
    assert model.meta.headers == ["api_a.h", "api_b.h"]
    assert model.meta.source() == "api_a.h and 1 other header"


def test_a_header_included_but_not_given_is_external(parser, tmp_path):
    _, b = headers(tmp_path, api_a=API_A, api_b=API_B)
    model, diagnostics = parser.parse([b])

    assert {e.name for e in model.entities} == {"api_a.h", "API_TWICE", "api_b"}
    assert "external-type" in rules(diagnostics)


# An API of two headers that include nothing: 'api_n.h' uses what 'api_m.h'
# declares, and both the standard types that yace includes before them
API_M = (
    "/** M */\nstruct api_m {\n\tuint32_t v; ///< V\n};\n"
    "/** M */\ntypedef struct api_m api_m;\n"
)
API_N = (
    "/**\n * N\n *\n * @param m M\n * @param len Length\n * @return Whether\n */\n"
    "bool api_n(api_m *m, size_t len);\n"
)


def test_a_header_may_use_what_one_given_before_it_declares(parser, tmp_path):
    model, diagnostics = parser.parse(headers(tmp_path, api_m=API_M, api_n=API_N))

    assert [str(d) for d in diagnostics] == []
    assert [e.name for e in model.entities] == ["api_m", "api_m", "api_n"]
    params = model.find("api_n").params
    assert params[0].typ == types.Pointer(to=types.Record(tag="struct", name="api_m"))
    assert params[1].typ == types.Builtin(name="size_t")


def test_a_header_using_a_type_before_its_header_is_given_is_reported(parser, tmp_path):
    m, n = headers(tmp_path, api_m=API_M, api_n=API_N)
    _, diagnostics = parser.parse([n, m])

    assert [d.rule for d in diagnostics] == ["parse-error"]
    assert diagnostics[0].file == "api_n.h"
    assert diagnostics[0].message == "unknown type name 'api_m'"


def test_gccs_headers_serve_where_clang_has_none(tmp_path, monkeypatch):
    """The libclang package ships no stddef.h; with no clang installed, gcc's
    give the same layouts"""

    gcc = CParser._gcc_include()
    if gcc is None:
        pytest.skip("no gcc")
    header = tmp_path / "api_l.h"
    header.write_text(
        "/** L */\nstruct api_l {\n\tbool b; ///< B\n\tsize_t n; ///< N\n"
        "\tuint16_t u; ///< U\n};\n"
    )
    found = CParser().parse(header)
    monkeypatch.setattr(CParser, "_clang_builtin_include", staticmethod(lambda: gcc))
    model, diagnostics = CParser().parse(header)

    assert [str(d) for d in diagnostics] == []
    assert model.model_dump() == found[0].model_dump()
    assert model.find("api_l").size == 24


def test_gccs_headers_are_found_last(tmp_path, monkeypatch):
    gcc = CParser._gcc_include()
    resource = subprocess.run(["cc", "-print-resource-dir"], capture_output=True)
    if gcc is None or resource.returncode == 0:
        pytest.skip("no gcc, or cc is clang")
    which = shutil.which
    monkeypatch.setattr(
        cparser.shutil, "which", lambda n: None if n == "clang" else which(n)
    )
    monkeypatch.setattr(cparser, "LLVM_LIB", tmp_path)
    monkeypatch.setenv(
        "YACE_SEARCHPATH_LIBCLANG", str(tmp_path / "lib" / "libclang.so")
    )
    monkeypatch.delenv("CC", raising=False)

    assert CParser._clang_builtin_include() == gcc


def test_the_standard_types_need_no_include(parse):
    model, diagnostics = parse(
        "/**\n * F\n *\n * @param a A\n * @return B\n */\n"
        "uint64_t api_f(int8_t a);\n"
    )

    assert [str(d) for d in diagnostics] == []
    assert model.find("api_f").ret == types.Builtin(name="uint64_t")


def test_a_type_from_outside_the_set_is_external_with_no_include(parser, tmp_path):
    paths = headers(
        tmp_path,
        api_o="#include <stdio.h>\n",
        api_p="/**\n * P\n *\n * @param f F\n * @return N\n */\nint api_p(FILE *f);\n",
    )
    _, diagnostics = parser.parse(paths)

    assert [d.rule for d in diagnostics] == ["external-type"]
    assert diagnostics[0].file == "api_p.h"


# Uses what <stdio.h> declares, without including it
API_Q = (
    "/** End of file, and one */\n#define API_EOF1 (EOF + 1)\n"
    "/**\n * Q\n *\n * @param f F\n * @return N\n */\nint api_q(FILE *f);\n"
)


def test_a_prelude_is_included_ahead_of_the_headers(parser, tmp_path):
    paths = headers(tmp_path, api_q=API_Q)
    _, without = parser.parse(paths)
    model, diagnostics = parser.parse(paths, prelude=["stdio.h"])

    assert "parse-error" in rules(without)
    # Which header of the C library declares FILE differs between libcs
    assert len(diagnostics) == 1
    assert str(diagnostics[0]).startswith(
        "api_q.h:9:17: external-type: 'FILE' is declared outside the headers, in "
    )
    assert [e.name for e in model.entities] == ["API_EOF1", "api_q"]
    assert model.find("API_EOF1").value.value == 0
    assert model.meta.prelude == ["stdio.h"]


def test_an_error_in_the_headers_is_reported_once(parser, tmp_path):
    paths = headers(
        tmp_path,
        api_e="/** E */\nint api_e(void) int;\n",
        api_f='#include "api_e.h"\n',
    )
    _, diagnostics = parser.parse(paths)

    assert [str(d) for d in diagnostics] == [
        "api_e.h:2:16: parse-error: expected ';' after top level declarator"
    ]


def test_every_error_of_the_headers_is_reported(parse):
    _, diagnostics = parse("".join(f"api_t{n} v{n};\n" for n in range(30)))
    errors = [d for d in diagnostics if d.rule == "parse-error"]

    assert len(errors) == 30
    assert errors[-1].message == "unknown type name 'api_t29'"


def test_a_header_yace_includes_not_found_stops_the_parse(parser, tmp_path):
    paths = headers(tmp_path, api_q=API_Q)

    with pytest.raises(MissingHeader, match="'yace_nowhere.h' file not found"):
        parser.parse(paths, prelude=["yace_nowhere.h"])


# An API's own printers, as xNVMe's libxnvme_pp.h declares them
OWN_PRINTERS = (
    "/** Formats */\nenum api_pr {\n\tAPI_PR_DEF = 0, ///< D\n"
    "\tAPI_PR_YAML = 1, ///< Y\n\tAPI_PR_TERSE = 2, ///< T\n};\n"
    "/**\n * List\n *\n * @param f F\n * @return N\n */\n"
    "int api_list_pr(enum api_pr f);\n"
    "/** JSON */\n#define API_PR_JSON 4\n"
    "/** S */\nstruct api_s {\n\tint v; ///< V\n};\n"
    "/**\n * Print\n *\n * @param s S\n * @param limit L\n * @param opts O\n"
    " * @return N\n */\nint api_s_pr(const struct api_s *s, int limit, int opts);\n"
    "/** K */\nenum api_k {\n\tAPI_K_A = 0, ///< A\n};\n"
    "/**\n * Name\n *\n * @param k K\n * @return N\n */\n"
    "const char *api_k_str(enum api_k k);\n"
    "/**\n * Q\n *\n * @param x X\n * @return N\n */\nint api_q(int x);\n"
)


def test_what_is_named_as_the_printers_output_formats_is_skipped(parse):
    model, diagnostics = parse(OWN_PRINTERS)

    skipped = "so yace skips"
    assert [str(d) for d in diagnostics] == [
        "api.h:13:5: enum-in-signature: 'api_list_pr' parameter 'f' enum api_pr",
        "api.h:39:13: enum-in-signature: 'api_k_str' parameter 'k' enum api_k",
        "api.h:15:9: printer-name: 'API_PR_JSON' defines API_PR_JSON. The"
        " pretty-printers that yace generates declare the same names,"
        f" {skipped} 'API_PR_JSON' and uses the generated printers",
        "api.h:2:6: printer-name: 'api_pr' declares enum api_pr, API_PR_DEF,"
        " API_PR_TERSE, API_PR_YAML. The pretty-printers that yace generates"
        f" declare the same names, {skipped} 'api_pr' and uses the generated"
        " printers",
        "api.h:28:5: printer-name: 'api_s_pr' has the name of the printer that"
        f" yace generates for 'api_s', {skipped} 'api_s_pr' and uses the"
        " generated printer",
        "api.h:39:13: printer-name: 'api_k_str' has the name of the printer that"
        f" yace generates for 'api_k', {skipped} 'api_k_str' and uses the"
        " generated printer",
        "<header>: unsupported-type: 'api_list_pr' uses 'api_pr', which is"
        " skipped; it is skipped",
    ]
    assert [e.name for e in model.entities] == ["api_s", "api_k", "api_q"]


# An API's own printers, tagged as not bound, and one not named as a printer
NOBIND = (
    "#include <stdio.h>\n"
    "/** A */\nstruct api_a {\n\tint x; ///< X\n};\n"
    "/**\n * Print\n *\n * @param obj A\n * @param opts O\n * @return N\n"
    " *\n * @nobind\n */\nint api_a_pr(const struct api_a *obj, int opts);\n"
    "/**\n * Print to\n *\n * @param stream S\n * @param obj A\n"
    " * @param opts O\n * @return N\n *\n * @nobind\n */\n"
    "int api_a_fpr(FILE *stream, const struct api_a *obj, int opts);\n"
    "/**\n * Dump\n *\n * @param stream S\n * @param obj A\n *\n * @nobind\n */\n"
    "void api_a_dump(FILE *stream, const struct api_a *obj);\n"
)


def test_a_function_tagged_nobind_is_left_out_unreported(parse):
    model, diagnostics = parse(NOBIND)

    assert diagnostics == []
    assert [e.name for e in model.entities] == ["stdio.h", "api_a"]


def test_nobind_with_text_is_reported_and_still_left_out(parse):
    model, diagnostics = parse(
        "/**\n * F\n *\n * @return N\n *\n * @nobind f\n */\nint f(void);\n"
    )

    assert [str(d) for d in diagnostics] == [
        "api.h:8:5: annotation: 'f': @nobind takes nothing"
    ]
    assert model.entities == []


STATIC_PR = (
    "/** T */\nstruct t {\n\tint x; ///< X\n};\n"
    "/**\n * Print\n *\n * @param x T\n *\n * @nobind\n */\n"
    "static inline void t_pr(struct t *x)\n{\n\t(void)x;\n}\n"
)


def test_a_static_inline_function_tagged_nobind_is_left_out_unreported(parse):
    model, diagnostics = parse(STATIC_PR)
    assert diagnostics == []
    assert [e.name for e in model.entities] == ["t"]

    model, diagnostics = parse(STATIC_PR.replace(" *\n * @nobind\n", ""))
    assert [str(d) for d in diagnostics] == [
        "api.h:10:20: unsupported-declaration: 't_pr' is a static or inline"
        " function; it is skipped"
    ]
    assert [e.name for e in model.entities] == ["t"]


def test_an_include_not_found_is_kept(parse):
    model, diagnostics = parse('#include "api_missing.h"\n/** F */\nint f(void);\n')

    assert [e.name for e in model.entities] == ["api_missing.h", "f"]
    assert rules(diagnostics) == ["parse-error"]


def test_an_enum_defined_nowhere_skips_what_uses_it(parse):
    model, diagnostics = parse(
        "/** S @return 0 */\nint s(enum shown mode);\n"
        "/** T @return 0 */\nint t(enum shown *mode);\n"
    )
    assert [str(d).split(": ", 1)[1] for d in diagnostics] == [
        "unsupported-type: 's' uses the type 'enum shown', an enum defined nowhere;"
        " it is skipped",
        "unsupported-type: 't' uses the type 'enum shown', an enum defined nowhere;"
        " it is skipped",
    ]
    assert [getattr(e, "name", None) for e in model.entities] == []


def test_what_uses_a_volatile_type_is_skipped(parse):
    model, diagnostics = parse(
        "/** S @return 0 */\nint s(volatile int *stop);\n"
        "/** A pair */\nstruct pair { volatile int a; };\n"
    )
    assert [str(d).split(": ", 1)[1] for d in diagnostics] == [
        "unsupported-type: 's' uses the type 'volatile int', which is volatile;"
        " it is skipped",
        "unsupported-type: field 'a' of 'pair' has the type 'volatile int', which"
        " is volatile; 'pair' is skipped",
    ]
    assert [getattr(e, "name", None) for e in model.entities] == []


X86_64 = pytest.mark.skipif(
    platform.machine().lower() not in ("x86_64", "amd64"),
    reason="ms_abi is a calling convention of x86-64",
)


@X86_64
def test_a_calling_convention_other_than_c_is_reported_and_skipped(parse):
    model, diagnostics = parse(
        "/**\n * F\n *\n * @param a A\n * @return R\n */\n"
        "int __attribute__((ms_abi)) api_f(int a);\n"
        "/** C */\ntypedef int (*api_cb)(int x) __attribute__((ms_abi));\n"
        "/**\n * G\n *\n * @param a A\n * @return R\n */\n"
        "int __attribute__((sysv_abi)) api_g(int a);\n"
    )
    assert [str(d).split(": ", 1)[1] for d in diagnostics] == [
        "unsupported-type: 'api_f' uses the type 'int (int) __attribute__((ms_abi))',"
        " whose calling convention is not the C one; it is skipped",
        "unsupported-type: typedef 'api_cb' is of the type 'int (int)"
        " __attribute__((ms_abi))', whose calling convention is not the C one; it is"
        " skipped",
    ]
    assert model.find("api_f") is None and model.find("api_cb") is None
    assert model.find("api_g") is not None


PRAGMA_PACK = (
    "#include <stdint.h>\n#pragma pack(push, {n})\n/** P */\nstruct api_p {{\n"
    "\tuint8_t a; ///< A\n\tuint32_t b; ///< B\n}};\n#pragma pack(pop)\n"
)


@needs_cc
def test_a_record_of_pragma_pack_1_is_recorded_as_packed(parse, tmp_path):
    model, diagnostics = parse(PRAGMA_PACK.format(n=1))
    assert diagnostics == []
    record = model.find("api_p")
    assert (record.packed, record.size, record.align) == (True, 5, 1)
    assert process(model, ["capi"], tmp_path / "out") == []


def test_a_record_of_pragma_pack_beyond_1_is_reported_and_skipped(parse):
    model, diagnostics = parse(PRAGMA_PACK.format(n=2))
    assert [str(d).split(": ", 1)[1] for d in diagnostics] == [
        "attribute: 'api_p' is aligned to 2 bytes where its fields need 4, as by"
        " '#pragma pack(2)', which the targets cannot all express; it is skipped"
    ]
    assert model.find("api_p") is None


def test_an_attribute_of_a_field_is_reported(parse):
    _, diagnostics = parse(
        "#include <stdint.h>\n/** Q */\nstruct api_q {\n\tuint8_t a; ///< A\n"
        "\tuint32_t b __attribute__((aligned(8))); ///< B\n};\n"
    )
    assert [str(d).split(": ", 1)[1] for d in diagnostics] == [
        "attribute: field 'b' of 'api_q' has the attribute 'aligned'; it is ignored"
    ]
