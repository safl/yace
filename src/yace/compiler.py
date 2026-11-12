# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Run targets on the IR: emit the code, then check it
"""

import logging as log
from pathlib import Path
from typing import Dict, List, Optional

from yace.ir.model import Model
from yace.targets import target as targets


def process(
    model: Model,
    names: List[str],
    output: Path,
    check: bool = True,
    include: Optional[List[Path]] = None,
    options: Optional[Dict[str, Dict[str, str]]] = None,
) -> list:
    """
    Emit, and check, the code of the named targets; returns the failures. The
    'include' directories are where the headers the API includes are found, and
    'options' are those of each target, by its name.
    """

    options = options or {}
    failures = []
    for name in names:
        cls = targets.load(name)
        # Only to a target given options, as a target that takes none may define
        # __init__() without them
        given = {"options": options[name]} if options.get(name) else {}
        tgt = cls(output, include or [], **given)
        for path in tgt.emit(model):
            log.info("%s: produced %s", name, path)
        if check:
            failures += [f"{name}: {failure}" for failure in tgt.check(model)]
    return failures
