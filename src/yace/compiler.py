import logging as log
import typing
from pathlib import Path

from yace import __version__ as version
from yace.model.linter import Linter
from yace.model.model import Model
from yace.targets.capi.target import CAPI


class Compiler(object):
    """
    Encapsulation of **yace** compiler stages

    * Parse
    * Lint
    * Emit
    * Format
    * Check

    The first two stages are generic, the last three are target-specific.
    """

    STAGES = ["parse", "lint", "emit", "format", "check"]
    TARGETS = [CAPI]

    def __init__(self, targets: typing.List[str], output: Path):
        self.targets = [target for target in Compiler.TARGETS if target.NAME in targets]
        self.output = output.resolve()

    def process(self, path: Path, stages: typing.List[str] = None):
        """
        Take 'path' through the given compiler 'stages'
        """

        if stages is None:
            stages = Compiler.STAGES

        log.info("Path: '%s', stages: '%s'", path, stages)
        self.output.mkdir(parents=True, exist_ok=True)

        log.info("Stage: 'parse'")
        model = Model.from_path(path)

        if "lint" in stages:
            log.info("Stage: 'lint'")
            nerrors = Linter().check(model)
            if nerrors:
                log.error("Skipping remaining stages, due to linter-errors")
                return

        target = CAPI(self.output)
        if "emit" in stages:
            log.info("Stage: 'emit'")
            target.emit(model)

        if "format" in stages:
            log.info("Stage: 'format'")
            target.format()

        if "check" in stages:
            log.info("Stage: 'check'")
            target.check()
