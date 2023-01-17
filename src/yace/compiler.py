import logging as log
import typing
from pathlib import Path

from yace import __version__ as version
from yace.model.linter import Linter
from yace.model.model import Model
from yace.targets.capi.target import CAPI


class Compiler(object):
    """Encapsulation of **yace** compiler stages"""

    STAGES = ["parse", "lint", "emit", "format", "check"]
    TARGETS = [CAPI]

    def __init__(
        self, stages: typing.List[str], targets: typing.List[str], output: Path
    ):
        self.output = output.resolve()
        self.stages = stages
        self.targets = targets

    def process(self, path: Path):
        """Compile the model given at 'path' into C API and FFIs"""

        log.info("Path: '%s'", path)
        self.output.mkdir(parents=True, exist_ok=True)

        log.info("Stage: 'parse'")
        model = Model.from_path(path)

        if "lint" in self.stages:
            log.info("Stage: 'lint'")
            nerrors = Linter().check(model)
            if nerrors:
                log.error("Skipping remaining stages, due to linter-errors")
                return

        target = CAPI(model, self.output)
        if "emit" in self.stages:
            log.info("Stage: 'emit'")
            target.emit()

        if "format" in self.stages:
            log.info("Stage: 'format'")
            target.format()

        if "check" in self.stages:
            log.info("Stage: 'check'")
            target.check()
