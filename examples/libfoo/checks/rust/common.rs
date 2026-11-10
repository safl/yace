// SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
//
// SPDX-License-Identifier: GPL-2.0-only

//! What the checks of the Rust bindings of libfoo share: printing documents

use std::ffi::c_int;
use std::io::{self, Write};

use foo::*;

/// A value as JSON, which is also YAML
pub enum Value {
    Int(i64),
    Str(String),
    Names(Vec<&'static str>),
}

pub fn json(value: &Value) -> String {
    match value {
        Value::Int(v) => v.to_string(),
        Value::Str(s) => format!("\"{s}\""),
        Value::Names(names) => {
            let quoted: Vec<String> = names.iter().map(|n| format!("\"{n}\"")).collect();
            format!("[{}]", quoted.join(", "))
        }
    }
}

pub fn document(name: &str, data: &[(&str, Value)], as_json: bool) {
    if as_json {
        let fields: Vec<String> = data
            .iter()
            .map(|(key, value)| format!("\"{key}\": {}", json(value)))
            .collect();
        println!("{{\"{name}\": {{{}}}}}", fields.join(", "));
        return;
    }
    println!("---\n{name}:");
    for (key, value) in data {
        println!("  {key}: {}", json(value));
    }
}

/// Print a record with the pretty-printer generated for it
pub fn record<T>(
    name: &str,
    fpr: fn(&mut dyn Write, Option<&T>, c_int) -> io::Result<()>,
    obj: Option<&T>,
    flags: c_int,
) -> io::Result<()> {
    let mut out = io::stdout().lock();
    if flags == FOO_PR_YAML {
        writeln!(out, "---")?;
        return fpr(&mut out, obj, flags);
    }
    write!(out, "{{\"{name}\": ")?;
    fpr(&mut out, obj, flags)?;
    writeln!(out, "}}")
}

/// Print the status of a full handle, its parts, and a status of parts set
pub fn statuses(status: &FooStatus, flags: c_int, as_json: bool) -> io::Result<()> {
    record("foo_status", FooStatus::fpr, Some(status), flags)?;
    let parts = [
        ("pending", Value::Int(status.code_pending().into())),
        ("points", Value::Int(status.code_points().into())),
        ("full", Value::Int(status.code_full().into())),
    ];
    document("status", &parts, as_json);
    let mut made = FooStatus {
        max: FOO_POINTS_MAX as u16,
        ..Default::default()
    };
    made.set_code_points(5);
    made.set_code_pending(1);
    record("foo_status", FooStatus::fpr, Some(&made), flags)
}
