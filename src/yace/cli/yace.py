#!/usr/bin/env python3
"""
The is the command-line interface to **yace**.

TODO
====

* Discover 'adhoc' targets, e.g. targets available in the
  current-workding-directory
* Discover targets via packages under the namespace 'yace.targets.{NAME}`

"""
import argparse
import logging as log
import sys
from pathlib import Path

from yace import __version__ as version
from yace.compiler import Compiler
from yace.ir.cparser import c_to_yace


def parse_args():
    """Parse command-line arguments"""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "filepath",
        nargs="+",
        type=Path,
        help="path to one or more Yace-file(s) or C Header(s)",
    )

    parser.add_argument(
        "--emit",
        nargs="+",
        choices=sorted([target.NAME for target in Compiler.TARGETS]),
        default="capi",
        help="treat filepath(s) as Yace-file, and emit code using target(s), then exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd(),
        help="path to output directory, for emitted code / artifacts",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        action="append_const",
        const=1,
        default=[],
        help="increase log-level.",
    )

    return parser.parse_args()


def main():
    """Emit enums, structs, and pretty-printer functions for them"""

    ok = False
    try:
        args = parse_args()
        args.filepath = [filepath.resolve() for filepath in args.filepath]

        levels = [log.ERROR, log.INFO, log.DEBUG]
        log.basicConfig(
            format="%(levelname)s:%(module)s:%(funcName)s(): %(message)s",
            level=levels[min(sum(args.log_level), len(levels) - 1)],
        )

        suffixes = list(
            set(path.suffix for path in args.filepath if path.suffix in [".h", ".yaml"])
        )
        if len(suffixes) != 1:
            log.error(f"Suffixes({suffixes}); provide either .h or .yaml")
            return sys.exit(1)

        missing = [str(path) for path in args.filepath if not path.exists()]
        if missing:
            log.error(f"Does not exist: {missing}")
            return sys.exit(1)

        if suffixes[0] == ".h":  # C to Yace-file Compiler
            log.info("Got .h will convert to Yace IR")

            errors = c_to_yace(args.filepath, args.output)
            for error in errors:
                log.error(error)

            return sys.exit(1 if errors else 0)

        log.info(f"Got .yaml, will do '{args.emit}'")
        yace = Compiler(args.emit, args.output)
        ok = all([yace.process(path, yace.STAGES) for path in args.filepath])
        return sys.exit(0 if ok else 1)

    except Exception as exc:
        log.error("Unhandled Exception: message(%s)", exc)
        log.error("Unhandled Exception: increase log-level (-ll) for trace")
        log.error("Unhandled Exception(%s)", exc, exc_info=True)

    return sys.exit(1)
