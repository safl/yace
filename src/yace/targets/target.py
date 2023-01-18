"""

"""
from abc import ABC, abstractmethod


class Target(ABC):
    """
    Encapsulation of a **yace** Emitter Target (yet). This serves as
    documentation for what is needed when adding a **yet** to **yace**.
    """

    def __init__(self, name, output):
        self.name = name  # Name of the compiler-target
        self.output = output  # Location to emit code to
        self.headers = []  # Resolved paths to emitted headers
        self.sources = []  # Resolved paths to emitted sources
        self.aux = []  # Resolved paths to auxilary files e.g. Doxy Conf

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
