"""

"""
from abc import ABC, abstractmethod


class Target(ABC):
    """
    Encapsulation of a **yace** Emitter Target (yet). This serves as
    documentation for what is needed when adding a **yet** to **yace**.
    """

    @abstractmethod
    def lint(self):
        """
        Check the integrity of the **yace* Interface Model.
        """
        pass

    @abstractmethod
    def emit(self):
        """
        Emit code using your weapons of choice, common choice would be to
        utilize an instance of the class:`.Emitter`.
        """
        pass

    @abstractmethod
    def format(self):
        """
        Format the emitted source-code, e.g. call tools such as clang-format,
        black, isort, rustfmt, etc. depending of what applies to the generated
        code.
        """
        pass

    @abstractmethod
    def check(self):
        """
        Compile the generated code and execute it. Or in case of an interpreted
        language just execute something verifying the generated code. This
        could for example be a test-program emitted earlier.
        """
        pass
