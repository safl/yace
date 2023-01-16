from pathlib import Path
import pytest
from yace.compiler import Compiler

VALID = [
    Path("models") / "example.yaml",
    Path("models") / "nvme.yaml",
    Path("models") / "xnvme.yaml",
]

INVALID = [
    Path("models") / "example_invalid.yaml",
]

@pytest.mark.parametrize("path", VALID)
def test_valid(path):
    """Test **yace** via the cli using valid **yims**"""

    yace = Compiler(Compiler.STAGES, ["capi"], Path("/tmp") / "foo")
    yace.compile(path)


@pytest.mark.parametrize("path", INVALID)
def test_invalid(path):
    """Test **yace** via the cli using invalid **yims**"""

    yace = Compiler(Compiler.STAGES, ["capi"], Path("/tmp") / "foo")
    yace.compile(path)
