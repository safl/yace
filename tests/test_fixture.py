"""
The fixture library, examples/libfoo, called through the bindings of each
target: its check must print what examples/libfoo/expected.yaml says
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.conftest import needs_cargo, needs_cc
from yace.compiler import process
from yace.ir.cparser import CParser
from yace.targets.capi.target import CFLAGS

FIXTURE = Path(__file__).parent.parent / "examples" / "libfoo"


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
def test_python(model, library, tmp_path, fmt):
    assert process(model, ["python"], tmp_path) == []

    lib = next(path for path in library.iterdir() if path.stem == "libfoo")
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "python")}
    env["FOO_LIBRARY"] = str(lib)
    proc = subprocess.run(
        [sys.executable, FIXTURE / "checks" / "python" / "check.py", fmt],
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
def test_rust(model, library, tmp_path, fmt):
    assert process(model, ["rust"], tmp_path) == []

    project = tmp_path / "check"
    project.mkdir()
    (project / "Cargo.toml").write_text(
        '[package]\nname = "check"\nversion = "0.0.0"\nedition = "2021"\n\n'
        f"[dependencies]\nfoo = {{ path = {json.dumps(str(tmp_path / 'rust'))} }}\n\n"
        '[[bin]]\nname = "check"\n'
        f"path = {json.dumps(str(FIXTURE / 'checks' / 'rust' / 'check.rs'))}\n"
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
