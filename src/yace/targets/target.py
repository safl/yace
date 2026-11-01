"""
The interface of a **yace** target: what generates the bindings of an API for
one language from its IR. Targets are found through the ``yace.targets`` entry
point group, so a package can provide one without changes to **yace**.
"""

from abc import ABC, abstractmethod
from importlib.metadata import entry_points
from pathlib import Path
from typing import Dict, List, Optional


class Target(ABC):
    """Emit code for the IR into '<output>/<NAME>', and check what it emitted"""

    NAME = ""

    def __init__(self, output: Path, include: Optional[List[Path]] = None):
        self.output = Path(output) / self.NAME
        self.output.mkdir(parents=True, exist_ok=True)
        self.include = [Path(path) for path in include or []]

    @abstractmethod
    def emit(self, model) -> list:
        """Emit the code for 'model'; returns the paths written"""

    @abstractmethod
    def check(self, model) -> list:
        """Build and exercise what emit() wrote; returns the failures, if any"""


def targets() -> Dict[str, type]:
    """The installed targets by name, loaded when asked for"""

    return {ep.name: ep for ep in entry_points(group="yace.targets")}


def load(name: str) -> type:
    found = targets()
    if name not in found:
        raise KeyError(f"no target '{name}'; installed: {', '.join(sorted(found))}")
    return found[name].load()
