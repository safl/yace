"""
What to do about "static" and "const"? The filter_typedecl.template currently
ignores them, except for the special-case "c_char_p".

"""
import copy
import logging as log
import shutil
import typing
from pathlib import Path

from yace.emitters import Emitter
from yace.errors import ToolError
from yace.targets.target import Target
from yace.tools import Black, Isort, Python3


class Ctypes(Target):
    """
    Several helper functions
    """

    NAME = "ctypes"

    def __init__(self, output):
        super().__init__(Ctypes.NAME, output)

        self.emitter = Emitter(self.output, Ctypes.NAME)

        self.tools = {
            "black": Black(self.output),
            "isort": Isort(self.output),
            "python": Python3(self.output),
        }

    def transform(self, model):
        """Transform the given idl, flatten nested structs/unions"""

        log.info("This is noop in target '%s'", Ctypes.NAME)

        return copy.deepcopy(model)

    def emit(self, model):
        """Emit code"""

        # Copy the generic ctypes-sugar from resources
        sugar_path = (self.output / "ctypes_sugar.py").resolve()
        shutil.copyfile(Path(__file__).parent / sugar_path.name, sugar_path)
        self.sources.append(sugar_path)

        # Generate the bindings / Python API
        files = [
            ((self.output / f"{model.meta.prefix}.py").resolve(), "file_api"),
            ((self.output / f"{model.meta.prefix}_check.py").resolve(), "file_check"),
        ]
        for path, template in files:
            with path.open("w") as file:
                file.write(
                    self.emitter.render(
                        template,
                        {
                            "meta": model.meta,
                            "entities": model.entities,
                            "headers": self.headers,
                        },
                    )
                )
            self.sources.append(path)

    def format(self):
        """
        Run 'black' and 'isort' on self.sources
        """

        for tool in ["black", "isort"]:
            self.tools[tool].run([str(path) for path in self.sources])

    def check(self):
        """Build generated sources and run the generated test-program"""

        log.info("Not there yet...")
