"""
The interface of a **yace** target: what generates the bindings of an API for
one language from its IR. Targets are found through the ``yace.targets`` entry
point group, so a package can provide one without changes to **yace**.
"""

from abc import ABC, abstractmethod
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Dict, List, Optional


class Target(ABC):
    """Emit code for the IR into '<output>/<NAME>', and check what it emitted"""

    NAME = ""
    # What check() builds and runs with, see yace.toolchain
    TOOLCHAINS: tuple = ()

    def __init__(self, output: Path, include: Optional[List[Path]] = None):
        self.output = Path(output) / self.NAME
        self.output.mkdir(parents=True, exist_ok=True)
        self.include = [Path(path) for path in include or []]

    def headers_unchecked(self, model) -> Optional[str]:
        """Why the signatures cannot be checked against the headers the IR was
        parsed from, or None where every one of them is found in the include
        directories"""

        if not model.meta.headers:
            return "the signatures are not checked: the IR records no headers"
        missing = [
            name
            for name in model.meta.headers
            if not any((path / name).is_file() for path in self.include)
        ]
        if missing:
            return (
                f"the signatures are not checked: {', '.join(missing)} not found;"
                " give its directory with -I"
            )
        return None

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
