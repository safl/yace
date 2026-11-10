// SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
//
// SPDX-License-Identifier: GPL-2.0-only

//! The benchmark through the idiomatic layer of the Zig bindings, as the C
//! one: by handle.pointGet() and by handle.pointVisit() with a method.
//!
//! Usage: bench ROUNDS REPEAT

const std = @import("std");
const foo = @import("foo");

fn calls(handle: foo.Handle, rounds: usize) i64 {
    const count = handle.pointCount();
    var sum: i64 = 0;
    for (0..rounds) |_| {
        for (0..count) |idx| {
            sum += handle.pointGet(idx).?.x;
        }
    }
    return sum;
}

const Sum = struct {
    x: i64 = 0,

    fn addX(self: *Sum, point: *const foo.FooPoint) c_int {
        self.x += point.x;
        return 0;
    }
};

fn callback(handle: foo.Handle, rounds: usize) i64 {
    var sum = Sum{};
    for (0..rounds) |_| {
        _ = handle.pointVisit(&sum, Sum.addX) catch unreachable;
    }
    return sum.x;
}

fn run(
    w: *std.Io.Writer,
    io: std.Io,
    handle: foo.Handle,
    way: []const u8,
    comptime sumOf: fn (foo.Handle, usize) i64,
    rounds: usize,
    repeat: usize,
) !void {
    var best: i96 = std.math.maxInt(i96);
    var sum: i64 = 0;
    for (0..repeat) |_| {
        const start = std.Io.Clock.awake.now(io);
        sum = sumOf(handle, rounds);
        best = @min(best, start.durationTo(std.Io.Clock.awake.now(io)).toNanoseconds());
    }
    const points: f64 = @floatFromInt(rounds * handle.pointCount());
    const ns = @as(f64, @floatFromInt(best)) / points;
    try w.print("{{\"target\": \"zig\", \"way\": \"{s}\", \"ns\": {d:.3}, \"sum\": {d}}}\n", .{ way, ns, sum });
}

pub fn main(init: std.process.Init) !void {
    var buf: [4096]u8 = undefined;
    var stdout = std.Io.File.stdout().writer(init.io, &buf);
    const w = &stdout.interface;
    var args = init.minimal.args.iterate();
    _ = args.next();
    const rounds = try std.fmt.parseInt(usize, args.next() orelse return error.Usage, 10);
    const repeat = try std.fmt.parseInt(usize, args.next() orelse return error.Usage, 10);

    var points: [foo.FOO_POINTS_MAX]foo.FooPoint = undefined;
    for (&points, 0..) |*point, idx| {
        const x: i32 = @intCast(idx);
        point.* = .{ .x = x, .y = -x };
    }
    var handle = try foo.Handle.open("bench");
    defer handle.deinit();
    _ = try handle.pointAddMany(&points);

    try run(w, init.io, handle, "calls", calls, rounds, repeat);
    try run(w, init.io, handle, "callback", callback, rounds, repeat);
    try w.flush();
}
