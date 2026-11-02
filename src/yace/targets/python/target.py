"""
The Python target: a module binding the API through ctypes, with the records
as ctypes structures and unions that print themselves as YAML or JSON, the
enums as IntEnum, and a check of what it generated

Emits, into ``<output>/python``:

* ``<prefix>.py``, the bindings, or ``<prefix>_.py`` where the prefix names a
  module of Python's standard library, such as ``zlib``
* ``<prefix>_check.py``, the check program

C names are kept, so the documentation of the C API applies: functions,
constants and enum members by their C names, as Python's own modules bind C
APIs. Only types are renamed, to CamelCase, as Python names classes:
``struct foo_point`` is ``FooPoint``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yace.ir import decls
from yace.ir.model import Model, host_abi
from yace.targets.capi import cgen
from yace.targets.idiom import Idioms
from yace.targets.target import Target

from . import idiomatic, pygen


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
            "returns": pygen.returns,
            "record_kind": cgen.tag,
            "layout": model.meta.abi == host_abi(),
            "idiomatic": idiomatic.Renderer(Idioms(model), namer).render(),
        }

    def emit(self, model: Model) -> list:
        env = self.environment()
        context = self.context(model)
        prefix = context["module"]

        paths = []
        for filename, template in [
            (f"{prefix}.py", "module.py.template"),
            (f"{prefix}_check.py", "check.py.template"),
        ]:
            path = self.output / filename
            path.write_text(env.get_template(template).render(**context))
            paths.append(path)

        return paths

    def check(self, model: Model) -> list:
        """Run the check program; returns what failed, if anything"""

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

        return failures
