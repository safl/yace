from itertools import product
from pathlib import Path

import pytest

from yace.compiler import Compiler

VALID = [
    Path("models") / "example.yaml",
    Path("models") / "example-mini.yaml",
    Path("models") / "nvme.yaml",
    Path("models") / "xnvme.yaml",
]

INVALID = [
    Path("models") / "example-invalid.yaml",
]


@pytest.mark.parametrize("path,target", product(VALID, Compiler.TARGETS))
def test_compiler_with_valid_model(path, target):
    """Test **yace** via the cli using valid **yims**"""

    yace = Compiler([target.NAME], Path("/tmp") / "foo")
    yace.process(path)


@pytest.mark.parametrize("path,target", product(INVALID, Compiler.TARGETS))
def test_compiler_with_invalid_model(path, target):
    """Test **yace** via the cli using invalid **yims**"""

    yace = Compiler([target.NAME], Path("/tmp") / "foo")
    yace.process(path)
