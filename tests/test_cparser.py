import pytest

from tests.conftest import ESCAPED, ESCAPED_VALUE, HEADERS, SKIPPED
from yace.ir import decls, types


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
    ("attribute", "struct __attribute__((packed)) s { char c; int i; };"),
    ("parse-error", "int f(unknown_t x);"),
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
