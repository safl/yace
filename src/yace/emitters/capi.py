"""
The :class:`.CAPI` emitter produces, formats, and check a C API with:

* ``lib{meta.prefix}.h``        -- Library header bundle
* ``lib{meta.prefix}_core.h``   -- The core API declarations
* ``lib{meta.prefix}_pp.h``     -- Pretty-printer definitions
* ``{meta.prefix}_pp.c``        -- Pretty-printer implementation
* ``{meta.prefix}_check.c``     -- ``main()`` program checking  generated code
* ``doxygen.conf``              -- Doxygen configuration for the above

Very neat :)
"""
import typing
from pathlib import Path

from jinja2 import Environment, PackageLoader

from yace.model.entities import Entity
from yace.model.interface import InterfaceModel, Meta
from yace.model.macros import Define

from .emitter import Emitter


class CAPI(Emitter):
    """
    Several helper functions
    """

    def __init__(self, model, output):
        super().__init__(model, output)

        self.headers = []
        self.sources = []
        self.aux = []

    def emit(self):
        """Emit code"""

        files = [
            (f"lib{self.meta.prefix}_core.h", "capi_core_h", self.headers),
            (f"lib{self.meta.prefix}_pp.h", "capi_pp_h", self.headers),
            (f"lib{self.meta.prefix}.h", "capi_bundle_h", self.headers),
            (f"{self.meta.prefix}_pp.c", "capi_pp_c", self.sources),
            (f"{self.meta.prefix}_check.c", "capi_check_c", self.sources),
            ("doxygen.conf", "doxygen", self.sources),
        ]
        for filename, template, container in files:
            with (self.output / filename).open("w") as file:
                file.write(
                    self.templates[template].render(
                        meta=self.meta,
                        entities=self.model.entities,
                        headers=self.headers,
                    )
                )
            container.append(filename)

    def format(self):
        """Run clang-format"""

        pass

    def check(self):
        """Run the generated test-program"""

        pass
