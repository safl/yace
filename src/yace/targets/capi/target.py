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

import copy
import logging as log
import shutil
from pathlib import Path

from yace.emitters import Emitter
from yace.errors import TransformationError
from yace.targets.target import Target
from yace.tools import ClangFormat, Doxygen, Gcc
from yace.transformations import CStyle


def emit_cstr_fmt(typespec):
    if typespec.integer:
        return f'%"PRIx{ typespec.width }"'
    elif typespec.boolean:
        return "%d"

    return f"MISSING_CSTR_FMT({typespec})"


def emit_typespec(typespec, anon: bool = False):
    return typespec.c_spelling()


class CAPI(Target):
    """
    Several helper functions
    """

    NAME = "capi"
    CFLAGS = ["-std=c11", "-pedantic-errors", "-Wall", "-Werror"]

    def __init__(self, output):
        super().__init__(self.NAME, output)

        self.emitter = Emitter(Path(__file__).parent)

        self.tools["clang-format"] = ClangFormat(self.output)
        self.tools["doxygen"] = Doxygen(self.output)
        self.tools["gcc"] = Gcc(self.output)

    def transform(self, model):
        """
        Transform the given model

        * Transform symbols according to :class:`yace.transformation.CStyle`

        That it currently the only thing done to the **yace** IR.
        """

        transformed = copy.deepcopy(model)

        status = CStyle(transformed).walk()
        if not all([res for res in status]):
            raise TransformationError("The CStyle transformation failed")

        return transformed

    def emit(self, model):
        """Emit code"""

        filters = {
            "emit_cstr_fmt": emit_cstr_fmt,
            "emit_typespec": emit_typespec,
        }

        files = [
            (f"lib{model.meta.prefix}_core.h", "file_core.h", self.headers),
            (f"lib{model.meta.prefix}_pp.h", "file_pp.h", self.headers),
            (f"lib{model.meta.prefix}.h", "file_bundle.h", self.headers),
            (f"{model.meta.prefix}_pp.c", "file_pp.c", self.sources),
            (f"{model.meta.prefix}_check.c", "file_check.c", self.sources),
            ("doxygen.conf", "doxygen", self.aux),
        ]
        for filename, template, container in files:
            path = (self.output / filename).resolve()
            with (path).open("w") as file:
                content = self.emitter.render(
                    template,
                    {
                        "meta": model.meta,
                        "entities": model.entities,
                        "headers": self.headers,
                    },
                    filters,
                )
                if content[-1] != "\n":
                    content += "\n"
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

        self.tools["gcc"].run(
            CAPI.CFLAGS + ["-I", str(self.output)] + [str(p) for p in self.sources]
        )
