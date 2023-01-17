import logging as log
import typing
from pathlib import Path

from yace import __version__ as version
from yace.model.interface import Model
from yace.model.linter import Linter
from yace.targets.capi.target import CAPI


class Compiler(object):
    """Encapsulation of **yace** compiler stages"""

    STAGES = ["parse", "lint", "emit", "format", "check"]

    def __init__(
        self, stages: typing.List[str], targets: typing.List[str], output: Path
    ):
        self.output = output
        self.stages = stages
        self.targets = targets

    def compile(self, path: Path):
        """Compile the model given at 'path' into C API and FFIs"""

        self.output.mkdir(parents=True, exist_ok=True)

        # STAGE[Parse]
        model = Model.from_path(path)

        # STAGE[Lint]
        if "lint" in self.stages:
            nerrors = Linter().check(model)
            log.info("Stage[Linter] found #errors: %d", nerrors)
            if nerrors:
                log.error("Skipping remaining stages, due to linter-errors")
                return

        # STAGE[Emit]
        target = CAPI(model, self.output)
        if "emit" in self.stages:
            target.emit()

        # STAGE[Format]
        if "format" in self.stages:
            target.format()

        # STAGE[Check]
        if "check" in self.stages:
            target.check()
