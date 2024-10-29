"""
Collect compiler-targets from the current workdir
"""

import inspect
import typing
from importlib.machinery import SourceFileLoader
from pathlib import Path

from yace.targets.target import Target


def collect(searchpath: typing.Optional[Path] = None):
    """Searches the current and immediate subdirectories"""

    if searchpath is None:
        searchpath = Path.cwd()

    TARGETS = []
    for dirpath in [searchpath] + [
        path for path in searchpath.glob("*") if path.is_dir()
    ]:
        for path in dirpath.glob("target.py"):
            mod = SourceFileLoader(path.stem, str(path)).load_module()
            for _, obj in inspect.getmembers(mod):
                if inspect.isclass(obj) and issubclass(obj, Target) and obj != Target:
                    TARGETS.append(obj)

    return TARGETS


def main():
    collect()


if __name__ == "__main__":
    main()
