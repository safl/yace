# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The Cython target emits the idiomatic API of the Python target as a module
compiled with Cython, and the C API for Cython as a ``.pxd``. The target also
checks what it emitted.

Emits, into ``<output>/cython``:

* ``<prefix>.pyx``, the module, or ``<prefix>_.pyx`` where the prefix names a
  module of Python's standard library, such as ``zlib``
* ``<prefix>.pyi``, the stub of the module: the types of what it defines
* ``<prefix>.pxd``, the C API for Cython. The module uses the declarations of
  the ``.pxd``, and other Cython code cimports the ``.pxd`` to call C
* ``lib<prefix>.h``, the C header that the ``.pxd`` declares, as the C target
  emits it
* ``<prefix>_check.py``, the check program, which prints a zeroed record of
  each type
* ``<prefix>_check.pyx``, the check of the ``.pxd``

The check translates the module with Cython, compiles the module without
linking the library, and runs the check program. The check program calls no
function of the library. The check also compiles the C that Cython generates
from ``<prefix>_check.pyx`` with the header, so a declaration in the ``.pxd``
that disagrees with the header fails to compile.
"""

import functools
import importlib.util
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import List, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yace import formatter, toolchain
from yace.ir import decls, types
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model
from yace.targets.capi import cgen
from yace.targets.capi.target import header
from yace.targets.python import pygen
from yace.targets.python.target import define_value, module_name, oneline, pysafe
from yace.targets.target import Target

from . import cygen, pyigen, pyxgen

# Warnings made errors when compiling the C that Cython generates, so that a
# declaration that disagrees with the header, or a wrong cast, fails the check
CHECK_CFLAGS = [
    "-Werror=incompatible-pointer-types",
    "-Werror=int-conversion",
    "-Werror=pointer-sign",
    "-Werror=implicit-function-declaration",
]

# GCC reports a discarded const only under this option. clang reports it as an
# incompatible pointer type and does not know the option.
DISCARDED_QUALIFIERS = "-Werror=discarded-qualifiers"

# The file suffix of an extension module of the Python running yace
SUFFIX = sysconfig.get_config_var("EXT_SUFFIX")


def define_type(value) -> str:
    """The Python type of the value of a define"""

    return "str" if isinstance(value, decls.StrLiteral) else "int"


@functools.lru_cache(maxsize=None)
def check_cflags(cc: str) -> List[str]:
    """Return CHECK_CFLAGS, with DISCARDED_QUALIFIERS added where the compiler
    'cc' accepts that option"""

    cmd = [cc, DISCARDED_QUALIFIERS, "-fsyntax-only", "-x", "c", os.devnull]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    known = proc.returncode == 0 and not proc.stderr
    return CHECK_CFLAGS + ([DISCARDED_QUALIFIERS] if known else [])


def link_args(link: Optional[List[str]]) -> List[str]:
    """Return the linker arguments of the module, linking 'link'. Without
    'link', each function of the library is resolved when first called. On
    macOS, the symbols of Python are resolved when the module is loaded."""

    if sys.platform == "darwin":
        return ["-undefined", "dynamic_lookup", *(link or [])]
    return link if link is not None else ["-Wl,-z,lazy"]


def run(cmd: list, log: List[str], cwd: Path) -> subprocess.CompletedProcess:
    cmd = [str(arg) for arg in cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    log.append(f"{' '.join(cmd)}\n{proc.stdout}{proc.stderr}")
    return proc


def build(
    out: Path,
    prefix: str,
    log: List[str],
    include: Optional[List[Path]] = None,
    link: Optional[List[str]] = None,
) -> List[str]:
    """Translate and compile the check of the .pxd and the module 'prefix' in
    'out', and return what failed. The module links 'link'; without 'link', the
    module links no library. Each command and its output is appended to 'log'."""

    cython = [sys.executable, "-m", "cython", "-3"]
    cc = toolchain.CC.command()
    includes = [sysconfig.get_paths()["include"], str(out), *(include or [])]
    flags = [f"-I{path}" for path in includes] + check_cflags(cc)

    proc = run([*cython, f"{prefix}_check.pyx", "-o", "pxd_check.c"], log, out)
    if proc.returncode:
        return [f"Cython failed on the check of the .pxd:\n{proc.stderr}"]
    proc = run([cc, "-fsyntax-only", *flags, "pxd_check.c"], log, out)
    if proc.returncode:
        return [f"compiling the check of the .pxd failed:\n{proc.stderr}"]

    proc = run([*cython, f"{prefix}.pyx", "-o", f"{prefix}.c"], log, out)
    if proc.returncode:
        return [f"Cython failed on the module:\n{proc.stdout}{proc.stderr}"]
    cmd = [cc, "-shared", "-fPIC", *flags, f"{prefix}.c"]
    cmd += [*link_args(link), "-o", f"{prefix}{SUFFIX}"]
    proc = run(cmd, log, out)
    if proc.returncode:
        return [f"compiling the module failed:\n{proc.stderr}"]
    return []


class Cython(Target):
    NAME = "cython"
    TOOLCHAINS = (toolchain.PYTHON, toolchain.CC)
    FORMATTERS = (formatter.BLACK, formatter.CLANG_FORMAT)

    def environment(self) -> Environment:
        env = Environment(
            loader=FileSystemLoader(Path(__file__).parent),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        env.filters.update(
            define_type=define_type,
            define_value=define_value,
            docstring=pygen.docstring,
            ident=pygen.ident,
            oneline=oneline,
            pysafe=pysafe,
            quoted=pygen.quoted,
        )
        return env

    def context(self, model: Model) -> dict:
        prefix = cgen.c_ident(model.meta.prefix)
        namer = pygen.Namer(model)
        pxd = cygen.Pxd(model)
        # pxd.lines() names the types declared outside the headers, and the
        # Renderer reads those names
        declarations = pxd.lines()
        renderer = pyxgen.Renderer(model, pxd, namer)
        rendered = renderer.render()
        entities = model.entities
        functions = [e for e in entities if isinstance(e, decls.Function)]
        defines = [e for e in entities if isinstance(e, decls.Define)]
        enums = [e for e in entities if isinstance(e, decls.Enum)]

        # Where the .pxd declares the name that the ctypes module gives a class,
        # the class is defined under another name and also bound to that name
        aliases = [
            (namer(name), renderer.class_of(name))
            for name in renderer.records
            if namer(name) != renderer.class_of(name)
        ]
        # The name of a typedef of a record or an enum is bound to the class of
        # that record or enum
        for typedef in model.typedefs().values():
            if typedef.name in namer.aliases:
                continue
            typ = namer.resolve(typedef.typ)
            cls = None
            if isinstance(typ, types.Record) and typ.name in renderer.records:
                cls = renderer.class_of(typ.name)
            elif isinstance(typ, types.EnumRef) and typ.name in model.enums():
                cls = namer(typ.name)
            if cls and namer(typedef.name) != cls:
                aliases.append((namer(typedef.name), cls))

        # The names the module defines besides the rendered functions and classes
        names = [pygen.ident(e.name) for e in defines] + [name for name, _ in aliases]
        for enum in enums:
            names.append(namer(enum.name))
            names += [pygen.ident(member.name) for member in enum.members]
        stub = pyigen.Stub(renderer, names).render()

        return {
            "meta": model.meta,
            "module": module_name(model),
            "PREFIX": prefix.upper(),
            "Prefix": pygen.camel(prefix),
            "namer": namer,
            "defines": defines,
            "enums": enums,
            "aliases": aliases,
            "variadic": [f for f in functions if f.variadic],
            "value_key": VALUE_KEY,
            "stdint": cygen.CIMPORTS["libc.stdint"],
            "declarations": declarations,
            "check": cygen.Check(pxd).render(),
            "printable": list(renderer.records.values()),
            "class_of": renderer.class_of,
            "stub": stub,
            **rendered,
        }

    def emit(self, model: Model) -> list:
        env = self.environment()
        context = self.context(model)
        prefix = context["module"]

        paths = []
        for filename, template in [
            (f"{prefix}.pyx", "module.pyx.template"),
            (f"{prefix}.pyi", "module.pyi.template"),
            (f"{prefix}.pxd", "module.pxd.template"),
            (f"{prefix}_check.py", "check.py.template"),
            (f"{prefix}_check.pyx", "check.pyx.template"),
        ]:
            path = self.output / filename
            path.write_text(env.get_template(template).render(**context))
            paths.append(path)

        # The header that the .pxd declares, as the C target emits it
        path = self.output / f"lib{model.meta.prefix}.h"
        path.write_text(header(model))
        paths.append(path)

        return paths

    def check(self, model: Model) -> list:
        """Translate and compile the module and the check of the .pxd, run the
        check program, and return the list of failures"""

        failures = toolchain.missing(list(self.TOOLCHAINS))
        if failures:
            return failures
        if importlib.util.find_spec("Cython") is None:
            return [f"no Cython in {sys.executable}"]

        out = self.output.resolve()
        prefix = module_name(model)
        log: List[str] = []
        try:
            failures = build(out, prefix, log, self.include)
        finally:
            (out / "cython.log").write_text("\n".join(log))
        if failures:
            return failures

        env = {**os.environ, "PYTHONPATH": str(out)}
        for fmt in ("yaml", "json"):
            proc = subprocess.run(
                [sys.executable, str(out / f"{prefix}_check.py"), fmt],
                capture_output=True,
                text=True,
                env=env,
            )
            (out / f"check.{fmt}").write_text(proc.stdout)
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
        return failures
