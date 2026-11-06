//! The check of the Rust bindings of libfoo: calls the library through the
//! generated crate and prints what it got back, as YAML documents, or with
//! argument "json" as JSON objects, each holding what 'expected.yaml' says

use std::ffi::{c_int, c_void, CStr};
use std::io;
use std::ptr;

use foo::*;

mod common;

use common::*;

/// Sums the points visited, stopping after 'stop_after' of them
#[derive(Default)]
struct Sum {
    x: i64,
    y: i64,
    visited: usize,
    stop_after: usize,
}

unsafe extern "C" fn summarize(arg: *mut c_void, point: *const FooPoint) -> c_int {
    let sum = &mut *(arg as *mut Sum);
    sum.x += (*point).x as i64;
    sum.y += (*point).y as i64;
    sum.visited += 1;
    (sum.visited == sum.stop_after) as c_int
}

unsafe extern "C" fn count_done(arg: *mut c_void, count: usize) {
    *(arg as *mut usize) = count;
}

fn string(ptr: *const std::ffi::c_char) -> String {
    unsafe { CStr::from_ptr(ptr) }.to_string_lossy().into_owned()
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
    let mut handle: *mut FooHandle = ptr::null_mut();
    let mut every = Sum::default();
    let mut first_two = Sum { stop_after: 2, ..Sum::default() };
    let mut with = Sum::default();
    let mut figure = FooFigure::default();

    unsafe {
        let version = string(foo_version());
        let opened = foo_open(c"points".as_ptr(), &mut handle);
        let open_without_name = foo_open(ptr::null(), &mut handle);
        let name = string(foo_name(handle));
        let added = points.iter().filter(|p| foo_point_add(handle, *p) == 0).count();
        let count = foo_point_count(handle);
        let visit = foo_point_visit(handle, Some(summarize), &mut every as *mut Sum as *mut c_void);
        let stopped =
            foo_point_visit(handle, Some(summarize), &mut first_two as *mut Sum as *mut c_void);
        let without = foo_point_visit(handle, None, ptr::null_mut());
        let visitor = FooVisitor {
            visit: Some(summarize),
            arg: &mut with as *mut Sum as *mut c_void,
        };
        let visit_with = foo_point_visit_with(handle, &visitor);
        let unknown = foo_figure_fill(&mut figure, 3);
        let add_many = foo_point_add_many(handle, points.as_ptr(), points.len());
        let count_after_add_many = foo_point_count(handle);
        let mut copied = [FooPoint::default(); 4];
        let points_copied = foo_point_copy(handle, copied.as_mut_ptr(), copied.len());
        let points_sum_x: i64 = copied.iter().map(|p| p.x as i64).sum();
        let mut done_count: usize = 0;
        let done = &mut done_count as *mut usize as *mut c_void;
        let submit = foo_count_submit(handle, Some(count_done), done);
        let submit_busy = foo_count_submit(handle, Some(count_done), done);
        let complete = foo_count_complete(handle);
        let complete_again = foo_count_complete(handle);
        document(
            "calls",
            &[
                ("version", Value::Str(version)),
                ("open", Value::Int(opened.into())),
                ("open_without_name", Value::Int(open_without_name.into())),
                ("name", Value::Str(name)),
                ("added", Value::Int(added as i64)),
                ("count", Value::Int(count as i64)),
                ("visit", Value::Int(visit as i64)),
                ("visit_sum_x", Value::Int(every.x)),
                ("visit_sum_y", Value::Int(every.y)),
                ("visit_stopped", Value::Int(stopped as i64)),
                ("visit_without_callback", Value::Int(without as i64)),
                ("visit_with", Value::Int(visit_with as i64)),
                ("visit_with_sum_x", Value::Int(with.x)),
                ("figure_of_unknown_shape", Value::Int(unknown.into())),
                ("add_many", Value::Int(add_many as i64)),
                ("count_after_add_many", Value::Int(count_after_add_many as i64)),
                ("points_copied", Value::Int(points_copied as i64)),
                ("points_sum_x", Value::Int(points_sum_x)),
                ("submit", Value::Int(submit.into())),
                ("submit_busy", Value::Int(submit_busy.into())),
                ("complete", Value::Int(complete as i64)),
                ("done_count", Value::Int(done_count as i64)),
                ("complete_again", Value::Int(complete_again as i64)),
            ],
            as_json,
        );

        record("foo_point", FooPoint::fpr, foo_point_get(handle, 1).as_ref(), flags)?;
        record("foo_point", FooPoint::fpr, foo_point_get(handle, 6).as_ref(), flags)?;

        while foo_point_add(handle, &points[0]) == 0 {}
        let full = [
            ("count", Value::Int(foo_point_count(handle) as i64)),
            ("add", Value::Int(foo_point_add(handle, &points[0]).into())),
            ("add_many", Value::Int(foo_point_add_many(handle, points.as_ptr(), 1) as i64)),
        ];
        document("full", &full, as_json);
        let mut status = FooStatus::default();
        foo_status_get(handle, &mut status);
        statuses(&status, flags, as_json)?;
        foo_close(handle);
        foo_close(ptr::null_mut());

        let mut scalars = FooScalars::default();
        foo_scalars_fill(&mut scalars);
        record("foo_scalars", FooScalars::fpr, Some(&scalars), flags)?;

        for shape in [FOO_SHAPE_POINT, FOO_SHAPE_LINE, FOO_SHAPE_POLYGON] {
            if foo_figure_fill(&mut figure, shape.0 as u32) != 0 {
                std::process::exit(1);
            }
            record("foo_figure", FooFigure::fpr, Some(&figure), flags)?;
        }

        let mut value = FooValue::default();
        foo_value_set(&mut value, -1);
        record("foo_value", FooValue::fpr, Some(&value), flags)?;

        let mut wire = FooWire::default();
        foo_wire_fill(&mut wire);
        record("foo_wire", FooWire::fpr, Some(&wire), flags)?;
    }

    Ok(())
}
