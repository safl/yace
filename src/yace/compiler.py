"""
Run targets on the IR: emit the code, then check it
"""

import logging as log
from pathlib import Path
from typing import List, Optional

from yace.ir.model import Model
from yace.targets import target as targets


def process(
    model: Model,
    names: List[str],
    output: Path,
    check: bool = True,
    include: Optional[List[Path]] = None,
) -> list:
    """
    Emit, and check, the code of the named targets; returns the failures. The
    'include' directories are where the headers the API includes are found.
    """

    failures = []
    for name in names:
        tgt = targets.load(name)(output, include or [])
        for path in tgt.emit(model):
            log.info("%s: produced %s", name, path)
        if check:
            failures += [f"{name}: {failure}" for failure in tgt.check(model)]
    return failures
