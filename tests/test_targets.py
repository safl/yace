import os

from tests.conftest import HEADERS
from yace.compiler import process
from yace.targets import target as targets


def test_every_target_checks_with_a_relative_output(parser, tmp_path, monkeypatch):
    """The checks run tools in the output directory, given as a relative path"""

    model, _ = parser.parse(HEADERS / "valid.h")
    monkeypatch.chdir(tmp_path)
    installed = sorted(targets.targets())
    failures = process(model, installed, "out")
    assert [
        f for f in failures if "toolchain" not in f and "no compiler" not in f
    ] == []
    assert os.path.isdir(tmp_path / "out")
