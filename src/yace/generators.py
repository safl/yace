"""
The interface of a **yace** generator: what writes C headers, and the C
sources implementing what they declare, from something other than C, as the
model of a specification, for **yace** to take as it takes any header.

Generators are found through the ``yace.generators`` entry point group, so a
project provides one without changes to **yace**. What a generator writes is
parsed, emitted and checked as headers written by hand are: it is held to the
C subset, its diagnostics are reported, and the targets emit its bindings and
printers. So a generator gets no way past **yace**'s rules, and what it writes
can be trusted as far as a header can.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Dict, List


@dataclass
class Generated:
    """What a generator wrote: the headers for **yace** to parse, and the
    sources implementing what they declare, for the project to build"""

    headers: List[Path] = field(default_factory=list)
    sources: List[Path] = field(default_factory=list)


class Generator(ABC):
    """Write into '<output>/<NAME>', by the 'options' given it"""

    NAME = ""

    def __init__(self, output: Path, options: Dict[str, str]):
        self.output = Path(output) / self.NAME
        self.output.mkdir(parents=True, exist_ok=True)
        self.options = dict(options)

    @abstractmethod
    def generate(self) -> Generated:
        """Write the headers and sources; returns what it wrote"""


def generators() -> Dict[str, EntryPoint]:
    """The installed generators by name, loaded when asked for"""

    return {ep.name: ep for ep in entry_points(group="yace.generators")}


def load(name: str) -> type:
    found = generators()
    if name not in found:
        raise KeyError(
            f"no generator '{name}'; installed: {', '.join(sorted(found)) or 'none'}"
        )
    return found[name].load()


def options_of(given: List[str]) -> Dict[str, Dict[str, str]]:
    """The options of each generator, from '<generator>.<key>=<value>' each"""

    options: Dict[str, Dict[str, str]] = {}
    for option in given:
        name, _, setting = option.partition(".")
        key, equals, value = setting.partition("=")
        if not name or not key or not equals:
            raise ValueError(
                f"generator option '{option}' is not <generator>.<key>=<value>"
            )
        options.setdefault(name, {})[key] = value
    return options


def generate(names: List[str], output: Path, given: List[str]) -> Generated:
    """Run the named generators, with their options; returns all they wrote"""

    options = options_of(given)
    unknown = sorted(set(options) - set(names))
    if unknown:
        raise ValueError(f"options of generators not run: {', '.join(unknown)}")
    generated = Generated()
    for name in names:
        wrote = load(name)(output, options.get(name, {})).generate()
        generated.headers += wrote.headers
        generated.sources += wrote.sources
    return generated
