import tempfile
from pathlib import Path

from yace.idl.generator import c_to_yace


def test_unsupported():
    """These should all produce errors"""

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = [path for path in Path(__file__).glob("*.h")]
        output_path = Path(tmpdir)

        errors = c_to_yace(paths, output_path)

        assert errors, "Parser did not produce any errors"
