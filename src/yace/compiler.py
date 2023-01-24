import copy
import logging as log
import typing
from pathlib import Path

from yace import __version__ as version
from yace.model.linter import Linter
from yace.model.model import Model
from yace.targets.capi.target import CAPI
from yace.targets.ctypes.target import Ctypes


class Compiler(object):
    """
    Encapsulation of **yace** compiler stages

    * Parse
    * Lint
    * Transform
    * Emit
    * Format
    * Check

    The first two stages are generic, the third is generic however is usually
    performed for target-specific-reasons such as re-structuring the IDL to
    make the code-emitter simpler, the last three are target-specific.
    """

    STAGES = ["parse", "lint", "transform", "emit", "format", "check"]
    TARGETS = [CAPI, Ctypes]

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
        model_orig = Model.from_path(path)

        if "lint" in stages:
            log.info("Stage: 'lint'")
            nerrors = Linter().check(model_orig)
            if nerrors:
                log.error("Skipping remaining stages, due to linter-errors")
                return

        for cls in self.targets:
            log.info("Target: %s", cls.NAME)

            model = copy.deepcopy(model_orig)
            target = cls(self.output)

            if "transform" in stages:
                log.info("Stage: 'transform'")
                model = target.transform(model)

            if "emit" in stages:
                log.info("Stage: 'emit'")
                target.emit(model)

            if "format" in stages:
                log.info("Stage: 'format'")
                target.format()

            if "check" in stages:
                log.info("Stage: 'check'")
                target.check()
