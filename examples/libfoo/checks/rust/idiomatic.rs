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

fn status(result: io::Result<()>) -> i64 {
    errno(result.map(|()| 0i64))
}

fn count(result: io::Result<usize>) -> i64 {
    errno(result.map(|n| n as i64))
}

fn main() -> io::Result<()> {
    let as_json = std::env::args().nth(1).as_deref() == Some("json");
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
    let added = points.iter().filter(|p| handle.add(p).is_ok()).count();
    let count_before = handle.count();

    let (mut sum_x, mut sum_y) = (0i64, 0i64);
    let visit = count(handle.visit(&mut |p: &FooPoint| {
        sum_x += p.x as i64;
        sum_y += p.y as i64;
        0
    }));
    let mut seen = 0;
    let stopped = count(handle.visit(&mut |_: &FooPoint| {
        seen += 1;
        (seen == 2) as c_int
    }));
    let without = unsafe { foo_visit(handle.as_ptr(), None, ptr::null_mut()) };
    let mut with_x = 0i64;
    let visitor = FooVisitor {
        visit: Some(add_x),
        arg: &mut with_x as *mut i64 as *mut c_void,
    };
    // A record holding a callback and its context: unsafe, as nothing checks them
    let visit_with = count(unsafe { handle.visit_with(&visitor) });
    let unknown = status(safe::figure_fill(3).map(|_| ()));
    let add_many = count(handle.add_many(&points));
    let copied = handle.points(4)?;

    document(
        "calls",
        &[
            ("version", Value::Str(safe::version().to_string_lossy().into_owned())),
            ("open", Value::Int(0)),
            ("open_without_name", Value::Int(open_without_name.into())),
            ("name", Value::Str(name)),
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
            ("count_after_add_many", Value::Int(handle.count() as i64)),
            ("points_copied", Value::Int(copied.len() as i64)),
            ("points_sum_x", Value::Int(copied.iter().map(|p| p.x as i64).sum())),
        ],
        as_json,
    );

    record("foo_point", FooPoint::fpr, handle.at(1).as_ref(), flags)?;
    record("foo_point", FooPoint::fpr, handle.at(6).as_ref(), flags)?;

    while handle.add(&points[0]).is_ok() {}
    document(
        "full",
        &[
            ("count", Value::Int(handle.count() as i64)),
            ("add", Value::Int(status(handle.add(&points[0])))),
            ("add_many", Value::Int(count(handle.add_many(&points[..1])))),
        ],
        as_json,
    );
    handle.close();

    record("foo_scalars", FooScalars::fpr, Some(&safe::scalars_fill()), flags)?;
    for shape in [FOO_SHAPE_POINT, FOO_SHAPE_LINE, FOO_SHAPE_POLYGON] {
        let figure = safe::figure_fill(shape.0 as u32)?;
        record("foo_figure", FooFigure::fpr, Some(&figure), flags)?;
    }
    record("foo_value", FooValue::fpr, Some(&safe::value_set(-1)), flags)?;

    Ok(())
}
