"""
Tools used by targets to do what they do, so mention a couple, then:

code-formating; :function:`.clang_format`

doxygen:

"""
from pathlib import Path
from subprocess import run
from typing import List


def clang_format(files: List[Path], rulefile: Path):
    """
    Formats the given files using the given rule-file
    """

    return run(
        ["clang-format", f"--style=file:{rulefile}", "-i"] + [str(f) for f in files],
        check=True,
    )
