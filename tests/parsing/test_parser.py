import tempfile
from pathlib import Path

from yace.ir.cparser import c_to_yace


def test_do_format():
    """How is this"""

    path = Path(__file__).parent / "example.h"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir)

        errors = c_to_yace([path], output_path)
        assert not errors, f"Failed parsing C Header at path: {path}: {errors}"
