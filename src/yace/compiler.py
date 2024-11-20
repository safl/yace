import copy
import logging as log
from pathlib import Path
from typing import List, Optional

from yace.model import Model
from yace.targets.capi.target import CAPI
from yace.targets.collector import collect
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

    The first two stages are generic, the third is generic however is usually performed
    for target-specific-reasons such as re-structuring the IR to make the code-emitter
    simpler, the last three are target-specific.
    """

    STAGES = ["parse", "lint", "transform", "emit", "format", "check"]
    TARGETS = list(set([CAPI, Ctypes] + collect()))

    def __init__(self, targets: List[str], output: Path):
        self.targets = [target for target in Compiler.TARGETS if target.NAME in targets]
        self.output = output.resolve()

    def process(self, path: Path, stages: Optional[List[str]] = None) -> bool:
        """
        Take 'path' through the given compiler 'stages'
        """

        if stages is None:
            stages = Compiler.STAGES

        log.info("Path: '%s', stages: '%s'", path, stages)
        self.output.mkdir(parents=True, exist_ok=True)

        log.info("Stage: 'parse'")
        model_orig = Model.from_path(path)

        targets = [cls(self.output) for cls in self.targets]
        if not all([tgt.is_ready() for tgt in targets]):
            log.error("One or more targets !ready; see above/log. stopping.")
            return False

        for target in targets:
            log.info("Target: %s", target.NAME)

            model = copy.deepcopy(model_orig)

            if "transform" in stages:
                log.info("Stage: 'transform'")
                model = target.transform(model)

            if "emit" in stages:
                log.info("Stage: 'emit'")
                err = target.emit(model)
                if err:
                    log.error("Got error, stopping.")
                    break

            if "format" in stages:
                log.info("Stage: 'format'")
                err = target.format()
                if err:
                    log.error("Got error, stopping.")
                    break

            if "check" in stages:
                log.info("Stage: 'check'")
                err = target.check()
                if err:
                    log.error("Got error, stopping.")
                    break

        return True
