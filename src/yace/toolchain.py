"""
The toolchains the checks of the targets build with: for each, the variable of
the environment naming its command, the command used where it is unset, and how
to ask it for its version. A target names its own in 'Target.TOOLCHAINS'.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Toolchain:
    """A command a check runs: 'env' names it where set, else 'default'"""

    what: str
    env: Optional[str]
    default: str
    version: Tuple[str, ...] = ("--version",)

    def command(self) -> str:
        return os.environ.get(self.env, self.default) if self.env else self.default

    def missing(self) -> Optional[str]:
        """Why the check cannot run, or None where the command is found"""

        if shutil.which(self.command()):
            return None
        hint = f"; set {self.env}" if self.env else ""
        return f"no {self.what} ('{self.command()}'){hint}"

    def find(self) -> Dict:
        """The command, where it is found, and the first line of its version"""

        found: Dict[str, Any] = {"what": self.what, "env": self.env, "command": None}
        found["command"] = self.command()
        path = shutil.which(self.command())
        found.update({"present": path is not None, "path": path, "version": None})
        if path:
            proc = subprocess.run(
                [path, *self.version], capture_output=True, text=True, check=False
            )
            lines = (proc.stdout or proc.stderr).strip().splitlines()
            found["version"] = lines[0].strip() if lines else None
        return found


CC = Toolchain("C compiler", "CC", "cc")
CXX = Toolchain("C++ compiler", "CXX", "c++")
CARGO = Toolchain("Rust toolchain", "CARGO", "cargo")
ZIG = Toolchain("Zig toolchain", "ZIG", "zig", ("version",))
GO = Toolchain("Go toolchain", "GO", "go", ("version",))
PYTHON = Toolchain("Python", None, sys.executable)


def missing(toolchains: List[Toolchain]) -> List[str]:
    """The failures of a check whose toolchains are not all found"""

    return [why for why in (tc.missing() for tc in toolchains) if why]
