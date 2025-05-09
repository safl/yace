"""
What to do about "static" and "const"? The filter_typedecl.template currently
ignores them, except for the special-case "c_char_p".

"""

import copy
import ctypes
import logging as log
import re
import shutil
import textwrap
from pathlib import Path

from yace.emitters import Emitter
from yace.errors import TransformationError
from yace.targets.target import Target
from yace.tools import Black, Isort, Python3
from yace.transformations import Camelizer, Modulizer


def emit_typespec(typespec, anon: bool = False):
    return typespec.python_spelling()


def wrap(text, indent="", width=72):
    return '\n'.join(textwrap.wrap(text, width=width, subsequent_indent=indent))


def sizeof(ctypes_member: str):
    return ctypes.sizeof(getattr(ctypes, ctypes_member))


class Ctypes(Target):
    """
    Several helper functions
    """

    NAME = "ctypes"

    def __init__(self, output):
        super().__init__(Ctypes.NAME, output)

        self.emitter = Emitter(Path(__file__).parent)

        self.tools = {
            "black": Black(self.output),
            "isort": Isort(self.output),
            "python": Python3(self.output),
        }

    def transform(self, model):
        """
        Transform the given model

        * Transform symbols according to :class:`yace.transformation.CStyle`

        That it currently the only thing done to the **yace** IR.
        """

        transformed = copy.deepcopy(model)

        status = Modulizer(transformed).walk()
        if not all([res for res in status]):
            raise TransformationError("The transformation to Python modules failed")

        status = Camelizer(transformed).walk()
        if not all([res for res in status]):
            raise TransformationError("The CStyle transformation failed")

        return transformed

    def emit(self, model):
        """Emit code"""

        filters = {
            "emit_typespec": emit_typespec,
            "wrap": wrap,
            "sizeof": sizeof,
        }

        output = (self.output / model.meta.prefix).resolve()
        output.mkdir(parents=True, exist_ok=True)

        raw_path = (output / "raw").resolve()
        raw_path.mkdir(parents=True, exist_ok=True)

        modules = dict()

        for entity in model.entities:
            if not entity.module:
                entity.module = "unknown"
            
            if entity.module not in modules:
                modules[entity.module] = []

            modules[entity.module].append(entity)
        
        # Copy the generic ctypes-sugar from resources
        sugar_path = (output / "ctypes_sugar.py").resolve()
        shutil.copyfile(Path(__file__).parent / sugar_path.name, sugar_path)
        self.sources.append(sugar_path)

        # Copy the generic init file from resources
        init_path = (output / "__init__.py").resolve()
        shutil.copyfile(Path(__file__).parent / "init.py", init_path)
        self.sources.append(init_path)

        # Generate helper files
        files = [
            ((output / "util.py").resolve(), "util", {}),
            ((output / f"{model.meta.prefix}_check.py").resolve(), "file_check", { "meta": model.meta }),
            ((raw_path / "__init__.py").resolve(), "init_raw", { "imports": modules.keys() }),
        ]

        for path, template, args in files:
            with path.open("w") as file:
                file.write(
                    self.emitter.render(template, args, filters)
                )
                self.sources.append(path)

        # Generate the bindings / Python API
        for module, entities in modules.items():
            module_path = (raw_path / f"{module}.py").resolve()

            with module_path.open("w") as file:
                file.write(
                    self.emitter.render(
                        "file_api",
                        {
                            "meta": model.meta,
                            "entities": entities,
                            "headers": self.headers,
                        },
                        filters,
                    )
                )
            self.sources.append(module_path)

    def format(self):
        """
        Run 'black' and 'isort' on self.sources
        """

        for tool in ["black", "isort"]:
            self.tools[tool].run([str(path) for path in self.sources])

    def check(self):
        """Build generated sources and run the generated test-program"""

        log.info("Not there yet...")
