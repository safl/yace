# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Build libfoo and generate its bindings
======================================

Makes 'bench.workdir' afresh on the target and copies libfoo there: its header,
source, meta and the benchmark's programs. Builds the library from its source,
with -O2, as a shared library, and has yace generate, from the header, the
bindings of what the targets in 'bench.targets' use, strictly and without the
checks of the targets, which the tests run.

Config Arguments
----------------

bench.workdir: where to build and run (default: 'work' in the run's output)
bench.targets: the targets benchmarked (default: all of them)
bench.cc, bench.yace: the commands of the C compiler and of yace

Retargetable: True
------------------
"""

import errno
import logging as log

import benchlib


def main(args, cijoe):
    try:
        targets = benchlib.targets(cijoe)
    except ValueError as exc:
        log.error(str(exc))
        return errno.EINVAL

    p = benchlib.paths(cijoe)
    for cmd in (f"rm -rf {p['work']}", f"mkdir -p {p['src']}/bench {p['libdir']}"):
        if not benchlib.run(cijoe, cmd):
            return errno.EIO
    for part in ("include", "src", "meta.yaml", "bench/programs"):
        if not cijoe.put(str(benchlib.LIBFOO / part), f"{p['src']}/{part}"):
            log.error(f"failed: copying {part} to {p['src']}")
            return errno.EIO

    cc = benchlib.command(cijoe, "cc")
    cmd = (
        f"{cc} -std=c11 -D_DEFAULT_SOURCE -O2 -shared -fPIC -I include src/foo.c"
        f" -o {p['lib']}"
    )
    if not benchlib.run(cijoe, cmd, p["src"]):
        return errno.EIO

    emit = []
    for target in targets:
        emit += [name for name in benchlib.TARGETS[target]["emit"] if name not in emit]
    yace = benchlib.command(cijoe, "yace")
    cmd = (
        f"{yace} include/foo.h --meta meta.yaml --output {p['gen']}"
        f" --emit {' '.join(emit)} --strict --no-check"
    )
    if not benchlib.run(cijoe, cmd, p["src"]):
        return errno.EIO

    return 0
