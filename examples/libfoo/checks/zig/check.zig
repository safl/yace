//! The check of the Zig bindings of libfoo: calls the library through the
//! idiomatic layer, its handle, errors and returned values, and prints what it
//! got back, as YAML documents, or with argument "json" as JSON objects, each
//! holding what 'expected.yaml' says. An error is printed as the negative errno
//! the C function returned; what the layer does not take, a NULL where none is
//! allowed, is called raw.

const std = @import("std");
const foo = @import("foo");

const Writer = std.Io.Writer;

var as_json = false;

const Field = struct { []const u8, Value };

const Value = union(enum) {
    int: i64,
    str: []const u8,
    names: []const []const u8,

    fn write(self: Value, w: *Writer) Writer.Error!void {
        switch (self) {
            .int => |v| try w.print("{d}", .{v}),
            .str => |s| try w.print("\"{s}\"", .{s}),
            .names => |list| {
                try w.writeAll("[");
                for (list, 0..) |name, idx| {
                    if (idx > 0) try w.writeAll(", ");
                    try w.print("\"{s}\"", .{name});
                }
                try w.writeAll("]");
            },
        }
    }
};

fn document(w: *Writer, name: []const u8, fields: []const Field) Writer.Error!void {
    if (as_json) {
        try w.print("{{\"{s}\": {{", .{name});
        for (fields, 0..) |field, idx| {
            if (idx > 0) try w.writeAll(", ");
            try w.print("\"{s}\": ", .{field[0]});
            try field[1].write(w);
        }
        return w.writeAll("}}\n");
    }
    try w.print("---\n{s}:\n", .{name});
    for (fields) |field| {
        try w.print("  {s}: ", .{field[0]});
        try field[1].write(w);
        try w.writeAll("\n");
    }
}

/// Print a record, or none, with the pretty-printer generated for it
fn record(w: *Writer, comptime T: type, name: []const u8, obj: ?T) Writer.Error!void {
    const flags = if (as_json) foo.FOO_PR_JSON else foo.FOO_PR_YAML;
    if (as_json) {
        try w.print("{{\"{s}\": ", .{name});
        try T.fpr(w, if (obj) |*o| o else null, flags);
        return w.writeAll("}\n");
    }
    try w.writeAll("---\n");
    try T.fpr(w, if (obj) |*o| o else null, flags);
}

/// The value, 0 for void, or the negative errno of the error
fn errno(result: anytype) i64 {
    if (result) |value| {
        return switch (@typeInfo(@TypeOf(value))) {
            .int, .comptime_int => @intCast(value),
            else => 0,
        };
    } else |err| {
        return -@as(i64, foo.errnoOf(err));
    }
}

fn names(comptime E: type, comptime values: []const c_int) [values.len][]const u8 {
    var found: [values.len][]const u8 = undefined;
    for (values, 0..) |value, idx| {
        const e: E = @enumFromInt(value);
        found[idx] = e.cName() orelse "UNKNOWN";
    }
    return found;
}

const Sum = struct {
    x: i64 = 0,
    y: i64 = 0,
    visited: usize = 0,
    stop_after: usize = 0,

    fn visit(self: *Sum, point: *const foo.FooPoint) c_int {
        self.x += point.x;
        self.y += point.y;
        self.visited += 1;
        return @intFromBool(self.visited == self.stop_after);
    }
};

const Done = struct {
    count: usize = 0,

    fn set(self: *Done, count: usize) void {
        self.count = count;
    }
};

fn addX(arg: ?*anyopaque, point: [*c]const foo.FooPoint) callconv(.c) c_int {
    const sum: *i64 = @ptrCast(@alignCast(arg));
    sum.* += point[0].x;
    return 0;
}

