"""
The fixture library, examples/libfoo, called through the bindings of each
target: its check must print what examples/libfoo/expected.yaml says
"""

import json
import os
import platform
import re
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
