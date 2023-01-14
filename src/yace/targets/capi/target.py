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
from yace.tools import ClangFormat, Doxygen, Gcc


class CAPI(Emitter, ClangFormat, Doxygen, Gcc):
    """
    Several helper functions
    """

    def __init__(self, model, output):
        super().__init__(model, output, "capi")

        self.headers = []  # Resolved paths to emitted headers
        self.sources = []  # Resolved paths to emitted sources
        self.aux = []  # Resolved paths to auxilary files e.g. Doxy Conf

    def lint(self):
        """Lint..."""

        log.info("lint ...")

    def emit(self):
        """Emit code"""

        log.info("emit ...")

        files = [
            (f"lib{self.meta.prefix}_core.h", "capi_core_h", self.headers),
            (f"lib{self.meta.prefix}_pp.h", "capi_pp_h", self.headers),
            (f"lib{self.meta.prefix}.h", "capi_bundle_h", self.headers),
            (f"{self.meta.prefix}_pp.c", "capi_pp_c", self.sources),
            (f"{self.meta.prefix}_check.c", "capi_check_c", self.sources),
            ("doxygen.conf", "doxygen", self.aux),
        ]
        for filename, template, container in files:
            path = (self.output / filename).resolve()
            with (path).open("w") as file:
                file.write(
                    self.templates[template].render(
                        meta=self.meta,
                        entities=self.model.entities,
                        headers=self.headers,
                    )
                )
            container.append(path)

    def format(self):
        """
        Transfer the clang-format definition from package to output and
        invokes the clang-formater
        """

        log.info("format ...")

        path = Path(__file__).parent
        for rules in [
            ClangFormat.CLANGFORMAT_STYLE_H,
            ClangFormat.CLANGFORMAT_STYLE_C,
        ]:
            shutil.copyfile(path / rules, self.output / rules)

        self.format_clang_format()
        self.docs_doxygen()

    def check(self):
        """Run the generated test-program"""

        log.info("check ...")

        cmd = ["-I", str(self.output)] + [str(p) for p in self.sources]
        log.info("cmd(%s)", " ".join(cmd))

        self.gcc_build_check(cmd)
