from pathlib import Path
from yace.parser import c_header_to_yidl_file
import tempfile


def test_do_format():
    """How is this"""

    path = Path(__file__).parent / "foo.h"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir)

        assert (
            c_header_to_yidl_file([path], output_path) == 0
        ), f"Failed parsing C Header at path: {path}"
