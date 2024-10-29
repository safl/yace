"""
Tools used by targets to do what they do. The tool-classes are wrapper-classes
around executables. A brief overview:

* :class:`.Black`
* :class:`.ClangFormat`
* :class:`.Doxygen`
* :class:`.Gcc`
* :class:`.Isort`

The tools listed above can be classified in the following two categories.

Code Formaters
==============

Tools such as source-code formaters (clang-format, black, isort, rustfmt),
these will change the given code according to style-definitions. When these
tools change files, then they typically terminate using a non-zero exit-code.
This is not an error as it is commonly what we wanted the tool to do, that is a
target emits format and invokes a format-tool to make it conform.

Thus the tool is usually invoked twice, once for formating, and a second time
for checking that the code is well-formatted.

The above tools needs to be installed on the system. These classes inherit the
``run()`` from the :class:`.Tool`. Invoking a system :class:`.Tool` raises
:class:`.ToolError`.

Compilers
=========

Compilers such as :class:`.Gcc` usually terminate with a non-zero exit-code
when the input-program / source is invalid. Re-running the compiler does not
change this, the program needs to be changed. Something is wrong, and the user
needs to fix it.

Interpreters
============

...
"""

import logging as log
import typing
from pathlib import Path
from subprocess import STDOUT, run


class Tool(object):
    """
    Wrapper-class for invoking system tools
    """

    def __init__(self, executable, cwd):
        self.executable = executable
        self.cwd = cwd

    def run(self, args: typing.List[str]):
        """
        Invoke subprocess.run([self.executable] + args, ...); logging stdout
        and stderr to the given 'logfile' using arguments and self.cwd as
        cwd.

        On success, proc is returned.
        """

        logpath = (Path(self.cwd) / f"{self.executable}.log").resolve()
        cmd = [self.executable] + args

        with logpath.open("a") as logfile:
            logfile.write(f"# cmd({' '.join(cmd)})\n")
            logfile.write(f"# cwd({self.cwd})\n")
            logfile.flush()

            proc = run(
                cmd,
                stdout=logfile,
                stderr=STDOUT,
                check=False,
                capture_output=False,
                cwd=self.cwd,
            )

        rcode = proc.returncode
        if rcode:
            log.error(
                f"cmd({' '.join(cmd)}) exited with rcode({rcode}),"
                f" see logfile({logfile.name}) for details"
            )

        return rcode, proc

    def exists(self):
        """Returns true if the tool exists."""

        try:
            rcode, _ = self.run(["--version"])
            return rcode == 0
        except FileNotFoundError:
            log.error("executable(%s); FileNotFound", self.executable)

        return False


class Black(Tool):
    """
    Wrapper for the system-tool ``black``, usually utilized to format code
    emitted by Python-targets
    """

    def __init__(self, cwd):
        super().__init__("black", cwd)


class ClangFormat(Tool):
    """
    Wrapper for ``clang-format``
    """

    CLANGFORMAT_STYLE_C = "clang-format-c.clang-format"  # Style for .c files
    CLANGFORMAT_STYLE_H = "clang-format-h.clang-format"  # Style for .h files
    CLANGFORMAT_BIN = "clang-format"  # Name of the clang-format binary

    def __init__(self, cwd):
        super().__init__(ClangFormat.CLANGFORMAT_BIN, cwd)


class Doxygen(Tool):
    """
    Wrapper for ``doxygen``

    Run 'doxygen' using :attr:`.Doxygen.DOXYGEN_CONF`
    """

    DOXYGEN_CONF = "doxygen.conf"  # Filename of the Doxygen configuration file
    DOXYGEN_BIN = "doxygen"  # Name of the doxygen binary / executable

    def __init__(self, cwd):
        super().__init__(Doxygen.DOXYGEN_BIN, cwd)


class Gcc(Tool):
    """
    Wrapper for ``gcc``
    """

    def __init__(self, cwd):
        super().__init__("gcc", cwd)


class Isort(Tool):
    """
    Wrapper for ``isort``
    """

    def __init__(self, cwd):
        super().__init__("isort", cwd)


class Python3(Tool):
    """
    Wrapper for ``python3``
    """

    def __init__(self, cwd):
        super().__init__("python3", cwd)
