# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The formatters the emitted code is formatted with, so that the bindings are
laid out as each language's own formatter lays them out. A target names its
own in 'Target.FORMATTERS'.

Black, clang-format and taplo are dependencies of **yace**, pinned to one
version each, so their output is that of the **yace** installed. gofmt, go mod
edit, rustfmt and zig fmt ship with the toolchains of their languages, and
their version is that of the toolchain found. C and C++ are formatted in the
style of xNVMe, which 'xnvme.clang-format' gives. Cython has no formatter, so
the '.pyx' and '.pxd' files keep the layout the Cython target writes.
"""

import os
import subprocess
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import black
import clang_format

from yace import toolchain

STYLE = Path(__file__).parent / "xnvme.clang-format"


@dataclass(frozen=True)
class Formatter:
    """Formats the files with a suffix of 'suffixes', in place"""

    what: str
    suffixes: Tuple[str, ...]

    def missing(self) -> Optional[str]:
        """Why the formatter cannot run, or None where it is found"""

        return None

    def find(self) -> Dict[str, Any]:
        """What the formatter is, where it is found, and its version"""

        raise NotImplementedError

    def run(self, paths: List[Path]) -> List[str]:
        """Format 'paths' in place; returns the failures, if any"""

        raise NotImplementedError

    def format(self, paths: Sequence[Path]) -> List[str]:
        """Format those of 'paths' with a suffix of the formatter"""

        mine = sorted(Path(p) for p in paths if Path(p).suffix in self.suffixes)
        return self.run(mine) if mine else []


@dataclass(frozen=True)
class Black(Formatter):
    """Black, in this process, at the version **yace** pins"""

    def find(self) -> Dict[str, Any]:
        version = f"black, {black.__version__}"
        return {"what": self.what, "present": True, "version": version}

    def run(self, paths: List[Path]) -> List[str]:
        failures = []
        for path in paths:
            try:
                text = black.format_str(path.read_text(), mode=black.Mode())
            except black.InvalidInput as error:
                failures.append(f"black cannot parse {path.name}: {error}")
                continue
            path.write_text(text)
        return failures


@dataclass(frozen=True)
class Command(Formatter):
    """A formatter run as 'tool' with 'args' and the files, or once per file
    where 'each'; its version is that of 'versioned', the toolchain it ships
    with, where it has no version of its own. The variables of the environment
    in 'unset', which would point it at a configuration, are removed."""

    tool: toolchain.Toolchain = toolchain.CC
    args: Tuple[str, ...] = ()
    versioned: Optional[toolchain.Toolchain] = None
    each: bool = False
    unset: Tuple[str, ...] = ()

    def missing(self) -> Optional[str]:
        return self.tool.missing()

    def find(self) -> Dict[str, Any]:
        found = self.tool.find()
        found["what"] = self.what
        if self.versioned is not None and found["present"]:
            found["version"] = self.versioned.find()["version"]
        return found

    def run(self, paths: List[Path]) -> List[str]:
        env = {k: v for k, v in os.environ.items() if k not in self.unset}
        failures = []
        for group in [[path] for path in paths] if self.each else [paths]:
            cmd = [self.tool.command(), *self.args, *map(str, group)]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, check=False, env=env
            )
            if proc.returncode:
                names = ", ".join(path.name for path in group)
                failures.append(f"{self.what} failed on {names}:\n{proc.stderr}")
        return failures


GOFMT = toolchain.Toolchain("gofmt of the Go toolchain", "GOFMT", "gofmt")

BLACK = Black("Python formatter, black", (".py",))
CLANG_FORMAT = Command(
    "C formatter, clang-format",
    (".c", ".h", ".cpp", ".hpp"),
    toolchain.Toolchain(
        "clang-format", None, clang_format.get_executable("clang-format")
    ),
    ("-i", f"--style=file:{STYLE}"),
)
GO = Command("Go formatter, gofmt", (".go",), GOFMT, ("-w",), toolchain.GO)
RUST = Command(
    "Rust formatter, rustfmt",
    (".rs",),
    toolchain.Toolchain("rustfmt of the Rust toolchain", "RUSTFMT", "rustfmt"),
    ("--edition", "2021"),
)
ZIG = Command("Zig formatter, zig fmt", (".zig",), toolchain.ZIG, ("fmt",))
GO_MOD = Command(
    "go.mod formatter, go mod edit",
    (".mod",),
    toolchain.GO,
    ("mod", "edit", "-fmt"),
    each=True,
)
TOML = Command(
    "TOML formatter, taplo",
    (".toml",),
    toolchain.Toolchain(
        "taplo", None, str(Path(sysconfig.get_path("scripts")) / "taplo")
    ),
    ("fmt", "--no-auto-config"),
    unset=("TAPLO_CONFIG",),
)


def missing(formatters: Sequence[Formatter]) -> List[str]:
    """The failures of a target whose formatters are not all found"""

    return [why for why in (f.missing() for f in formatters) if why]


def format_all(formatters: Sequence[Formatter], paths: Sequence[Path]) -> List[str]:
    """Format 'paths' with each formatter that takes their suffix"""

    return [failure for f in formatters for failure in f.format(paths)]
