import tempfile
from pathlib import Path

from yace.ir.generator import c_to_yace


def test_do_format():
    """How is this"""

    path = Path(__file__).parent / "foo.h"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir)

        assert (
            c_to_yace([path], output_path) == 0
        ), f"Failed parsing C Header at path: {path}"
