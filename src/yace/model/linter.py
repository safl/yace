import logging as log
import typing

from yace.model.model import ModelWalker


class Linter(ModelWalker):
    """
    Language Integrity checker, for the **yace** Interface Model.
    """

    def visit(self, current, ancestors, depth: int):
        """
        Visits the entity / typedecl and returns the status is_valid() on it
        """

        return current.is_valid()

    def check(self, model):
        """
        Returns the number of integrity issues found checking checking the
        given model. Any messages are logged.
        """

        nerrors = 0
        for is_valid, message in self.walk(model):
            if is_valid:
                continue

            nerrors += 1
            log.error("message(%s)", message)

        return nerrors
