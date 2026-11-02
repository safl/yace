"""
The Zig target: a module binding the API, in two layers, the raw one declaring
the C API as C has it and the idiomatic one over it, with pretty-printers for
every struct and union, and a check of what it generated

Emits, into ``<output>/zig``:

* ``<prefix>.zig``, the bindings
* ``<prefix>_check.zig``, the check program
* ``<prefix>_compile.zig``, what has all of the module compiled

The module needs Zig 0.16, as Zig's standard library changes between releases
and the printers use its ``std.Io.Writer``, and libc, as the C API does.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yace.ir import decls
from yace.ir.model import Model, host_abi
from yace.targets.capi import cgen
from yace.targets.idiom import Idioms, strip
from yace.targets.target import Target

from . import idiomatic, zgen


def zigdoc(doc) -> str:
    lines = zgen.doc_lines(doc)
    if not lines:
        return ""
    return "\n" + "\n".join(f"/// {line}".rstrip() for line in lines)


class Zig(Target):
    NAME = "zig"

    def context(self, model: Model) -> dict:
        prefix = cgen.c_ident(model.meta.prefix)
        namer = zgen.Namer(model)
        entities = model.entities
        records = [e for e in entities if isinstance(e, decls.RECORDS)]
        typedefs = [
            e
            for e in entities
            if isinstance(e, decls.Typedef) and e.name not in namer.aliases
        ]
        functions = [e for e in entities if isinstance(e, decls.Function)]
        blobs = [
            r for r in records if r.size and any(f.bits is not None for f in r.fields)
        ]
        printable = [
            r for r in cgen.ordered_records(model) if r.fields and r not in blobs
        ]

        # Resolve every type now, so the stubs are known before the layout
        for entity in typedefs:
            namer.ztype(entity.typ)
        for record in records:
            for field in record.fields:
                namer.ztype(field.typ)
        for function in functions:
            namer.ztype(function.ret)
            for param in function.params:
                namer.ztype(param.typ, True)

        renderer = idiomatic.Renderer(Idioms(model), namer)

        def member_name(enum, member):
            name = strip(member.name, enum.name.upper()).lower()
            return zgen.ident(name if not name[:1].isdigit() else member.name.lower())

        def enum_type(enum):
            return zgen.ZIG_TYPES[enum.underlying.name] if enum.underlying else "c_int"

        return {
            "meta": model.meta,
            "prefix": prefix,
            "PREFIX": prefix.upper(),
            "namer": namer,
            "printer": zgen.Printer(namer, {r.name: r for r in printable}),
            "locals": renderer.locals,
            "defines": [e for e in entities if isinstance(e, decls.Define)],
            "enums": [e for e in entities if isinstance(e, decls.Enum)],
            "records": records,
            "blobs": blobs,
            "printable": printable,
            "typedefs": typedefs,
            "functions": functions,
            "stubs": sorted(namer.stubs.items()),
            "params": lambda f: [
                zgen.ident(p.name) if p.name else f"arg{i}"
                for i, p in enumerate(f.params)
            ],
            "member_name": member_name,
            "enum_type": enum_type,
            "layout": model.meta.abi == host_abi(),
            "idiomatic": renderer.render(),
        }

    def emit(self, model: Model) -> list:
        env = Environment(
            loader=FileSystemLoader(Path(__file__).parent),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        env.filters.update(
            define_value=zgen.define_value,
            ident=zgen.ident,
            is_union=lambda record: isinstance(record, decls.Union),
            oneline=lambda text: " ".join(text.split()),
            zigdoc=zigdoc,
        )
        context = self.context(model)
        env.filters["locals"] = context["locals"].rename
        prefix = context["prefix"]

        paths = []
        for filename, template in [
            (f"{prefix}.zig", "module.zig.template"),
            (f"{prefix}_check.zig", "check.zig.template"),
            (f"{prefix}_compile.zig", "compile.zig.template"),
        ]:
            path = self.output / filename
            path.write_text(env.get_template(template).render(**context))
            paths.append(path)

        return paths

    def check(self, model: Model) -> list:
        """Build and run the check program; returns what failed, if anything"""

        zig = os.environ.get("ZIG", "zig")
        if not shutil.which(zig):
            return [f"no Zig toolchain ('{zig}'); set ZIG"]

        prefix = cgen.c_ident(model.meta.prefix)
        out = self.output.resolve()  # zig runs in it, so relative paths would not do
        binary = out / f"{prefix}_check"
        cache = ["--cache-dir", str(out / ".cache")]
        cache += ["--global-cache-dir", str(out / ".cache")]
        log = []
        for cmd in [
            [zig, "build-obj", str(out / f"{prefix}_compile.zig")]
            + ["-fno-emit-bin", *cache],
            [zig, "build-exe", "-lc", str(out / f"{prefix}_check.zig")]
            + [f"-femit-bin={binary}", *cache],
        ]:
            proc = subprocess.run(cmd, cwd=self.output, capture_output=True, text=True)
            log.append(f"{' '.join(cmd)}\n{proc.stdout}{proc.stderr}")
            (self.output / "zig.log").write_text("\n".join(log))
            if proc.returncode:
                return [f"building the check failed:\n{proc.stderr}"]

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
