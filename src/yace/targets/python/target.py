# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The Python target: a module binding the API through ctypes, with the records
as ctypes structures and unions that print themselves as YAML or JSON, the
enums as IntEnum, and a check of what it generated

Emits, into ``<output>/python``:

* ``<prefix>.py``, the bindings, or ``<prefix>_.py`` where the prefix names a
  module of Python's standard library, such as ``zlib``
* ``<prefix>_check.py``, the check program
* ``<prefix>.pxd``, the C API for Cython, and ``lib<prefix>.h``, the C API, as
  the C target emits it, which the ``.pxd`` declares
* ``<prefix>_check.pyx``, the check of the ``.pxd``

C names are kept, so the documentation of the C API applies: functions,
constants and enum members by their C names, as Python's own modules bind C
APIs. Only types are renamed, to CamelCase, as Python names classes:
``struct foo_point`` is ``FooPoint``.
"""

import importlib.util
import json
import logging as log
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yace import toolchain
from yace.ir import decls
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model, host_abi
from yace.targets.capi import cgen
from yace.targets.capi.target import header
from yace.targets.idiom import Idioms
from yace.targets.target import Target

from . import cygen, idiomatic, pygen

# What the C compiler is not to let pass in the C Cython makes of the check of
# the .pxd, where a declaration disagrees with the header
CYTHON_CHECK_CFLAGS = [
    "-Werror=incompatible-pointer-types",
    "-Werror=int-conversion",
    "-Werror=pointer-sign",
]


def define_value(value) -> str:
    if isinstance(value, decls.StrLiteral):
        return json.dumps(value.value)
    if value.base == 16 and value.value >= 0:
        return hex(value.value)
    return str(value.value)


def oneline(text: str) -> str:
    return " ".join(text.split())


def pysafe(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def module_name(model: Model) -> str:
    """The name of the module: the prefix, other than a module of Python's
    standard library, which an import would find instead, or hide"""

    prefix = cgen.c_ident(model.meta.prefix)
    stdlib = set(sys.stdlib_module_names) | set(sys.builtin_module_names)
    return f"{prefix}_" if prefix in stdlib else prefix


class Python(Target):
    NAME = "python"
    TOOLCHAINS = (toolchain.PYTHON, toolchain.CC)

    def environment(self) -> Environment:
        env = Environment(
            loader=FileSystemLoader(Path(__file__).parent),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        env.filters.update(
            define_value=define_value,
            docstring=pygen.docstring,
            ident=pygen.ident,
            is_union=lambda record: isinstance(record, decls.Union),
            oneline=oneline,
            pysafe=pysafe,
            quoted=pygen.quoted,
        )
        return env

    def context(self, model: Model) -> dict:
        prefix = cgen.c_ident(model.meta.prefix)
        namer = pygen.Namer(model)
        entities = model.entities
        functions = [e for e in entities if isinstance(e, decls.Function)]
        typedefs = [
            e
            for e in entities
            if isinstance(e, decls.Typedef) and e.name not in namer.aliases
        ]
        complete = cgen.ordered_records(model)

        # Resolve every type now, so the stubs of those the IR does not define
        # are known before the module is laid out
        for entity in typedefs:
            namer.ctype(entity.typ)
        for record in complete:
            namer.fields(record)
        for function in functions:
            namer.ctype(function.ret)
            for param in function.params:
                namer.ctype(param.typ, True)

        library = model.meta.name or prefix
        if library.startswith("lib"):
            library = library[3:]

        pxd = cygen.Pxd(model)
        return {
            "meta": model.meta,
            "module": module_name(model),
            "PREFIX": prefix.upper(),
            "Prefix": pygen.camel(prefix),
            "library": library,
            "namer": namer,
            "defines": [e for e in entities if isinstance(e, decls.Define)],
            "enums": [e for e in entities if isinstance(e, decls.Enum)],
            "records": [e for e in entities if isinstance(e, decls.RECORDS)],
            "complete": complete,
            "printable": [r for r in complete if not namer.is_blob(r)],
            "blobs": [r for r in complete if namer.is_blob(r)],
            "typedefs": typedefs,
            "stubs": sorted(namer.stubs.items()),
            "functions": [f for f in functions if not f.variadic],
            "variadic": [f for f in functions if f.variadic],
            "params": pygen.params,
            "argument": pygen.argument,
            "errcheck": pygen.errcheck,
            "direct": pygen.direct,
            "record_kind": cgen.tag,
            "layout": model.meta.abi == host_abi(),
            "value_key": VALUE_KEY,
            "accessor": pygen.accessor,
            "attribute": pygen.attribute,
            "idiomatic": idiomatic.Renderer(Idioms(model), namer).render(),
            "stdint": cygen.CIMPORTS["libc.stdint"],
            "declarations": pxd.lines(),
            "check": cygen.Check(pxd).render(),
        }

    def emit(self, model: Model) -> list:
        env = self.environment()
        context = self.context(model)
        prefix = context["module"]

        paths = []
        for filename, template in [
            (f"{prefix}.py", "module.py.template"),
            (f"{prefix}_check.py", "check.py.template"),
            (f"{prefix}.pxd", "module.pxd.template"),
            (f"{prefix}_check.pyx", "check.pyx.template"),
        ]:
            path = self.output / filename
            path.write_text(env.get_template(template).render(**context))
            paths.append(path)

        # The C API, as the C target emits it, which the .pxd declares
        path = self.output / f"lib{model.meta.prefix}.h"
        path.write_text(header(model))
        paths.append(path)

        return paths

    def check(self, model: Model) -> list:
        """Run the check program, and, where there is Cython, compile the check
        of the .pxd; returns what failed, if anything"""

        prefix = module_name(model)
        env = {**os.environ, "PYTHONPATH": str(self.output)}

        failures = []
        for fmt in ("yaml", "json"):
            proc = subprocess.run(
                [sys.executable, str(self.output / f"{prefix}_check.py"), fmt],
                capture_output=True,
                text=True,
                env=env,
            )
            (self.output / f"check.{fmt}").write_text(proc.stdout)
            if proc.returncode:
                failures.append(f"the check failed printing {fmt}:\n{proc.stderr}")
                continue
            try:
                if fmt == "yaml":
                    list(yaml.safe_load_all(proc.stdout))
                else:
                    [json.loads(line) for line in proc.stdout.splitlines()]
            except (yaml.YAMLError, json.JSONDecodeError) as exc:
                failures.append(f"the pretty-printers print invalid {fmt}: {exc}")

        return failures + self.cython(model)

    def cython(self, model: Model) -> list:
        """Translate the check of the .pxd with Cython, and compile what it made
        of it with the header, so a declaration that disagrees with the header
        fails; where the Python running yace has no Cython, it warns that the
        .pxd is not checked, and fails nothing"""

        out = self.output.resolve()
        if importlib.util.find_spec("Cython") is None:
            note = f"the .pxd is not checked: no Cython in {sys.executable}"
            (out / "cython.log").write_text(f"{note}\n")
            log.warning("python: %s", note)
            return []
        pyx = out / f"{module_name(model)}_check.pyx"
        source = out / "pxd_check.c"
        cmd = [sys.executable, "-m", "cython", "-3", str(pyx), "-o", str(source)]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=out)
        logged = [f"{' '.join(cmd)}\n{proc.stdout}{proc.stderr}"]
        (out / "cython.log").write_text("\n".join(logged))
        if proc.returncode:
            return [f"Cython failed on the check of the .pxd:\n{proc.stderr}"]

        failures = toolchain.missing(self.TOOLCHAINS)
        if failures:
            return failures
        cc = toolchain.CC.command()
        includes = [sysconfig.get_paths()["include"], str(out), *self.include]
        cmd = [cc, "-fsyntax-only", *CYTHON_CHECK_CFLAGS]
        cmd += [f"-I{path}" for path in includes] + [str(source)]
        proc = subprocess.run([str(arg) for arg in cmd], capture_output=True, text=True)
        logged.append(f"{' '.join(map(str, cmd))}\n{proc.stdout}{proc.stderr}")
        (out / "cython.log").write_text("\n".join(logged))
        if proc.returncode:
            return [f"compiling the check of the .pxd failed:\n{proc.stderr}"]
        return []
