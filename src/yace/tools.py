"""
Tools used by targets to do what they do... a brief overview:

* :class:`.Black`
* :class:`.ClangFormat`
* :class:`.Doxygen`
* :class:`.Gcc`
* :class:`.Isort`

The above tools needs to be installed on the system. These classes inherit the
``run()`` from the :class:`.Tool`.
"""
import logging as log
import typing
from subprocess import run


class Tool(object):
    """
    Default arguments for the invocation of system tools, provided as a
    mixin-class for
    """

    def run(self, cmd: typing.List[str]):
        """Run subprocess.run() using arguments other than the defaults"""

        return run(
            cmd,
            check=True,
            cwd=self.output,
        )


class Black(Tool):
    """
    Mixin-class: run ``black`` on the generated source files (``self.sources``)
    """

    def black(self, args: typing.List[str]):
        """..."""

        return self.run(["black"] + [self.sources])

    def format_black(self):
        """Format :attr:`self.sources` using :class:`.Black`"""

        return self.black(self.sources)


class ClangFormat(Tool):
    """
    Format the files:

    * self.sources using :attr:`.ClangFormat.CLANGFORMAT_STYLE_C`
    * self.headers using :attr:`.ClangFormat.CLANGFORMAT_STYLE_H`
    """

    CLANGFORMAT_STYLE_C = "src.clang-format"  # Style-file to use for .c files
    CLANGFORMAT_STYLE_H = "hdr.clang-format"  # Style-file to use for .h files

    def clang_format(self, args: typing.List[str]):
        """Run ``clang-format``, passing it the given 'args'"""

        return self.run(["clang-format"] + args)

    def format_clang_format(self):
        """
        Format self.sources, self.headers using ``clang-format``
        """

        for filename, container in [
            (ClangFormat.CLANGFORMAT_STYLE_C, self.sources),
            (ClangFormat.CLANGFORMAT_STYLE_H, self.headers),
        ]:
            result = self.clang_format(
                [f"--style=file:{filename}", "-i"] + [str(f) for f in container],
            )
            if result.returncode:
                log.error(f"clang_format: failed({result})")


class Doxygen(Tool):
    """
    Mixin-class: run doxygen in the self.output, using rulefile
    :attr:`.Doxygen.DOXYGEN_CONF`

    The filename is provided as a variable such that it can be used by the
    emitter.
    """

    DOXYGEN_CONF = "doxygen.conf"  # Filename of the Doxygen configuration file

    def doxygen(self, args: typing.List[str]):
        """Run 'doxygen' using :attr:`.Doxygen.DOXYGEN_CONF`"""

        return self.run(["doxygen"] + args)

    def docs_doxygen(self):
        """Run ``doxygen`` using :attr:`.Doxygen.DOXYGEN_CONF`"""

        result = self.doxygen([f"{Doxygen.DOXYGEN_CONF}"])
        if result.returncode:
            log.error(f"doxygen: failed({result})")

        return result


class Gcc(Tool):
    """
    Mixin-class: run ``gcc`` passing 'args' or invoke gcc on self.sources in
    self.output
    """

    def gcc(self, args: typing.List[str]):
        """Run gcc, with cwd=self.output, using the given args"""

        result = self.run(["gcc"] + args)
        if result.returncode:
            log.error(f"gcc: failed{result})")

    def gcc_build_check(self):
        """Run gcc using the given args"""

        self.gcc(self.sources)


class Isort(Tool):
    """
    Mixin-class: run ``isort`` on the generated source files (``self.sources``)
    """

    def isort(self, args: typing.List[str]):
        """Run ``isort`` using the given args"""

        return self.run(["isort", self.sources])

    def format_isort(self):
        """Sorts the import-statements of self.sources"""

        return self.isort(self.sources)
