# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Run the targets on the IR: emit the code, format it, then check it
"""

import logging as log
from pathlib import Path
from typing import Dict, List, Optional

from yace import formatter
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
    Emit, format and check the code of the targets in 'names', and return the
    failures. 'include' holds the directories of the headers that the API
    includes, and 'options' the options of each target, by its name. The code
    of a target is not emitted when one of its formatters is not found.
    """

    options = options or {}
    failures = []
    for name in names:
        cls = targets.load(name)
        missing = formatter.missing(cls.FORMATTERS)
        if missing:
            failures += [f"{name}: {why}; nothing is emitted" for why in missing]
            continue
        # A target that takes no options may define __init__() without 'options'
        given = {"options": options[name]} if options.get(name) else {}
        tgt = cls(output, include or [], **given)
        paths = tgt.emit(model)
        for path in paths:
            log.info("%s: produced %s", name, path)
        formatted = formatter.format_all(cls.FORMATTERS, paths)
        failures += [f"{name}: {failure}" for failure in formatted]
        if formatted:
            continue
        if check:
            failures += [f"{name}: {failure}" for failure in tgt.check(model)]
    return failures
