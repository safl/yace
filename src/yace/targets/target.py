# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The interface of a **yace** target: what generates the bindings of an API for
one language from its IR. Targets are found through the ``yace.targets`` entry
point group, so a package can provide one without changes to **yace**.
"""

from abc import ABC, abstractmethod
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Target(ABC):
    """Emit code for the IR into '<output>/<NAME>', and check what it emitted"""

    NAME = ""
    # What check() builds and runs with, see yace.toolchain
    TOOLCHAINS: tuple = ()
    # The options the target takes, each with the values it accepts, the first
    # of them its default
    OPTIONS: Dict[str, Tuple[str, ...]] = {}

    def __init__(
        self,
        output: Path,
        include: Optional[List[Path]] = None,
        options: Optional[Dict[str, str]] = None,
    ):
        self.options = self.options_of(options or {})
        self.output = Path(output) / self.NAME
        self.output.mkdir(parents=True, exist_ok=True)
        self.include = [Path(path) for path in include or []]

    @classmethod
    def options_of(cls, given: Dict[str, str]) -> Dict[str, str]:
        """Every option of the target, those not given at their default; raises
        ValueError for a key it does not take, or a value it does not accept"""

        for key, value in given.items():
            if key not in cls.OPTIONS:
                takes = ", ".join(sorted(cls.OPTIONS)) or "none"
                raise ValueError(f"{cls.NAME} takes no option '{key}'; takes: {takes}")
            if value not in cls.OPTIONS[key]:
                accepts = ", ".join(cls.OPTIONS[key])
                raise ValueError(f"{cls.NAME}.{key} is one of {accepts}, not '{value}'")
        return {key: given.get(key, values[0]) for key, values in cls.OPTIONS.items()}

    def headers_missing(self, model) -> Optional[str]:
        """Why the headers the IR was parsed from cannot be compiled with, or
        None where every one of them is found in the include directories"""

        if not model.meta.headers:
            return "the IR records no headers"
        missing = [
            name
            for name in model.meta.headers
            if not any((path / name).is_file() for path in self.include)
        ]
        if missing:
            return f"{', '.join(missing)} not found; give its directory with -I"
        return None

    def headers_unchecked(self, model) -> Optional[str]:
        """Why the signatures cannot be checked against the headers the IR was
        parsed from, or None where every one of them is found"""

        missing = self.headers_missing(model)
        return f"the signatures are not checked: {missing}" if missing else None

    @abstractmethod
    def emit(self, model) -> list:
        """Emit the code for 'model'; returns the paths written"""

    @abstractmethod
    def check(self, model) -> list:
        """Build and exercise what emit() wrote; returns the failures, if any"""


def targets() -> Dict[str, EntryPoint]:
    """The installed targets by name, loaded when asked for"""

    return {ep.name: ep for ep in entry_points(group="yace.targets")}


def load(name: str) -> type:
    found = targets()
    if name not in found:
        raise KeyError(f"no target '{name}'; installed: {', '.join(sorted(found))}")
    return found[name].load()
