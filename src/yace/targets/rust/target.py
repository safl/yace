"""
The Rust target: a crate binding the API, in the manner of a ``-sys`` crate,
with pretty-printers for every struct and union, and a check of what it
generated

Emits, into ``<output>/rust``:

* ``Cargo.toml`` and ``build.rs``, the crate, linking the library
* ``lib.rs``, the bindings
* ``check.rs``, the check program, an example of the crate

Functions, constants and enum members keep their C names, so the documentation
of the C API applies; types become CamelCase, as Rust names types:
``struct foo_point`` is ``FooPoint``.
"""

import json
import os
import subprocess
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yace import toolchain
from yace.ir import decls
from yace.ir.model import Model, host_abi
from yace.targets.capi import cgen
from yace.targets.idiom import Idioms
from yace.targets.target import Target

from . import idiomatic, rgen


def rustdoc(doc) -> str:
    """'doc' as a Rust doc comment, on lines of its own, or nothing"""

    lines = rgen.doc_lines(doc)
    if not lines:
        return ""
    return "\n" + "\n".join(f"/// {line}".rstrip() for line in lines)


def oneline(text: str) -> str:
    return " ".join(text.split())


def toml_str(text: str) -> str:
    return json.dumps(oneline(text))


class Rust(Target):
    NAME = "rust"
    TOOLCHAINS = (toolchain.CARGO,)

    def environment(self) -> Environment:
        env = Environment(
            loader=FileSystemLoader(Path(__file__).parent),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        env.filters.update(
            define_type=rgen.define_type,
            define_value=rgen.define_value,
            ident=rgen.ident,
            is_union=lambda record: isinstance(record, decls.Union),
            oneline=oneline,
            rustdoc=rustdoc,
            rustdoc_lines=rgen.doc_lines,
            toml_str=toml_str,
        )
        return env

    def context(self, model: Model) -> dict:
        prefix = cgen.c_ident(model.meta.prefix)
        namer = rgen.Namer(model)
        entities = model.entities
        records = [e for e in entities if isinstance(e, decls.RECORDS)]
        functions = [e for e in entities if isinstance(e, decls.Function)]
        typedefs = [
            e
            for e in entities
            if isinstance(e, decls.Typedef) and e.name not in namer.aliases
        ]
        blobs = [
            r for r in records if r.size and any(f.bits is not None for f in r.fields)
        ]
        printable = [
            r for r in cgen.ordered_records(model) if r.fields and r not in blobs
        ]

        # Resolve every type now, so the stubs of those the IR does not define
        # are known before the crate is laid out
        for entity in typedefs:
            namer.rtype(entity.typ)
        for record in printable:
            for field in record.fields:
                namer.rtype(field.typ)
        for function in functions:
            namer.rtype(function.ret)
            for param in function.params:
                namer.rtype(param.typ, True)

        printer = rgen.Printer(model, namer)
        printer.records = {r.name: r for r in printable}

        library = model.meta.name or prefix
        if library.startswith("lib"):
            library = library[3:]

        return {
            "meta": model.meta,
            "crate": prefix,
            "PREFIX": prefix.upper(),
            "library": library,
            "namer": namer,
            "printer": printer,
            "defines": [e for e in entities if isinstance(e, decls.Define)],
            "enums": [e for e in entities if isinstance(e, decls.Enum)],
            "records": records,
            "blobs": blobs,
            "printable": printable,
            "complete": cgen.ordered_records(model),
            "typedefs": typedefs,
            "stubs": sorted(namer.stubs.items()),
            "functions": functions,
            "params": lambda f: [
                rgen.ident(p.name) if p.name else f"arg{i}"
                for i, p in enumerate(f.params)
            ],
            "layout": model.meta.abi == host_abi(),
            "accessors": lambda record: rgen.accessors(record, namer),
            "debug": lambda record: rgen.debug(record, namer, record in blobs),
            "idiomatic": idiomatic.Renderer(Idioms(model), namer).render(),
        }

    def emit(self, model: Model) -> list:
        env = self.environment()
        context = self.context(model)

        paths = []
        for filename, template in [
            ("Cargo.toml", "Cargo.toml.template"),
            ("build.rs", "build.rs.template"),
            ("lib.rs", "lib.rs.template"),
            ("check.rs", "check.rs.template"),
        ]:
            path = self.output / filename
            path.write_text(env.get_template(template).render(**context))
            paths.append(path)

        return paths

    def check(self, model: Model) -> list:
        """Build and run the check program; returns what failed, if anything"""

        failures = toolchain.missing(self.TOOLCHAINS)
        if failures:
            return failures
        cargo = toolchain.CARGO.command()

        prefix = cgen.c_ident(model.meta.prefix).upper()
        env = {**os.environ, f"{prefix}_NO_LINK": "1"}
        cmd = [cargo, "build", "--quiet", "--offline", "--example", "check"]
        proc = subprocess.run(
            cmd, cwd=self.output, capture_output=True, text=True, env=env
        )
        (self.output / "cargo.log").write_text(
            f"{' '.join(cmd)}\n{proc.stdout}{proc.stderr}"
        )
        if proc.returncode:
            return [f"building the check failed:\n{proc.stderr}"]

        binary = self.output / "target" / "debug" / "examples" / "check"
        failures = []
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
