# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Build the program of each target
================================

Builds, in 'build/<target>' of 'bench.workdir', the benchmark's program of each
target in 'bench.targets', against the bindings and the library that
bench_prepare made: C with -O2 and C++ with -O2, Rust in release, Zig
ReleaseFast, Go as 'go build' does, and Cython with -O2; Python needs no
building. Fails at the first that does not build.

Config Arguments
----------------

bench.workdir: where to build and run (default: 'work' in the run's output)
bench.targets: the targets benchmarked (default: all of them)
bench.<toolchain>: the command of a toolchain, such as bench.cc or bench.python

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

    build = benchlib.paths(cijoe)["build"]
    for target in targets:
        if not benchlib.run(cijoe, f"mkdir -p {build}/{target}"):
            return errno.EIO
        for cmd, cwd in benchlib.build_commands(cijoe, target):
            if not benchlib.run(cijoe, cmd, cwd):
                log.error(f"target({target}) does not build")
                return errno.EIO

    return 0
