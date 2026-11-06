"""
The fixture library, examples/libfoo, called through the bindings of each
target: its check must print what examples/libfoo/expected.yaml says
"""

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
from yace.targets.cpp.target import CXXFLAGS
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
    """The documents of the output of a check; JSON objects follow each other"""

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
    """The fixture library, built as a shared library from its own header"""

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
def test_capi(model, library, tmp_path, fmt):
    assert process(model, ["capi"], tmp_path) == []

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
def test_python(model, library, tmp_path, fmt, program):
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
def test_cython(model, library, tmp_path, fmt):
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


# Each target of the benchmark, the toolchain it is built with, and the results
# its program prints
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
    assert (out / "artifacts" / "results.csv").exists()


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
def test_rust(model, library, tmp_path, fmt, program):
    check_rust(model, library, tmp_path, fmt, program)


@needs_cc
@needs_cargo
@pytest.mark.skipif(
    "YACE_RUST_MSRV" not in os.environ,
    reason="no Rust toolchain of the declared rust-version; the devenv has it",
)
@pytest.mark.parametrize("program", ["check", "idiomatic"])
def test_rust_at_the_declared_rust_version(
    model, library, tmp_path, program, monkeypatch
):
    template = (RUST / "Cargo.toml.template").read_text()
    declared = re.search(r'^rust-version = "(.+)"$', template, re.M).group(1)
    assert os.environ["YACE_RUST_MSRV"] == declared

    monkeypatch.setenv("RUSTUP_TOOLCHAIN", declared)
    check_rust(model, library, tmp_path, "yaml", program)


@needs_cc
@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_cpp(model, library, tmp_path, fmt):
    assert process(model, ["cpp"], tmp_path) == []

    cxx = os.environ.get("CXX", "c++")
    includes = ["-I", tmp_path / "capi", "-I", tmp_path / "cpp"]
    binary = tmp_path / "check"
    run(
        [cxx, *CXXFLAGS, *includes, FIXTURE / "checks" / "cpp" / "check.cpp"]
        + ["-L", library, "-lfoo", f"-Wl,-rpath,{library}"]
        + ["-o", binary]
    )
    expected = list(yaml.safe_load_all((FIXTURE / "expected.yaml").read_text()))

    assert documents(run([binary, fmt]), fmt) == expected


@needs_cc
@needs_zig
@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_zig(model, library, tmp_path, fmt):
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
def test_go(model, library, tmp_path, fmt):
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
