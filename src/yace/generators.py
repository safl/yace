# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The interface of a **yace** generator. A generator writes C headers, and the C
sources that implement them, from a source other than C, such as the data model
of a specification.

**yace** finds a generator through the ``yace.generators`` entry point group,
or by its file or module and its class, so that a project that is not a Python
package installs nothing. The generated headers are parsed, emitted and checked
as headers written by hand are.
"""

import importlib
import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Generated:
    """What a generator wrote: the headers for **yace** to parse, and the
    sources implementing what they declare, for the project to build"""

    headers: List[Path] = field(default_factory=list)
    sources: List[Path] = field(default_factory=list)


class Generator(ABC):
    """Writes headers and sources into '<output>/<NAME>', as 'options' say"""

    NAME = ""

    def __init__(self, output: Path, options: Dict[str, str]):
        self.output = Path(output) / self.NAME
        self.output.mkdir(parents=True, exist_ok=True)
        self.options = dict(options)

    @abstractmethod
    def generate(self) -> Generated:
        """Write the headers and sources, and return their paths"""


def generators() -> Dict[str, EntryPoint]:
    """The entry point of each installed generator, by name"""

    return {ep.name: ep for ep in entry_points(group="yace.generators")}


def load(name: str) -> Any:
    """
    The class of the generator 'name': an installed generator of that name, or
    else "<where>:<class>", where '<where>' is the dotted name of a module or
    the path of a '.py' file, such as ``toolbox/spec.py:SpecHeaders``
    """

    found = generators()
    if name in found:
        return found[name].load()
    where, colon, attr = name.rpartition(":")
    if not colon or not where or not attr:
        raise KeyError(
            f"no generator '{name}'; installed: {', '.join(sorted(found)) or 'none'}"
        )
    if where.endswith(".py"):
        path = Path(where)
        if not path.is_file():
            raise KeyError(f"no generator '{name}': no file '{where}'")
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise KeyError(f"no generator '{name}': '{where}' is no module")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(where)
        except ImportError as error:
            raise KeyError(f"no generator '{name}': {error}") from error
    generator = getattr(module, attr, None)
    if not isinstance(generator, type):
        raise KeyError(f"no generator '{name}': '{where}' has no class '{attr}'")
    return generator


def options_of(given: List[str], kind: str = "generator") -> Dict[str, Dict[str, str]]:
    """The options in 'given', each '<name>.<key>=<value>', by name; the error names
    'kind', a generator or a target"""

    options: Dict[str, Dict[str, str]] = {}
    for option in given:
        name, _, setting = option.partition(".")
        key, equals, value = setting.partition("=")
        if not name or not key or not equals:
            raise ValueError(f"{kind} option '{option}' is not <{kind}>.<key>=<value>")
        options.setdefault(name, {})[key] = value
    return options


def generate(names: List[str], output: Path, given: List[str]) -> Generated:
    """Run the generators in 'names' with the options in 'given'; returns what they
    wrote"""

    options = options_of(given)
    # A generator given by its file has no name but its NAME
    classes = [load(name) for name in names]
    unknown = sorted(set(options) - {cls.NAME for cls in classes})
    if unknown:
        raise ValueError(f"options of generators not run: {', '.join(unknown)}")
    generated = Generated()
    for cls in classes:
        wrote = cls(output, options.get(cls.NAME, {})).generate()
        generated.headers += wrote.headers
        generated.sources += wrote.sources
    return generated
