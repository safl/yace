//! The check of the idiomatic Rust layer of libfoo, the module 'safe': as
//! check.rs, through an owned handle, io::Result and returned values rather
//! than raw calls. An error is printed as the negative errno the C function
//! returned, so the documents printed are those of 'expected.yaml'.
//!
//! What safe Rust cannot express, a NULL where none is allowed, is called raw.

use std::ffi::{c_int, c_void};
use std::io;
use std::ptr;

use foo::safe::{self, Handle};
use foo::*;

mod common;

use common::*;

unsafe extern "C" fn add_x(arg: *mut c_void, point: *const FooPoint) -> c_int {
    *(arg as *mut i64) += (*point).x as i64;
    0
}

/// The value, 0 for (), or the negative errno of the error
fn errno<T: Into<i64>>(result: io::Result<T>) -> i64 {
    match result {
        Ok(value) => value.into(),
        Err(err) => -(err.raw_os_error().unwrap_or(0) as i64),
    }
}

/// Compiles only while T is not Send: were it Send, both impls would apply
/// and the call in main() would be ambiguous. A handle keeps the callbacks
/// given to it, which need not be Send, and they run on the thread that
/// polls it, so a handle must not leave its thread.
trait NotSend<A> {
    fn not_send() {}
}
impl<T: ?Sized> NotSend<()> for T {}
impl<T: ?Sized + Send> NotSend<u8> for T {}

/// As NotSend, for Sync: a handle shared between threads would let two of
/// them call it, and run its callbacks, at once
trait NotSync<A> {
    fn not_sync() {}
}
impl<T: ?Sized> NotSync<()> for T {}
impl<T: ?Sized + Sync> NotSync<u8> for T {}

fn status(result: io::Result<()>) -> i64 {
    errno(result.map(|()| 0i64))
}

fn count(result: io::Result<usize>) -> i64 {
    errno(result.map(|n| n as i64))
}

