"""
The :class:`.CAPI` emits a C API consisting of the following files:

* ``lib{meta.prefix}.h``        -- Library header bundle
* ``lib{meta.prefix}_core.h``   -- The core API declarations
* ``lib{meta.prefix}_pp.h``     -- Pretty-printer definitions
* ``{meta.prefix}_pp.c``        -- Pretty-printer implementation

additionally then:

* ``{meta.prefix}_check.c``     -- ``main()`` program checking generated code

This program is utilized by the 'check-stage' and is as such not part of the
emitted C API but rather a test of it.

Last then:

* ``doxygen.conf``              -- Doxygen configuration for the above

Is emitted, this is to produce DoxyGen documentation for API.

The 'format' stage also emits the files:

* ``hdr.clang-format`` -- clang-format rule-file for header-files
* ``src.clang-format`` -- clang-format rule-file for source-files

Thus, the above files are what you should expect to see in the output-directory
"""
import logging as log
import shutil
import typing
from pathlib import Path

from yace.emitters import Emitter
from yace.errors import ToolError
from yace.targets.target import Target
from yace.tools import ClangFormat, Doxygen, Gcc


class CAPI(Target):
    """
    Several helper functions
    """

    def __init__(self, model, output):
        self.name = "capi"
        self.model = model
        self.output = output

        self.headers = []  # Resolved paths to emitted headers
        self.sources = []  # Resolved paths to emitted sources
        self.aux = []  # Resolved paths to auxilary files e.g. Doxy Conf

        self.emitter = Emitter(self.model, self.output, self.name)

        self.tools = {
            "clang-format": ClangFormat(output),
            "doxygen": Doxygen(output),
            "gcc": Gcc(output),
        }

    def emit(self):
        """Emit code"""

        files = [
            (f"lib{self.model.meta.prefix}_core.h", "capi_core_h", self.headers),
            (f"lib{self.model.meta.prefix}_pp.h", "capi_pp_h", self.headers),
            (f"lib{self.model.meta.prefix}.h", "capi_bundle_h", self.headers),
            (f"{self.model.meta.prefix}_pp.c", "capi_pp_c", self.sources),
            (f"{self.model.meta.prefix}_check.c", "capi_check_c", self.sources),
            ("doxygen.conf", "doxygen", self.aux),
        ]
        for filename, template, container in files:
            path = (self.output / filename).resolve()
            with (path).open("w") as file:
                content = self.emitter.render(
                    template,
                    {
                        "meta": self.model.meta,
                        "entities": self.model.entities,
                        "headers": self.headers,
                    },
                )
                file.write(content)

            log.info("produced: %s", path)
            container.append(path)

    def format(self):
        """
        Transfer the clang-format definition from package to output and
        invokes the clang-formater
        """

        path = Path(__file__).parent
        for rules, container in [
            (ClangFormat.CLANGFORMAT_STYLE_C, self.sources),
            (ClangFormat.CLANGFORMAT_STYLE_H, self.headers),
        ]:
            shutil.copyfile(path / rules, self.output / rules)
            self.tools["clang-format"].run(
                [f"--style=file:{rules}", "-i"] + [str(f) for f in container],
            )

        self.tools["doxygen"].run([Doxygen.DOXYGEN_CONF])

    def check(self):
        """Build generated sources and run the generated test-program"""

        self.tools["gcc"].run(["-I", str(self.output)] + [str(p) for p in self.sources])
