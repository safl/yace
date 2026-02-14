import tempfile
from pathlib import Path

import pytest

from yace.ir.cparser import c_to_yace


@pytest.mark.xfail(reason="Unsupported-construct validation not yet implemented")
def test_unsupported():
    """These should all produce errors"""

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = [path for path in Path(__file__).parent.glob("*.h")]
        output_path = Path(tmpdir)

        _, errors = c_to_yace(paths, output_path)

        assert errors, "Parser did not produce any errors"
