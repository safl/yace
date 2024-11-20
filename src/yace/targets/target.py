"""

"""

import os
from abc import ABC, abstractmethod


class Target(ABC):
    """
    Encapsulation of a **yace** Emitter Target (yet). This serves as
    documentation for what is needed when adding a target to **yace**.
    Additionally, the Target-constructur sets up commonly used attributes of
    the Target and creates the sub-directory for artifacts produced by the
    target. Labelled, as artifacts, as it is not just for the emitted code, but
    also log-files from running tools, and other similar side-effects.
    """

    def __init__(self, name, output):
        self.name = name  # Name of the compiler-target
        self.output = output / name  # Location to emit code to

        self.headers = []  # Resolved paths to emitted headers
        self.sources = []  # Resolved paths to emitted sources
        self.aux = []  # Resolved paths to auxilary files e.g. Doxy Conf

        self.tools = {}  # Dictionary of :class:`yace.tools.Tool` instances

        os.makedirs(self.output, exist_ok=True)

    def is_ready(self):
        """Pre-flight check, inspect availability of self.tools"""

        return all([tool.exists() for label, tool in self.tools.items()])

    @abstractmethod
    def transform(self, model):
        """
        Transform the given model for code-emission.
        """

    @abstractmethod
    def emit(self, model):
        """
        Emit code for the given model, using your weapons of choice, common
        choice would be to utilize an instance of the class:`.Emitter`.
        """

    @abstractmethod
    def format(self):
        """
        Format the emitted source-code, e.g. call tools such as clang-format,
        black, isort, rustfmt, etc. depending of what applies to the generated
        code.
        """

    @abstractmethod
    def check(self):
        """
        Compile the generated code and execute it. Or in case of an interpreted
        language just execute something verifying the generated code. This
        could for example be a test-program emitted earlier.
        """
