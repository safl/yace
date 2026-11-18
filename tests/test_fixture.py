# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Tests that call the fixture library, examples/libfoo, through the bindings of
each target. The check program of each target must print the documents in
examples/libfoo/expected.yaml.
"""

import errno
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.conftest import needs_cargo, needs_cc, needs_cython, needs_go, needs_zig
from yace.compiler import process
from yace.ir.cparser import CParser
from yace.targets.capi.target import CFLAGS
from yace.targets.cpp.target import CPP, cxxflags
from yace.targets.go.target import GO_VERSION
from yace.targets.rust import target as rust_target

FIXTURE = Path(__file__).parent.parent / "examples" / "libfoo"
RUST = Path(rust_target.__file__).parent


def cc() -> str:
    return os.environ.get("CC", "cc")


def run(cmd: list) -> str:
    proc = subprocess.run([str(arg) for arg in cmd], capture_output=True, text=True)
    assert proc.returncode == 0, f"{' '.join(map(str, cmd))}\n{proc.stderr}"
    return proc.stdout


def documents(text: str, fmt: str) -> list:
    """Return the documents that a check printed; in JSON, the check prints its
    objects one after another, with no separator but whitespace"""

    if fmt == "yaml":
        return list(yaml.safe_load_all(text))

    found, decoder, pos = [], json.JSONDecoder(), 0
    while text[pos:].strip():
        while text[pos].isspace():
            pos += 1
        doc, pos = decoder.raw_decode(text, pos)
        found.append(doc)
    return found


@pytest.fixture(scope="module")
def library(tmp_path_factory) -> Path:
    """Build the fixture library from src/foo.c as a shared library, and return
    the directory that holds it"""

    out = tmp_path_factory.mktemp("libfoo")
    suffix = ".dylib" if platform.system() == "Darwin" else ".so"
    run(
        [cc(), *CFLAGS, "-shared", "-fPIC", "-I", FIXTURE / "include"]
        + [FIXTURE / "src" / "foo.c", "-o", out / f"libfoo{suffix}"]
    )
    return out


def parse():
    meta = yaml.safe_load((FIXTURE / "meta.yaml").read_text())
    return CParser().parse(FIXTURE / "include" / "foo.h", meta)


@pytest.fixture(scope="module")
def model():
    return parse()[0]


def test_the_fixture_is_in_the_subset():
    _, diagnostics = parse()
    assert [f"{d.rule}: {d.message}" for d in diagnostics] == []


@needs_cc
@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_the_capi_check_prints_the_expected_documents(model, library, tmp_path, fmt):
    assert process(model, ["capi"], tmp_path, include=[FIXTURE / "include"]) == []
    assert "not checked" not in (tmp_path / "capi" / "signatures.log").read_text()

    capi = tmp_path / "capi"
    binary = tmp_path / "check"
    run(
        [cc(), *CFLAGS, "-I", capi, FIXTURE / "checks" / "capi" / "check.c"]
        + [capi / "foo_pp.c", "-L", library, "-lfoo", f"-Wl,-rpath,{library}"]
        + ["-o", binary]
    )
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(run([binary, fmt]), fmt) == expected


@needs_cc
@pytest.mark.parametrize("fmt", ["yaml", "json"])
@pytest.mark.parametrize("program", ["check.py", "idiomatic.py"])
def test_the_python_checks_print_the_expected_documents(
    model, library, tmp_path, fmt, program
):
    assert process(model, ["python"], tmp_path) == []

    lib = next(path for path in library.iterdir() if path.stem == "libfoo")
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "python")}
    env["FOO_LIBRARY"] = str(lib)
    proc = subprocess.run(
        [sys.executable, FIXTURE / "checks" / "python" / program, fmt],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(proc.stdout, fmt) == expected


@needs_cc
@needs_cython
@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_the_cython_check_prints_the_expected_documents(model, library, tmp_path, fmt):
    assert process(model, ["python"], tmp_path) == []

    lib = next(path for path in library.iterdir() if path.stem == "libfoo")
    python = tmp_path / "python"
    project = tmp_path / "check"
    project.mkdir()
    (project / "check.pyx").write_text(
        (FIXTURE / "checks" / "cython" / "check.pyx").read_text()
    )
    (project / "setup.py").write_text(
        "from Cython.Build import cythonize\n"
        "from setuptools import Extension, setup\n\n"
        "extension = Extension(\n"
        f"    'check', ['check.pyx'], include_dirs=[{str(python)!r}],\n"
        f"    extra_link_args=[{str(lib)!r}, '-Wl,-rpath,{library}'],\n"
        ")\n"
        f"setup(ext_modules=cythonize([extension], include_path=[{str(python)!r}]))\n"
    )
    build = subprocess.run(
        [sys.executable, "setup.py", "-q", "build_ext", "--inplace"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    proc = subprocess.run(
        [sys.executable, "-c", f"import sys, check; sys.exit(check.main({fmt!r}))"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(proc.stdout, fmt) == expected


# Each target of the benchmark, the tool that builds it, and the names of the
# results that its program prints
BENCH = {
    "c": ("cc", ["c"]),
    "cpp": (os.environ.get("CXX", "c++"), ["cpp"]),
    "rust": ("cargo", ["rust-raw", "rust-safe"]),
    "zig": ("zig", ["zig"]),
    "go": ("go", ["go"]),
    "python": (sys.executable, ["python-raw", "python-idiomatic"]),
    "cython": ("cython", ["cython"]),
}


def has_toolchain(target):
    """Whether this machine has every tool the benchmark builds 'target' with"""

    if target == "cython":
        return all(importlib.util.find_spec(m) for m in ["Cython", "setuptools"])
    if target == "rust":
        return all(shutil.which(tool) for tool in ["cargo", "rustc"])
    return shutil.which(BENCH[target][0]) is not None


@needs_cc
@pytest.mark.skipif(not shutil.which("cijoe"), reason="no cijoe")
@pytest.mark.parametrize("target", list(BENCH))
def test_the_benchmark_runs_every_target_alike(tmp_path, target):
    if not has_toolchain(target):
        pytest.skip(f"no toolchain for the {target} benchmark")

    python = f'"{sys.executable}"'
    (tmp_path / "test.toml").write_text(
        f"[bench]\nrounds = 3\nrepeat = 1\ntargets = {json.dumps(['c', target])}\n"
        f"workdir = {json.dumps(str(tmp_path / 'work'))}\n"
        f"python = {json.dumps(python)}\nyace = {json.dumps(f'{python} -m yace')}\n"
        f"cc = {json.dumps(cc())}\ncxx = {json.dumps(BENCH['cpp'][0])}\n"
    )
    out = tmp_path / "out"
    proc = subprocess.run(
        ["cijoe", "bench.yaml", "-c", "bench.toml", "-c", tmp_path / "test.toml"]
        + ["-o", out, "--report-skip"],
        cwd=FIXTURE / "bench",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stderr}\nsee {out}"

    results = BENCH["c"][1] + BENCH[target][1]
    rows = json.loads((out / "artifacts" / "results.json").read_text())["rows"]
    printed = {(row["target"], row["way"]) for row in rows}
    assert printed == {(r, way) for r in results for way in ["calls", "callback"]}
    assert {row["sum"] for row in rows} == {3 * sum(range(8))}
    report = (out / "artifacts" / "report.txt").read_text()
    assert all(result in report for result in results)
    assert "built at -O3 for the baseline CPU" in report
    assert "not pinned to a core; the clock not pinned" in report
    assert (out / "artifacts" / "results.csv").exists()
    recorded = json.loads((out / "artifacts" / "results.json").read_text())
    assert recorded["clock"]["pinned"] is False
    ran = [run["target"] for run in recorded["runs"]]
    assert ran == list(dict.fromkeys(["c", target]))
    assert recorded["rounds"] == {name: 3 for name in ran}
    assert recorded["seconds"] is None


def benchlib():
    """examples/libfoo/bench/scripts/benchlib.py"""

    spec = importlib.util.spec_from_file_location(
        "benchlib", FIXTURE / "bench" / "scripts" / "benchlib.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_benchmark_counts_how_busy_each_cpu_was():
    lib = benchlib()
    before = lib.ticks("cpu0 10 0 10 80 0 0 0 0 0 0\ncpu1 0 0 0 100 0 0 0 0 0 0\n")
    after = lib.ticks("cpu0 60 0 10 130 0 0 0 0 0 0\ncpu1 0 0 5 195 0 0 0 0 0 0\n")
    assert before == {0: (20, 100), 1: (0, 100)}
    assert lib.busy(before, after) == {0: 0.5, 1: 0.05}


def test_the_benchmark_pins_every_program_to_the_core_given(tmp_path, monkeypatch):
    lib = benchlib()
    where = {"build": "/b", "gen": "/g", "lib": "/l/libfoo.so", "programs": "/p"}
    monkeypatch.setattr(lib, "paths", lambda cijoe: where)

    class Conf:
        output_path = str(tmp_path)

        def __init__(self, values):
            self.values = values

        def getconf(self, key, default=None):
            return self.values.get(key, default)

    for target in lib.TARGETS:
        cmd, _ = lib.run_command(Conf({"bench.cpu": 3}), target, 10, 1)
        assert "taskset -c 3 " in cmd, target
        cmd, _ = lib.run_command(Conf({}), target, 10, 1)
        assert "taskset" not in cmd, target


def check_rust(model, library, tmp_path, fmt, program):
    assert process(model, ["rust"], tmp_path) == []

    project = tmp_path / "check"
    project.mkdir()
    (project / "Cargo.toml").write_text(
        '[package]\nname = "check"\nversion = "0.0.0"\nedition = "2021"\n\n'
        f"[dependencies]\nfoo = {{ path = {json.dumps(str(tmp_path / 'rust'))} }}\n\n"
        f'[[bin]]\nname = "{program}"\n'
        f"path = {json.dumps(str(FIXTURE / 'checks' / 'rust' / f'{program}.rs'))}\n"
    )
    env = {**os.environ, "FOO_LIB_DIR": str(library)}
    env["RUSTFLAGS"] = f"-C link-arg=-Wl,-rpath,{library}"
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "--offline", "--", fmt],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(proc.stdout, fmt) == expected


@needs_cc
@needs_cargo
@pytest.mark.parametrize("fmt", ["yaml", "json"])
@pytest.mark.parametrize("program", ["check", "idiomatic"])
def test_the_rust_checks_print_the_expected_documents(
    model, library, tmp_path, fmt, program
):
    check_rust(model, library, tmp_path, fmt, program)


@needs_cc
@needs_cargo
@pytest.mark.skipif(
    "YACE_RUST_MSRV" not in os.environ,
    reason="no Rust toolchain of the declared rust-version; the devenv has it",
)
@pytest.mark.parametrize("program", ["check", "idiomatic"])
def test_the_rust_checks_pass_with_the_declared_rust_version(
    model, library, tmp_path, program, monkeypatch
):
    template = (RUST / "Cargo.toml.template").read_text()
    declared = re.search(r'^rust-version = "(.+)"$', template, re.M).group(1)
    assert os.environ["YACE_RUST_MSRV"] == declared

    monkeypatch.setenv("RUSTUP_TOOLCHAIN", declared)
    check_rust(model, library, tmp_path, "yaml", program)


@needs_cc
@pytest.mark.parametrize("fmt", ["yaml", "json"])
@pytest.mark.parametrize("std", CPP.OPTIONS["std"])
def test_the_cpp_check_prints_the_expected_documents(
    model, library, tmp_path, fmt, std
):
    assert process(model, ["cpp"], tmp_path, options={"cpp": {"std": std}}) == []

    cxx = os.environ.get("CXX", "c++")
    includes = ["-I", tmp_path / "capi", "-I", tmp_path / "cpp"]
    binary = tmp_path / "check"
    run(
        [cxx, *cxxflags(std), *includes, FIXTURE / "checks" / "cpp" / "check.cpp"]
        + ["-L", library, "-lfoo", f"-Wl,-rpath,{library}"]
        + ["-o", binary]
    )
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(run([binary, fmt]), fmt) == expected


# What foo_errmsg() returns after foo_point_add() failed on a handle named
# 'points' that holds FOO_POINTS_MAX points
FULL = "the handle 'points' holds 8 points, as many as it can"


@needs_cc
@pytest.mark.parametrize("std", CPP.OPTIONS["std"])
def test_the_cpp_exception_holds_the_message_of_the_library(
    model, library, tmp_path, std
):
    assert process(model, ["cpp"], tmp_path, options={"cpp": {"std": std}}) == []

    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\n#include <system_error>\n#include <foo.hpp>\n"
        "int main() {\n"
        '\tauto handle = foo::open("points");\n'
        "\ttry {\n\t\tfor (;;) {\n\t\t\thandle.point_add({1, 2});\n\t\t}\n"
        "\t} catch (const std::system_error &err) {\n"
        '\t\tstd::printf("%d %s\\n", err.code().value(), err.what());\n\t}\n'
        "\treturn 0;\n}\n"
    )
    cxx = os.environ.get("CXX", "c++")
    includes = ["-I", tmp_path / "capi", "-I", tmp_path / "cpp"]
    binary = tmp_path / "main"
    run(
        [cxx, *cxxflags(std), *includes, tmp_path / "main.cpp"]
        + ["-L", library, "-lfoo", f"-Wl,-rpath,{library}", "-o", binary]
    )
    enospc = errno.ENOSPC
    assert run([binary]) == f"{enospc} foo_point_add: {FULL}: {os.strerror(enospc)}\n"


@needs_cc
def test_the_python_oserror_holds_the_message_of_the_library(
    model, library, tmp_path, monkeypatch
):
    assert process(model, ["python"], tmp_path) == []

    lib = next(path for path in library.iterdir() if path.stem == "libfoo")
    monkeypatch.setenv("FOO_LIBRARY", str(lib))
    foo: dict = {}
    path = tmp_path / "python" / "foo.py"
    exec(compile(path.read_text(), str(path), "exec"), foo)

    with foo["open"]("points") as handle, pytest.raises(OSError) as raised:
        while True:
            handle.point_add(foo["FooPoint"](1, 2))
    assert (raised.value.errno, raised.value.strerror) == (errno.ENOSPC, FULL)


@needs_cc
@needs_zig
@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_the_zig_check_prints_the_expected_documents(model, library, tmp_path, fmt):
    assert process(model, ["zig"], tmp_path) == []

    binary = tmp_path / "check"
    cache = tmp_path / "zig" / ".cache"
    run(
        ["zig", "build-exe", "--cache-dir", cache, "--global-cache-dir", cache]
        + ["-lc", "-L", library, "-lfoo", "-rpath", library]
        + ["--dep", "foo", f"-Mroot={FIXTURE / 'checks' / 'zig' / 'check.zig'}"]
        + [f"-Mfoo={tmp_path / 'zig' / 'foo.zig'}", f"-femit-bin={binary}"]
    )
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(run([binary, fmt]), fmt) == expected


@needs_cc
@needs_go
@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_the_go_check_prints_the_expected_documents(model, library, tmp_path, fmt):
    assert process(model, ["go"], tmp_path) == []

    project = tmp_path / "check"
    project.mkdir()
    (project / "go.mod").write_text(
        f"module check\n\ngo {GO_VERSION}\n\nrequire foo v0.0.0\n\n"
        f"replace foo => {tmp_path / 'go'}\n"
    )
    (project / "main.go").write_text(
        (FIXTURE / "checks" / "go" / "main.go").read_text()
    )
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOTOOLCHAIN": "local"}
    env["CGO_LDFLAGS"] = f"-L{library} -Wl,-rpath,{library}"
    binary = tmp_path / "check.bin"
    build = subprocess.run(
        ["go", "build", "-buildvcs=false", "-o", str(binary), "."],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )
    assert build.returncode == 0, build.stderr
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(run([binary, fmt]), fmt) == expected


def test_a_c_time_below_the_clock_s_resolution_gives_no_ratio(tmp_path, monkeypatch):
    """A run of few rounds can take less than one tick of the clock, as on
    macOS, which makes the time of C 0. bench_report then leaves the ratio to
    the time of C empty."""

    import types

    monkeypatch.syspath_prepend(str(FIXTURE / "bench" / "scripts"))
    import bench_report

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    rows = [
        {"target": "c", "way": "calls", "ns": 0.0, "sum": 84},
        {"target": "python", "way": "calls", "ns": 5.0, "sum": 84},
    ]
    (artifacts / "results.json").write_text(
        json.dumps({"rows": rows, "points": 8, "rounds": 3, "repeat": 1})
    )
    cijoe = types.SimpleNamespace(
        output_path=str(tmp_path), facts=types.SimpleNamespace(target=lambda: {})
    )
    assert bench_report.main(None, cijoe) == 0
    assert (artifacts / "results.csv").read_text().splitlines()[1:] == [
        "c,calls,0.0,84,",
        "python,calls,5.0,84,",
    ]


def test_the_benchmark_calibrates_the_rounds_to_the_slowest_way():
    lib = benchlib()
    rows = [{"ns": 2.5}, {"ns": 10.0}]

    # 8 points at 10 ns for 10**7 rounds is 0.8 s; 2 s takes 2.5 times as many
    assert lib.rounds_for(rows, 10**7, 2.0) == 25 * 10**6
    assert lib.rounds_for(rows, 10**6, 2.0) is None
    assert lib.rounds_for([{"ns": 0.0}], 1000, 2.0) is None
