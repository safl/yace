import json
import subprocess

import yaml

from tests.conftest import (
    BITS,
    ESCAPED,
    ESCAPED_VALUE,
    HEADERS,
    PACKED,
    PACKED_PRINTED,
    SKIPPED,
    needs_cc,
    needs_zig,
)
from tests.test_rust import (
    BITS_PRINTED,
    BITS_UNION,
    EDGES,
    HANDLE_NAMED_AS_PREFIX,
    doc,
    misindented_docs,
)
from yace.compiler import process

pytestmark = needs_zig


def json_lines(text):
    return [json.loads(line) for line in text.splitlines()]


@needs_cc
def test_the_subset_prints_as_the_c_api_does(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["capi", "zig"], tmp_path) == []

    for fmt, load in (("yaml", yaml.safe_load_all), ("json", json_lines)):
        c_out = (tmp_path / "capi" / f"check.{fmt}").read_text()
        zig_out = (tmp_path / "zig" / f"check.{fmt}").read_text()
        assert list(load(zig_out)) == list(load(c_out))


@needs_cc
def test_floats_print_as_printf_g_does(parse, tmp_path):
    values = [0.1, -2.5e-5, 1e-4, 123456.0, 1234567.0, 1e300, -0.0, 0.5, 99999.95]
    model, _ = parse("/** Values */\nstruct api_f { double d; float f; };\n")
    assert process(model, ["zig"], tmp_path) == []

    main = tmp_path / "main.zig"
    main.write_text(
        'const std = @import("std");\nconst api = @import("api.zig");\n'
        "pub fn main(init: std.process.Init) !void {\n"
        "    var buf: [4096]u8 = undefined;\n"
        "    var out = std.Io.File.stdout().writer(init.io, &buf);\n"
        + "".join(
            f'    try out.interface.print("{{f}}", .{{api.ApiF{{ .d = {v!r},'
            f" .f = @floatCast(@as(f64, {v!r})) }}}});\n"
            for v in values
        )
        + "    try out.interface.flush();\n}\n"
    )
    (tmp_path / "api.zig").write_text((tmp_path / "zig" / "api.zig").read_text())
    cache = str(tmp_path / ".cache")
    zig = subprocess.run(
        ["zig", "run", "-lc", str(main), "--cache-dir", cache]
        + ["--global-cache-dir", cache],
        capture_output=True,
        text=True,
    )
    assert zig.returncode == 0, zig.stderr

    program = tmp_path / "g.c"
    program.write_text(
        "#include <stdio.h>\nint main(void) {\n"
        + "".join(
            f'\tprintf("api_f:\\n  d: %g\\n  f: %g\\n", {v!r}, (double)(float){v!r});\n'
            for v in values
        )
        + "\treturn 0;\n}\n"
    )
    subprocess.run(["cc", str(program), "-o", str(tmp_path / "g")], check=True)
    c = subprocess.run([str(tmp_path / "g")], capture_output=True, text=True).stdout

    assert zig.stdout == c


def test_the_idiomatic_layer_compiles_for_every_kind_of_parameter(parse, tmp_path):
    model, _ = parse(EDGES)
    assert process(model, ["zig"], tmp_path) == []

    module = (tmp_path / "zig" / "api.zig").read_text()
    assert "pub fn open(name: ?[*:0]const u8) anyerror!H {" in module
    assert "pub fn step(self: H, pos: *usize) anyerror!c_int {" in module
    assert "pub const deinit = close;" in module
    assert "/// `cb_context` must live until it has been called, once." in module
    assert "/// `cb_context` must live until the handle is destroyed." in module
    assert misindented_docs(module) == []


def test_names_that_clash_in_zig_are_made_distinct(parse, tmp_path):
    model, _ = parse(
        HANDLE_NAMED_AS_PREFIX
        + doc("Self", "@errno")
        + "int api_self(struct api *h);\n"
        + doc("Ret", "@param[out] data D", "@errno")
        + "int api_ret(struct api *h, int *data);\n"
        + doc("Data", "@param[out] ret R", "@errno")
        + "int api_data(struct api *h, int *ret);\n"
    )
    assert process(model, ["zig"], tmp_path) == []

    module = (tmp_path / "zig" / "api.zig").read_text()
    assert "pub const ApiHandle = struct {" in module
    assert "pub fn self_(self: ApiHandle) anyerror!void {" in module


