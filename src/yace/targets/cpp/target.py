"""
The C++ target: the idiomatic C++ layer of the API, over the C API, which is
its raw layer, as C++ includes C headers

Emits, into ``<output>/cpp``:

* ``<prefix>.hpp``, the layer, header-only
* ``<prefix>_check.cpp``, the check program

and the C API into ``<output>/capi``, as the C target does, which the layer
includes; its printers are its own, printing what the C API's print.
"""

import json
import subprocess
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from yace import toolchain
from yace.ir.model import Model, host_abi
from yace.targets.capi import cgen
from yace.targets.capi.target import CAPI, comment
from yace.targets.target import Target

from . import cppgen

CXXFLAGS = ["-std=c++20", "-pedantic-errors", "-Wall", "-Wextra", "-Werror"]


class CPP(Target):
    NAME = "cpp"
    TOOLCHAINS = (toolchain.CXX,)

    def __init__(self, output: Path, include=None):
        super().__init__(output, include)
        self.capi = CAPI(output, include)

    def emit(self, model: Model) -> list:
        paths = self.capi.emit(model)

        env = Environment(
            loader=FileSystemLoader(Path(__file__).parent),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        env.filters.update(comment=comment, tag=cgen.tag)
        renderer = cppgen.Renderer(model)
        prefix = cgen.c_ident(model.meta.prefix)
        context = {
            "meta": model.meta,
            "ns": renderer.ns,
            "guard": f"{prefix.upper()}_HPP",
            "body": renderer.render(),
            "operators": "\n".join(renderer.operators()),
            "complete": cgen.ordered_records(model),
            "layout": model.meta.abi == host_abi(),
        }
        for filename, template in [
            (f"{prefix}.hpp", "header.hpp.template"),
            (f"{prefix}_check.cpp", "check.cpp.template"),
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
        cxx = toolchain.CXX.command()

        prefix = cgen.c_ident(model.meta.prefix)
        includes = ["-I", str(self.capi.output), "-I", str(self.output)]
        includes += [f"-I{path}" for path in self.include]
        binary = self.output / f"{prefix}_check"
        cmd = [cxx, *CXXFLAGS, *includes, str(self.output / f"{prefix}_check.cpp")]
        cmd += ["-o", str(binary)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        (self.output / "cc.log").write_text(
            f"{' '.join(cmd)}\n{proc.stdout}{proc.stderr}"
        )
        if proc.returncode:
            return [f"compiling the check failed:\n{proc.stderr}"]

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
                failures.append(f"the printers print invalid {fmt}: {exc}")

        return failures
