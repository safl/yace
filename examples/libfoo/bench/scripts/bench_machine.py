"""
Record the machine the benchmark runs on
========================================

Adds to the facts core.facts_gather records of the target what the benchmark's
numbers also depend on: its CPU, as 'cpu.model', and, as 'toolchains.<name>',
the first line of what each toolchain of the targets in 'bench.targets' says
its version is, and yace's. Fails, naming them, when a toolchain is missing.

Config Arguments
----------------

bench.targets: the targets benchmarked (default: all of them)
bench.<toolchain>: the command of a toolchain, such as bench.cc or bench.python

Retargetable: True
------------------
"""

import errno
import logging as log

import benchlib
from cijoe.core.tools import family

CPU_MODEL = {
    "linux": (
        "sed -n 's/^model name[[:space:]]*: //p' /proc/cpuinfo | head -n 1 | grep ."
        " || lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -n 1"
    ),
    "darwin": "sysctl -n machdep.cpu.brand_string",
    "freebsd": "sysctl -n hw.model",
}


def main(args, cijoe):
    try:
        targets = benchlib.targets(cijoe)
    except ValueError as exc:
        log.error(str(exc))
        return errno.EINVAL

    facts = cijoe.facts.target()
    on = family(cijoe, cijoe.default_target)
    if on in CPU_MODEL:
        err, state = cijoe.run(CPU_MODEL[on])
        model = " ".join(state.output().split())
        if not err and model:
            facts.update("cpu", {"model": model})

    toolchains = {"yace": "--version"}
    for target in targets:
        toolchains.update(benchlib.TARGETS[target]["toolchains"])

    found, missing = {}, []
    for name, version in toolchains.items():
        cmd = f"{benchlib.command(cijoe, name)} {version}"
        err, state = cijoe.run(cmd)
        lines = state.output().strip().splitlines()
        if err or not lines:
            missing.append(f"{name}: '{cmd}' failed")
            continue
        found[name] = lines[0].strip()
    facts.update("toolchains", found)

    if missing:
        log.error("missing toolchains:\n  " + "\n  ".join(missing))
        return errno.ENOENT

    return 0
