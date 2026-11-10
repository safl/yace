# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The C target: an idiomatic C header for the API, pretty-printers for every
struct, union and enum, and a check program asserting the layout recorded in
the IR and exercising the pretty-printers

Emits, into ``<output>/capi``:

* ``lib<prefix>.h``, the C API
* ``<prefix>_pp.c``, the pretty-printers
* ``<prefix>_check.c``, the check program
"""

import json
import logging as log
import subprocess
import textwrap
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yace import toolchain
from yace.ir import decls
from yace.ir.cparser import STANDARD_HEADERS
from yace.ir.model import Model, host_abi
from yace.targets.target import Target

from . import cgen

# ISO C, strictly; with what glibc declares by default, as the parser saw it
CFLAGS = [
    "-std=c11",
    "-D_DEFAULT_SOURCE",
    "-pedantic-errors",
    "-Wall",
    "-Wextra",
    "-Werror",
]


def comment(text: str) -> str:
    """Make 'text' safe inside a C block comment"""

    return text.replace("/*", "/ *").replace("*/", "* /")


def docblock(doc, indent: str = "") -> str:
    """'doc' as a Doxygen comment, wrapped, or nothing when it is empty"""

    if doc.is_empty():
        return ""

    width = 80 - len(indent.expandtabs()) - 3

    def para(text, prefix=""):
        lines = textwrap.wrap(
            comment(text),
            width,
            initial_indent=prefix,
            subsequent_indent="  " if prefix else "",
        )
        return [f" * {line}" for line in lines] or [f" * {prefix}".rstrip()]

    body = []
    if doc.brief:
        body += para(doc.brief)
    for paragraph in [p for p in doc.description.split("\n\n") if p]:
        body += [" *"] + para(paragraph)
    tags = [
        (
            f"param[{doc.directions[name]}]" if name in doc.directions else "param",
            f"{cgen.param_name(name)} {text}",
        )
        for name, text in doc.params.items()
    ]
    tags += [("return", doc.returns)] if doc.returns else []
    tags += list(doc.tags.items())
    if tags:
        body.append(" *")
    for tag, text in tags:
        body += para(text, f"@{tag} ")

    lines = ["/**"] + body + [" */"]
    return "\n" + "\n".join(f"{indent}{line}".rstrip() for line in lines)


def string_literal(text: str, control: str = "\\{:03o}") -> str:
    """'text' as a string literal of C, and of the languages escaping as C does;
    'control' formats a control character, a byte that is not UTF-8, and a '?'
    followed by another, which C would read as a trigraph"""

    named = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r"}

    def escape(idx: int, ch: str) -> str:
        code = ord(ch)
        if 0xDC80 <= code <= 0xDCFF:
            return control.format(code - 0xDC00)
        if code < 0x20 or code == 0x7F or text[idx : idx + 2] == "??":
            return control.format(code)
        return ch

    escaped = (named.get(ch) or escape(idx, ch) for idx, ch in enumerate(text))
    return '"' + "".join(escaped) + '"'


def define_value(value) -> str:
    if isinstance(value, decls.StrLiteral):
        return string_literal(value.value)
    if value.base == 16 and value.value >= 0:
        return hex(value.value)
    return str(value.value)


def header(model: Model) -> str:
    """The C API, lib<prefix>.h, as the C target emits it, for a target that
    includes it in what it emits"""

    template = CAPI.environment().get_template("header.h.template")
    return template.render(**CAPI.context(model))


class CAPI(Target):
    NAME = "capi"
    TOOLCHAINS = (toolchain.CC,)

    @staticmethod
    def environment() -> Environment:
        env = Environment(
            loader=FileSystemLoader(Path(__file__).parent),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        env.filters.update(
            comment=comment,
            decl=cgen.decl,
            docblock=docblock,
            define_value=define_value,
            field_decl=cgen.field_decl,
            signature=cgen.signature,
            pointer_type=cgen.pointer_type,
            tag=cgen.tag,
        )
        return env

    @staticmethod
    def context(model: Model) -> dict:
        prefix = cgen.c_ident(model.meta.prefix).upper()
        entities = model.entities
        printer = cgen.Printer(model)
        records = [e for e in entities if isinstance(e, decls.RECORDS)]
        defaults = {"stdbool.h", "stddef.h", "stdint.h", "stdio.h"}
        return {
            "meta": model.meta,
            "PREFIX": prefix,
            "guard": f"LIB{prefix}_H",
            "includes": [
                f"<{name}>" for name in model.meta.prelude if name not in defaults
            ]
            + [
                f"<{e.name}>" if e.system else f'"{e.name}"'
                for e in entities
                if isinstance(e, decls.Include) and e.name not in defaults
            ],
            "defines": [e for e in entities if isinstance(e, decls.Define)],
            "enums": [e for e in entities if isinstance(e, decls.Enum)],
            "records": records,
            "complete": cgen.ordered_records(model),
            "typedefs": [e for e in entities if isinstance(e, decls.Typedef)],
            "functions": [e for e in entities if isinstance(e, decls.Function)],
            "printer": printer,
            "helpers": printer.helpers(cgen.ordered_records(model)),
            "layout": model.meta.abi == host_abi(),
            "spelled": cgen.spellings(model),
            "standard": list(STANDARD_HEADERS),
        }

    def emit(self, model: Model) -> list:
        env = self.environment()
        context = self.context(model)
        prefix = model.meta.prefix

        files = [
            (f"lib{prefix}.h", "header.h.template"),
            (f"{prefix}_pp.c", "pp.c.template"),
            (f"{prefix}_check.c", "check.c.template"),
            (f"{prefix}_signatures.c", "signatures.c.template"),
        ]
        paths = []
        for filename, template in files:
            path = self.output / filename
            path.write_text(env.get_template(template).render(**context))
            paths.append(path)

        return paths

    def check(self, model: Model) -> list:
        """Build and run the check program; returns what failed, if anything"""

        prefix = model.meta.prefix
        failures = toolchain.missing(self.TOOLCHAINS)
        if failures:
            return failures
        cc = toolchain.CC.command()

        binary = self.output / f"{prefix}_check"
        cmd = [cc, *CFLAGS, "-I", str(self.output)]
        cmd += [f"-I{path}" for path in self.include]
        cmd += [
            str(self.output / f"{prefix}_pp.c"),
            str(self.output / f"{prefix}_check.c"),
        ]
        cmd += ["-o", str(binary)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        (self.output / "cc.log").write_text(
            f"{' '.join(cmd)}\n{proc.stdout}{proc.stderr}"
        )
        if proc.returncode:
            return [f"compiling the check failed:\n{proc.stderr}"]

        failures = self.signatures(model, cc)
        for fmt in ("yaml", "json"):
            proc = subprocess.run([str(binary), fmt], capture_output=True, text=True)
            (self.output / f"check.{fmt}").write_text(proc.stdout)
            if proc.returncode:
                failures.append(f"the check exited {proc.returncode} printing {fmt}")
                continue
            try:
                if fmt == "yaml":
                    list(yaml.safe_load_all(proc.stdout))
                else:
                    [json.loads(line) for line in proc.stdout.splitlines()]
            except (yaml.YAMLError, json.JSONDecodeError) as exc:
                failures.append(f"the pretty-printers print invalid {fmt}: {exc}")

        return failures

    def signatures(self, model: Model, cc: str) -> list:
        """Compile the check of the signatures with the headers the IR was
        parsed from, found in the include directories, so that a function whose
        type in the IR is not the header's fails; where a header is not found,
        it warns that the signatures are not checked, and fails nothing"""

        log_path = self.output / "signatures.log"
        note = self.headers_unchecked(model)
        if note:
            log_path.write_text(f"{note}\n")
            log.warning("capi: %s", note)
            return []

        source = self.output / f"{model.meta.prefix}_signatures.c"
        cmd = [cc, "-std=gnu11", "-fsyntax-only"]
        cmd += [f"-I{path}" for path in self.include] + [str(source)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        log_path.write_text(f"{' '.join(cmd)}\n{proc.stdout}{proc.stderr}")
        if proc.returncode:
            return [f"the signatures disagree with the headers:\n{proc.stderr}"]
        return []