def test_a_layout_other_than_recorded_fails_the_check(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    model.find("valid_point").size = 12

    failures = process(model, ["zig"], tmp_path)
    assert failures and "building the check failed" in failures[0]


def test_string_defines_keep_their_value(parse, tmp_path):
    model, _ = parse(ESCAPED)
    assert process(model, ["zig"], tmp_path) == []

    main = tmp_path / "main.zig"
    main.write_text(
        'const std = @import("std");\nconst api = @import("api.zig");\n'
        "pub fn main(init: std.process.Init) !void {\n"
        "    try std.Io.File.stdout().writeStreamingAll(init.io, api.API_S);\n}\n"
    )
    (tmp_path / "api.zig").write_text((tmp_path / "zig" / "api.zig").read_text())
    cache = str(tmp_path / ".cache")
    run = subprocess.run(
        ["zig", "run", "-lc", str(main), "--cache-dir", cache]
        + ["--global-cache-dir", cache],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout == ESCAPED_VALUE


@needs_cc
def test_shared_counts_handles_given_and_constructors_without_errno(parse, tmp_path):
    from tests.test_rust import MORE, MORE_C

    model, _ = parse(MORE)
    assert process(model, ["zig"], tmp_path) == []
    (tmp_path / "impl.c").write_text(MORE + MORE_C)
    (tmp_path / "api.zig").write_text((tmp_path / "zig" / "api.zig").read_text())
    main = tmp_path / "main.zig"
    main.write_text(
        'const std = @import("std");\nconst api = @import("api.zig");\n'
        "pub fn main() !void {\n"
        "    const h = try api.H.open();\n"
        "    try h.copy(api.H.make().?);\n"
        "    const a = [_]c_int{ 1, 2 };\n"
        "    const b = [_]c_int{ 3, 4 };\n"
        "    var buf: [2]c_int = undefined;\n"
        "    const mapped = try api.map(&a, &buf);\n"
        '    std.debug.print("{} {} {s}\\n", .{ api.dot(&a, &b), mapped[1],'
        " std.mem.span(try h.label()) });\n"
        "}\n"
    )
    cache = str(tmp_path / ".cache")
    run = subprocess.run(
        ["zig", "run", str(main), str(tmp_path / "impl.c"), "-lc"]
        + ["--cache-dir", cache, "--global-cache-dir", cache],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert run.stderr == "11 4 lbl\n"

    module = (tmp_path / "zig" / "api.zig").read_text()
    assert "if (b.len != a.len) @panic(" in module


def test_typedefs_of_handles_and_methods_named_deinit_build(parse, tmp_path):
    model, _ = parse(
        "struct api_h;\ntypedef struct api_h api_h_t;\n"
        "/**\n * Open\n * @param[out] h H\n * @errno\n */\n"
        "int api_open(struct api_h **h);\n"
        "/**\n * Close\n * @destroys h\n */\nvoid api_close(struct api_h *h);\n"
        "/**\n * Deinit\n */\nint api_h_deinit(struct api_h *h);\n"
        "/**\n * Use\n */\nint api_use(api_h_t *h);\n"
    )
    assert process(model, ["zig"], tmp_path) == []


@needs_cc
def test_bytes_clones_and_outs_named_like_ret(parse, tmp_path):
    from tests.test_rust import IO, IO_C, doc

    header = IO + doc("Get", "@param[out] retval R") + "void api_get(int *retval);\n"
    model, _ = parse(header)
    assert process(model, ["zig"], tmp_path) == []
    (tmp_path / "impl.c").write_text(
        header + IO_C + "void api_get(int *retval) { *retval = 42; }\n"
    )
    (tmp_path / "api.zig").write_text((tmp_path / "zig" / "api.zig").read_text())
    main = tmp_path / "main.zig"
    main.write_text(
        'const std = @import("std");\nconst api = @import("api.zig");\n'
        "pub fn main() !void {\n"
        "    var buf: [8]u8 = undefined;\n"
        "    const read = try api.read(&buf);\n"
        "    const h = try api.H.open();\n"
        "    const copy = try h.clone();\n"
        '    std.debug.print("{} {s} {} {}\\n", .{ api.write("abcd"), read, api.get(),'
        " copy.ptr == h.ptr });\n"
        "}\n"
    )
    cache = str(tmp_path / ".cache")
    run = subprocess.run(
        ["zig", "run", str(main), str(tmp_path / "impl.c"), "-lc"]
        + ["--cache-dir", cache, "--global-cache-dir", cache],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert run.stderr == "4 xyz 42 false\n"


@needs_cc
def test_internal_names_nullable_slices_and_callback_strings(parse, tmp_path):
    from tests.test_rust import doc

    header = (
        "#include <stddef.h>\ntypedef void (*api_seen_cb)(void *arg, const char *s);\n"
        + doc("Flags")
        + "int api_flags(void);\n"
        + doc("W")
        + "int api_w(int x);\n"
        + doc("Err")
        + "int api_err(void);\n"
        + doc("Sum", "@nullable v", "@len v n")
        + "int api_sum(const int *v, size_t n);\n"
        + doc("Seen", "@lifetime cb call")
        + "void api_seen(api_seen_cb cb, void *arg);\n"
    )
    model, _ = parse(header)
    assert process(model, ["zig"], tmp_path) == []
    (tmp_path / "impl.c").write_text(
        header + "int api_flags(void) { return 1; }\nint api_w(int x) { return x; }\n"
        "int api_err(void) { return 2; }\n"
        "int api_sum(const int *v, size_t n)\n"
        "{\n\tint s = 0;\n\tif (!v) return -1;\n"
        "\tfor (size_t i = 0; i < n; i++) s += v[i];\n\treturn s;\n}\n"
        'void api_seen(api_seen_cb cb, void *arg) { cb(arg, "hi"); }\n'
    )
    (tmp_path / "api.zig").write_text((tmp_path / "zig" / "api.zig").read_text())
    main = tmp_path / "main.zig"
    main.write_text(
        'const std = @import("std");\nconst api = @import("api.zig");\n'
        "const Seen = struct { len: usize = 0 };\n"
        "fn seen(s: *Seen, text: [*:0]const u8) void {\n"
        "    s.len = std.mem.span(text).len;\n}\n"
        "pub fn main() !void {\n"
        "    var got = Seen{};\n"
        "    api.seen(&got, seen);\n"
        "    const v = [_]c_int{ 1, 2, 3 };\n"
        '    std.debug.print("{} {} {} {} {} {}\\n", .{ api.flags_(), api.w_(5),'
        " api.err_(), api.sum(&v), api.sum(null), got.len });\n"
        "}\n"
    )
    cache = str(tmp_path / ".cache")
    run = subprocess.run(
        ["zig", "run", str(main), str(tmp_path / "impl.c"), "-lc"]
        + ["--cache-dir", cache, "--global-cache-dir", cache],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert run.stderr == "1 5 2 6 -1 2\n"


def test_names_of_the_module_and_of_its_locals_are_made_distinct(parse, tmp_path):
    from tests.test_rust import SHARED, doc

    model, _ = parse(
        SHARED
        + "#include <stddef.h>\nstruct api_h;\n"
        + "typedef int (*api_cb)(void *arg, int v);\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Errno of")
        + "int api_errno_of(int x);\n"
        + doc("Sum", "@nullable s", "@len s n")
        + "int api_sum(const int *s, size_t n);\n"
        + doc("Use", "@nullable h")
        + "int api_use(int context, struct api_h *h);\n"
        + doc("Each", "@lifetime cb call")
        + "int api_each(int a0, api_cb cb, void *arg);\n"
        + doc("Make", "@param[out] out O", "@errno")
        + "int api_make(int p, struct api_h **out);\n"
    )
    assert process(model, ["zig"], tmp_path) == []


def test_a_module_of_more_declarations_than_a_comptime_quota_builds(parse, tmp_path):
    """Compiling refers to every declaration, beyond 1000 comptime branches"""

    model, _ = parse("".join(f"/** F */\nint api_f{i}(int x);\n" for i in range(1200)))
    assert process(model, ["zig"], tmp_path) == []


def test_parameters_named_as_what_the_body_uses_build(parse, tmp_path):
    from tests.test_rust import HIDDEN

    model, _ = parse(HIDDEN)
    assert process(model, ["zig"], tmp_path) == []


def test_parameters_named_as_locals_of_the_layer_build(parse, tmp_path):
    from tests.test_rust import NAMES

    model, _ = parse(NAMES)
    assert process(model, ["zig"], tmp_path) == []


def test_a_method_named_as_the_pointer_of_its_handle(parse, tmp_path):
    from tests.test_rust import doc

    model, _ = parse(
        "struct api_h;\n"
        + doc("Open", "@param[out] h H", "@errno")
        + "int api_open(struct api_h **h);\n"
        + doc("Ptr")
        + "int api_h_ptr(struct api_h *h);\n"
    )
    assert process(model, ["zig"], tmp_path) == []


def test_a_function_named_as_a_record_has_its_own_doc(parse, tmp_path):
    model, _ = parse("/** R */\nstruct api_tag;\n/** F */\nint api_tag(int v);\n")
    assert process(model, ["zig"], tmp_path) == []
    assert (
        "/// F\n///\n/// Calls `api_tag`.\npub fn tag_("
        in (tmp_path / "zig" / "api.zig").read_text()
    )


def test_kept_contexts_are_called(parse, tmp_path):
    from tests.test_rust import KEPT, KEPT_C

    model, _ = parse(KEPT)
    assert process(model, ["zig"], tmp_path) == []
    (tmp_path / "impl.c").write_text(KEPT + KEPT_C)
    (tmp_path / "api.zig").write_text((tmp_path / "zig" / "api.zig").read_text())
    main = tmp_path / "main.zig"
    main.write_text(
        'const std = @import("std");\nconst api = @import("api.zig");\n'
        "const Sum = struct { v: c_int = 0 };\n"
        "fn add(s: *Sum, v: c_int) c_int {\n    s.v += v;\n    return 0;\n}\n"
        "fn add100(s: *Sum, v: c_int) c_int {\n    s.v += 100 * v;\n    return 0;\n}\n"
        "pub fn main() !void {\n"
        "    var sum = Sum{};\n"
        "    var h = try api.H.open();\n"
        "    defer h.deinit();\n"
        "    try h.on(&sum, add);\n"
        "    const taken = if (h.on(&sum, add)) |_| false else |_| true;\n"
        "    try h.submit(&sum, add100);\n"
        "    const busy = if (h.submit(&sum, add100)) |_| false else |_| true;\n"
        "    const n = try h.poke();\n"
        "    try h.fire(5);\n"
        '    std.debug.print("{} {} {} {}\\n", .{ taken, busy, n, sum.v });\n'
        "}\n"
    )
    cache = str(tmp_path / ".cache")
    run = subprocess.run(
        ["zig", "run", str(main), str(tmp_path / "impl.c"), "-lc"]
        + ["--cache-dir", cache, "--global-cache-dir", cache],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert run.stderr == "true true 1 705\n"


def test_skipped_records_and_padding_bits_build(parse, tmp_path):
    model, _ = parse(SKIPPED)
    assert process(model, ["zig"], tmp_path) == []


def run_zig(tmp_path, body: str) -> str:
    """Run 'body', in a main() with 'out' the writer of stdout, against the
    module generated into 'tmp_path'; returns what it printed"""

    main = tmp_path / "main.zig"
    main.write_text(
        'const std = @import("std");\nconst api = @import("api.zig");\n'
        "pub fn main(init: std.process.Init) !void {\n"
        "    var buf: [4096]u8 = undefined;\n"
        "    var out = std.Io.File.stdout().writer(init.io, &buf);\n"
        f"{body}"
        "    try out.interface.flush();\n}\n"
    )
    (tmp_path / "api.zig").write_text((tmp_path / "zig" / "api.zig").read_text())
    cache = str(tmp_path / ".cache")
    run = subprocess.run(
        ["zig", "run", "-lc", str(main), "--cache-dir", cache]
        + ["--global-cache-dir", cache],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    return run.stdout


def test_a_field_of_bits_prints_its_parts(parse, tmp_path):
    model, _ = parse(BITS)
    assert process(model, ["zig"], tmp_path) == []

    printed = run_zig(
        tmp_path,
        "    const s = api.ApiStatus{ .code = 0x8a05, .wide = 0x8000000100000002 };\n"
        '    try out.interface.print("{f}", .{s});\n'
        "    try api.ApiStatus.fpr(&out.interface, &s, api.API_PR_JSON);\n",
    )
    assert printed == BITS_PRINTED


def test_the_parts_of_a_field_of_bits_are_methods(parse, tmp_path):
    model, _ = parse(
        BITS + BITS_UNION + "/** C */\nstruct api_c {\n"
        "\tuint8_t status; ///< Status, see API_C_STATUS_*\n"
        "\tuint8_t statusFlags; ///< Named as a getter in Zig\n};\n"
        "/** Flags; bits 7:6 of 'status' */\n#define API_C_STATUS_FLAGS 0xc0\n"
        "/** A function named as the parameter of a setter */\nint value(int x);\n"
    )
    assert process(model, ["zig"], tmp_path) == []

    printed = run_zig(
        tmp_path,
        "    var s = api.ApiStatus{ .code = 0x8a05, .wide = 0x8000000100000002 };\n"
        '    try out.interface.print("{d} {d} {d} {d} {d}\\n", .{ s.codeType(),'
        " s.codeDelay(), s.codeDnr(), s.wideLow(), s.wideTop() });\n"
        "    s.setCodeDelay(3);\n    s.setCodeDnr(0);\n"
        "    s.setWideTop(0);\n    s.setWideLow(0xffffffff);\n"
        '    try out.interface.print("0x{x} 0x{x}\\n", .{ s.code, s.wide });\n'
        "    var u = std.mem.zeroes(api.ApiU);\n    u.setTypeHi(0xabcd);\n"
        '    try out.interface.print("0x{x} 0x{x}\\n", .{ u.@"type", u.typeHi() });\n'
        "    var c = std.mem.zeroes(api.ApiC);\n    c.setStatusFlags(2);\n"
        '    try out.interface.print("0x{x} {d}\\n",'
        " .{ c.status, c.statusFlags_() });\n"
        '    try out.interface.print("{s}\\n",'
        " .{@typeName(@TypeOf(s.codeDelay()))});\n",
    )
    assert printed == "5 10 1 2 1\n0x305 0x1ffffffff\n0xabcd0000 0xabcd\n0x80 2\nu4\n"


def test_a_packed_record_is_an_extern_struct_of_fields_aligned_to_1(parse, tmp_path):
    model, _ = parse(PACKED)
    assert process(model, ["zig"], tmp_path) == []
    assert "    value: u32 align(1)," in (tmp_path / "zig" / "api.zig").read_text()

    printed = run_zig(
        tmp_path,
        "    const p = api.ApiP{ .x = 4, .y = 5 };\n"
        "    var k = api.ApiK{ .tag = 1, .value = 0xdeadbeef,"
        " .at = .{ .x = -2, .y = 3 }, .path = .{ p, .{ .x = 6, .y = 7 } },"
        ' .pair = .{ 8, 9 }, .@"type" = 0x10 };\n'
        "    k.setTypeLow(0xa);\n"
        '    try out.interface.print("{f}", .{k});\n'
        "    try api.ApiK.fpr(&out.interface, &k, api.API_PR_JSON);\n"
        '    try out.interface.print("{d} {d}\\n", .{ @sizeOf(api.ApiKu),'
        " @alignOf(api.ApiKu) });\n",
    )
    assert printed == PACKED_PRINTED + "8 1\n"
