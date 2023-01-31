from pathlib import Path

from yace.tools import Python3, Tool


class FooBarBaz(Tool):
    """The foobar tool which is nowhere to be found"""

    def __init__(self, cwd):
        super().__init__("foo_bar_baz", cwd)


def test_tool_does_not_exist():
    """When executables does not exists, then it exists() should failed"""

    foobar = FooBarBaz(Path.cwd())
    assert not foobar.exists()


def test_tool_invalid_usage():
    """When Passing invalid arguments run() should give a non-zero rcode"""

    python = Python3(Path.cwd())
    rcode, proc = python.run(["--foo"])

    assert rcode
