//! The benchmark through the Rust bindings, as the C one: through the raw
//! layer, by foo_point_get() and by foo_point_visit() with an extern "C"
//! callback, and through the safe layer, by Handle::point_get() and by
//! Handle::point_visit() with a closure.
//!
//! Usage: bench ROUNDS REPEAT

use std::ffi::{c_int, c_void};
use std::ptr;
use std::time::{Duration, Instant};

use foo::safe::Handle;
use foo::*;

fn raw_calls(handle: *mut FooHandle, rounds: usize) -> i64 {
    let count = unsafe { foo_point_count(handle) };
    let mut sum = 0i64;
    for _ in 0..rounds {
        for idx in 0..count {
            sum += unsafe { (*foo_point_get(handle, idx)).x } as i64;
        }
    }
    sum
}

unsafe extern "C" fn add_x(arg: *mut c_void, point: *const FooPoint) -> c_int {
    *(arg as *mut i64) += (*point).x as i64;
    0
}

fn raw_callback(handle: *mut FooHandle, rounds: usize) -> i64 {
    let mut sum = 0i64;
    for _ in 0..rounds {
        unsafe { foo_point_visit(handle, Some(add_x), &mut sum as *mut i64 as *mut c_void) };
    }
    sum
}

fn safe_calls(handle: &mut Handle, rounds: usize) -> i64 {
    let count = handle.point_count();
    let mut sum = 0i64;
    for _ in 0..rounds {
        for idx in 0..count {
            sum += handle.point_get(idx).unwrap().x as i64;
        }
    }
    sum
}

fn safe_callback(handle: &mut Handle, rounds: usize) -> i64 {
    let mut sum = 0i64;
    for _ in 0..rounds {
        handle
            .point_visit(&mut |point: &FooPoint| {
                sum += point.x as i64;
                0
            })
            .unwrap();
    }
    sum
}

fn run(target: &str, way: &str, points: usize, repeat: usize, mut sum_of: impl FnMut() -> i64) {
    let mut best = Duration::MAX;
    let mut sum = 0;
    for _ in 0..repeat {
        let start = Instant::now();
        sum = sum_of();
        best = best.min(start.elapsed());
    }
    let ns = best.as_nanos() as f64 / points as f64;
    println!("{{\"target\": \"{target}\", \"way\": \"{way}\", \"ns\": {ns:.3}, \"sum\": {sum}}}");
}

fn main() {
    let args: Vec<usize> = std::env::args()
        .skip(1)
        .map(|arg| arg.parse().expect("usage: bench ROUNDS REPEAT"))
        .collect();
    let [rounds, repeat] = args[..] else {
        panic!("usage: bench ROUNDS REPEAT");
    };
    let points: Vec<FooPoint> =
        (0..FOO_POINTS_MAX).map(|idx| FooPoint { x: idx, y: -idx }).collect();

    let mut raw = ptr::null_mut();
    assert_eq!(unsafe { foo_open(c"bench".as_ptr(), &mut raw) }, 0);
    let added = unsafe { foo_point_add_many(raw, points.as_ptr(), points.len()) };
    assert_eq!(added, points.len() as isize);
    let total = rounds * points.len();
    run("rust-raw", "calls", total, repeat, || raw_calls(raw, rounds));
    run("rust-raw", "callback", total, repeat, || raw_callback(raw, rounds));
    unsafe { foo_close(raw) };

    let mut handle = Handle::open(c"bench").unwrap();
    handle.point_add_many(&points).unwrap();
    run("rust-safe", "calls", total, repeat, || safe_calls(&mut handle, rounds));
    run("rust-safe", "callback", total, repeat, || safe_callback(&mut handle, rounds));
}
