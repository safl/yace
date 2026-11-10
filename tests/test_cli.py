# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import json
import subprocess
import sys

from tests.conftest import HEADERS


def yace(*args):
    return subprocess.run(
        [sys.executable, "-m", "yace", *map(str, args)], capture_output=True, text=True
    )


def test_a_header_in_the_subset_passes_strict(tmp_path):
    proc = yace(HEADERS / "valid.h", "--output", tmp_path, "--strict")
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "valid.yaml").exists()
    assert (tmp_path / "valid.status").read_text().startswith("Parsed ")


def test_strict_fails_outside_the_subset(tmp_path):
    header = tmp_path / "bad.h"
    header.write_text("struct s { unsigned int a : 3; };\n")

    lenient = yace(header, "--output", tmp_path)
    assert lenient.returncode == 0
    assert "bitfield" in lenient.stderr

    strict = yace(header, "--output", tmp_path, "--strict")
    assert strict.returncode == 1


def test_meta_is_applied(tmp_path):
    meta = tmp_path / "meta.yaml"
    meta.write_text("name: Valid\nprefix: val\nlicense: MIT\n")
    proc = yace(HEADERS / "valid.h", "--output", tmp_path, "--meta", meta)
    assert proc.returncode == 0, proc.stderr
    assert "prefix: val" in (tmp_path / "valid.yaml").read_text()


def test_schema(tmp_path):
    proc = yace("--schema")
    assert proc.returncode == 0
    assert "Struct" in json.loads(proc.stdout)["$defs"]


def test_unknown_target(tmp_path):
    proc = yace(HEADERS / "valid.h", "--output", tmp_path, "--emit", "nope")
    assert proc.returncode == 1
    assert "no target" in proc.stderr


def test_the_headers_given_are_parsed_as_one_ir(tmp_path):
    a = tmp_path / "api_a.h"
    a.write_text("#pragma once\n/** A */\nstruct api_a {\n\tint n; ///< N\n};\n")
    b = tmp_path / "api_b.h"
    b.write_text(
        '#include "api_a.h"\n/**\n * B\n *\n * @param a A\n * @return N\n */\n'
        "int api_b(struct api_a *a);\n"
    )
    out = tmp_path / "out"
    proc = yace(a, b, "--output", out, "--strict")

    assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in out.iterdir()) == ["api_a.status", "api_a.yaml"]
    assert "api_b" in (out / "api_a.yaml").read_text()


def test_headers_including_nothing_pass_strict_and_build(tmp_path):
    a = tmp_path / "api_a.h"
    a.write_text("/** A */\nstruct api_a {\n\tuint64_t n; ///< N\n};\n")
    b = tmp_path / "api_b.h"
    b.write_text(
        "/**\n * B\n *\n * @param a A\n * @return N\n */\n"
        "size_t api_b(struct api_a *a);\n"
    )
    out = tmp_path / "out"
    proc = yace(a, b, "--output", out, "--strict", "--emit", "capi")

    assert proc.returncode == 0, proc.stderr


def test_a_prelude_supplies_what_the_headers_do_not_include(tmp_path):
    header = tmp_path / "api_v.h"
    header.write_text(
        "/**\n * V\n *\n * @param f F\n * @param iov Vector\n * @return N\n */\n"
        "ssize_t api_v(FILE *f, const struct iovec *iov);\n"
    )
    out = tmp_path / "out"
    preludes = ["--prelude", "stdio.h", "--prelude", "sys/uio.h"]
    proc = yace(header, "--output", out, *preludes, "--emit", "capi")

    assert proc.returncode == 0, proc.stderr
    assert "parse-error" not in proc.stderr
    assert "'FILE' is declared outside the headers" in proc.stderr
    assert "'struct iovec' is declared outside the headers" in proc.stderr


def test_toolchains_are_those_the_checks_build_with(monkeypatch):
    monkeypatch.setenv("GO", "/nonexistent/go")
    monkeypatch.setenv("CC", sys.executable)

    proc = yace("--toolchains")
    assert proc.returncode == 0, proc.stderr
    found = json.loads(proc.stdout)
    assert set(found) == {"capi", "cpp", "go", "python", "rust", "zig"}
    assert all(found[name] for name in found)
    go = found["go"][0]
    assert (go["env"], go["command"], go["present"]) == ("GO", "/nonexistent/go", False)
    cc = found["capi"][0]
    assert cc["present"] and cc["command"] == cc["path"] == sys.executable
    assert cc["version"].startswith("Python ")

    assert set(json.loads(yace("--toolchains", "--emit", "go").stdout)) == {"go"}


def test_a_check_without_its_toolchain_fails_naming_it(tmp_path, monkeypatch):
    monkeypatch.setenv("CXX", "/nonexistent/c++")
    header = tmp_path / "one.h"
    header.write_text("/** One @return 1 */\nint one_get(void);\n")
    meta = tmp_path / "meta.yaml"
    meta.write_text("name: one\nprefix: one\n")

    proc = yace(header, "--meta", meta, "--output", tmp_path, "--emit", "cpp")
    assert proc.returncode == 1
    assert "cpp: no C++ compiler ('/nonexistent/c++'); set CXX" in proc.stderr