pub fn main(init: std.process.Init) !void {
    var buf: [4096]u8 = undefined;
    var stdout = std.Io.File.stdout().writer(init.io, &buf);
    const w = &stdout.interface;
    var args = init.minimal.args.iterate();
    _ = args.next();
    as_json = if (args.next()) |arg| std.mem.eql(u8, arg, "json") else false;

    try document(w, "defines", &.{
        .{ "FOO_NAME", .{ .str = foo.FOO_NAME } },
        .{ "FOO_MAGIC", .{ .int = foo.FOO_MAGIC } },
        .{ "FOO_VERSION_MAJOR", .{ .int = foo.FOO_VERSION_MAJOR } },
        .{ "FOO_VERSION_MINOR", .{ .int = foo.FOO_VERSION_MINOR } },
        .{ "FOO_VERSION_PATCH", .{ .int = foo.FOO_VERSION_PATCH } },
        .{ "FOO_POINTS_MAX", .{ .int = foo.FOO_POINTS_MAX } },
        .{ "FOO_DEFAULT_SHAPE_SIDES", .{ .int = foo.FOO_DEFAULT_SHAPE_SIDES } },
    });
    const shapes = names(foo.FooShape, &.{ -1, 0, 1, 2, 3 });
    const options = names(foo.FooOption, &.{ 1, 2, 3 });
    try document(w, "enums", &.{
        .{ "foo_shape", .{ .names = &shapes } },
        .{ "foo_option", .{ .names = &options } },
    });

    const points = [_]foo.FooPoint{ .{ .x = 1, .y = 2 }, .{ .x = 3, .y = 4 }, .{ .x = 5, .y = 6 } };
    var handle = try foo.Handle.open("points");
    defer handle.deinit();
    var unopened: ?*foo.FooHandle = null;
    const open_without_name = foo.foo_open(null, &unopened);
    var added: i64 = 0;
    for (&points) |*point| added += @intFromBool(errno(handle.add(point)) == 0);
    const count = handle.count();

    var every = Sum{};
    const visit = errno(handle.visit(&every, Sum.visit));
    var first_two = Sum{ .stop_after = 2 };
    const stopped = errno(handle.visit(&first_two, Sum.visit));
    const without = foo.foo_visit(handle.ptr, null, null);
    var with_x: i64 = 0;
    const visitor = foo.FooVisitor{ .visit = &addX, .arg = &with_x };
    const visit_with = errno(handle.visitWith(&visitor));
    const unknown = errno(foo.figureFill(3));
    const add_many = errno(handle.addMany(&points));
    const count_after = handle.count();
    var copied_buf: [4]foo.FooPoint = undefined;
    const copied = try handle.points(&copied_buf);
    var copied_x: i64 = 0;
    for (copied) |p| copied_x += p.x;
    var done = Done{};
    const submit = errno(handle.submit(&done, Done.set));
    const submit_busy = errno(handle.submit(&done, Done.set));
    const poke = handle.poke();
    const poke_again = handle.poke();

    try document(w, "calls", &.{
        .{ "version", .{ .str = foo.version() } },
        .{ "open", .{ .int = 0 } },
        .{ "open_without_name", .{ .int = open_without_name } },
        .{ "name", .{ .str = handle.name() } },
        .{ "added", .{ .int = added } },
        .{ "count", .{ .int = @intCast(count) } },
        .{ "visit", .{ .int = visit } },
        .{ "visit_sum_x", .{ .int = every.x } },
        .{ "visit_sum_y", .{ .int = every.y } },
        .{ "visit_stopped", .{ .int = stopped } },
        .{ "visit_without_callback", .{ .int = without } },
        .{ "visit_with", .{ .int = visit_with } },
        .{ "visit_with_sum_x", .{ .int = with_x } },
        .{ "figure_of_unknown_shape", .{ .int = unknown } },
        .{ "add_many", .{ .int = add_many } },
        .{ "count_after_add_many", .{ .int = @intCast(count_after) } },
        .{ "points_copied", .{ .int = @intCast(copied.len) } },
        .{ "points_sum_x", .{ .int = copied_x } },
        .{ "submit", .{ .int = submit } },
        .{ "submit_busy", .{ .int = submit_busy } },
        .{ "poke", .{ .int = @intCast(poke) } },
        .{ "done_count", .{ .int = @intCast(done.count) } },
        .{ "poke_again", .{ .int = @intCast(poke_again) } },
    });

    try record(w, foo.FooPoint, "foo_point", handle.at(1));
    try record(w, foo.FooPoint, "foo_point", handle.at(6));

    while (errno(handle.add(&points[0])) == 0) {}
    try document(w, "full", &.{
        .{ "count", .{ .int = @intCast(handle.count()) } },
        .{ "add", .{ .int = errno(handle.add(&points[0])) } },
        .{ "add_many", .{ .int = errno(handle.addMany(points[0..1])) } },
    });

    const status = handle.statusGet();
    try record(w, foo.FooStatus, "foo_status", status);
    try document(w, "status", &.{
        .{ "pending", .{ .int = status.codePending() } },
        .{ "points", .{ .int = status.codePoints() } },
        .{ "full", .{ .int = status.codeFull() } },
    });
    var made = foo.FooStatus{ .code = 0, .max = foo.FOO_POINTS_MAX };
    made.setCodePoints(5);
    made.setCodePending(1);
    try record(w, foo.FooStatus, "foo_status", made);

    try record(w, foo.FooScalars, "foo_scalars", foo.scalarsFill());
    for ([_]foo.FooShape{ .point, .line, .polygon }) |shape| {
        const figure = try foo.figureFill(@intCast(@intFromEnum(shape)));
        try record(w, foo.FooFigure, "foo_figure", figure);
    }
    try record(w, foo.FooValue, "foo_value", foo.valueSet(-1));
    try record(w, foo.FooPacked, "foo_packed", foo.packedFill());
    try w.flush();
}