fn main() -> io::Result<()> {
    let as_json = std::env::args().nth(1).as_deref() == Some("json");
    <Handle as NotSend<_>>::not_send();
    <Handle as NotSync<_>>::not_sync();
    let flags = if as_json { FOO_PR_JSON } else { FOO_PR_YAML };

    document(
        "defines",
        &[
            ("FOO_NAME", Value::Str(FOO_NAME.to_string_lossy().into_owned())),
            ("FOO_MAGIC", Value::Int(FOO_MAGIC.into())),
            ("FOO_VERSION_MAJOR", Value::Int(FOO_VERSION_MAJOR.into())),
            ("FOO_VERSION_MINOR", Value::Int(FOO_VERSION_MINOR.into())),
            ("FOO_VERSION_PATCH", Value::Int(FOO_VERSION_PATCH.into())),
            ("FOO_POINTS_MAX", Value::Int(FOO_POINTS_MAX.into())),
            ("FOO_DEFAULT_SHAPE_SIDES", Value::Int(FOO_DEFAULT_SHAPE_SIDES.into())),
        ],
        as_json,
    );
    let names = |values: &[c_int], name: fn(c_int) -> Option<&'static str>| {
        Value::Names(values.iter().map(|&v| name(v).unwrap_or("UNKNOWN")).collect())
    };
    document(
        "enums",
        &[
            ("foo_shape", names(&[-1, 0, 1, 2, 3], |v| FooShape(v as _).name())),
            ("foo_option", names(&[1, 2, 3], |v| FooOption(v as _).name())),
        ],
        as_json,
    );

    let points = [FooPoint { x: 1, y: 2 }, FooPoint { x: 3, y: 4 }, FooPoint { x: 5, y: 6 }];
    let mut handle = Handle::open(c"points")?;
    let open_without_name = unsafe { foo_open(ptr::null(), &mut ptr::null_mut()) };
    let name = handle.name().to_string_lossy().into_owned();
    let watched = std::rc::Rc::new(std::cell::Cell::new((0usize, 0i64)));
    let (watcher, busy) = (watched.clone(), watched.clone());
    let watch = status(handle.point_watch(Box::new(move |p: &FooPoint| {
        let (n, x) = watcher.get();
        watcher.set((n + 1, x + p.x as i64));
    })));
    let watch_busy = status(handle.point_watch(Box::new(move |_: &FooPoint| busy.set((0, 0)))));
    let added = points.iter().filter(|p| handle.point_add(p).is_ok()).count();
    let count_before = handle.point_count();

    let (mut sum_x, mut sum_y) = (0i64, 0i64);
    let visit = count(handle.point_visit(&mut |p: &FooPoint| {
        sum_x += p.x as i64;
        sum_y += p.y as i64;
        0
    }));
    let mut seen = 0;
    let stopped = count(handle.point_visit(&mut |_: &FooPoint| {
        seen += 1;
        (seen == 2) as c_int
    }));
    let without = unsafe { foo_point_visit(handle.as_ptr(), None, ptr::null_mut()) };
    let mut with_x = 0i64;
    let visitor = FooVisitor {
        visit: Some(add_x),
        arg: &mut with_x as *mut i64 as *mut c_void,
    };
    // A record holding a callback and its context: unsafe, as nothing checks them
    let visit_with = count(unsafe { handle.point_visit_with(&visitor) });
    let unknown = status(safe::figure_fill(3).map(|_| ()));
    let add_many = count(handle.point_add_many(&points));
    let copied = handle.point_copy(4)?;
    let counted = std::rc::Rc::new(std::cell::Cell::new(0));
    let (once, again) = (counted.clone(), counted.clone());
    let submit = status(handle.count_submit(Box::new(move |n| once.set(n))));
    let submit_busy = status(handle.count_submit(Box::new(move |n| again.set(n))));
    let complete = handle.count_complete();
    let complete_again = handle.count_complete();

    document(
        "calls",
        &[
            ("version", Value::Str(safe::version().to_string_lossy().into_owned())),
            ("open", Value::Int(0)),
            ("open_without_name", Value::Int(open_without_name.into())),
            ("name", Value::Str(name)),
            ("watch", Value::Int(watch)),
            ("watch_busy", Value::Int(watch_busy)),
            ("added", Value::Int(added as i64)),
            ("count", Value::Int(count_before as i64)),
            ("visit", Value::Int(visit)),
            ("visit_sum_x", Value::Int(sum_x)),
            ("visit_sum_y", Value::Int(sum_y)),
            ("visit_stopped", Value::Int(stopped)),
            ("visit_without_callback", Value::Int(without as i64)),
            ("visit_with", Value::Int(visit_with)),
            ("visit_with_sum_x", Value::Int(with_x)),
            ("figure_of_unknown_shape", Value::Int(unknown)),
            ("add_many", Value::Int(add_many)),
            ("count_after_add_many", Value::Int(handle.point_count() as i64)),
            ("watched", Value::Int(watched.get().0 as i64)),
            ("watched_sum_x", Value::Int(watched.get().1)),
            ("points_copied", Value::Int(copied.len() as i64)),
            ("points_sum_x", Value::Int(copied.iter().map(|p| p.x as i64).sum())),
            ("submit", Value::Int(submit)),
            ("submit_busy", Value::Int(submit_busy)),
            ("complete", Value::Int(complete as i64)),
            ("done_count", Value::Int(counted.get() as i64)),
            ("complete_again", Value::Int(complete_again as i64)),
        ],
        as_json,
    );

    record("foo_point", FooPoint::fpr, handle.point_get(1).as_ref(), flags)?;
    record("foo_point", FooPoint::fpr, handle.point_get(6).as_ref(), flags)?;

    while handle.point_add(&points[0]).is_ok() {}
    document(
        "full",
        &[
            ("count", Value::Int(handle.point_count() as i64)),
            ("add", Value::Int(status(handle.point_add(&points[0])))),
            ("add_many", Value::Int(count(handle.point_add_many(&points[..1])))),
            ("watched", Value::Int(watched.get().0 as i64)),
        ],
        as_json,
    );
    statuses(&handle.status_get(), flags, as_json)?;
    handle.close();

    record("foo_scalars", FooScalars::fpr, Some(&safe::scalars_fill()), flags)?;
    for shape in [FOO_SHAPE_POINT, FOO_SHAPE_LINE, FOO_SHAPE_POLYGON] {
        let figure = safe::figure_fill(shape.0 as u32)?;
        record("foo_figure", FooFigure::fpr, Some(&figure), flags)?;
    }
    record("foo_value", FooValue::fpr, Some(&safe::value_set(-1)), flags)?;
    record("foo_wire", FooWire::fpr, Some(&safe::wire_fill()), flags)?;

    Ok(())
}
