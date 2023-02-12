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


def parse_args():
    """Parse command-line arguments"""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "idl",
        nargs="+",
        type=Path,
        help="Path to Yace IDL (yidl) file",
    )
    parser.add_argument(
        "--target",
        nargs="+",
        choices=[target.NAME for target in Compiler.TARGETS],
        default=[target.NAME for target in Compiler.TARGETS][0],
        help="Targets",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Path to output directory, for emitted code / artifacts",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        action="append_const",
        const=1,
        default=[],
        help="Increase log-level.",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="Parse and check the given idl-files, then exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
    )

    return parser.parse_args()


def main():
    """Emit enums, structs, and pretty-printer functions for them"""

    ok = False
    try:
        args = parse_args()

        levels = [log.ERROR, log.INFO, log.DEBUG]
        log.basicConfig(
            format="%(levelname)s:%(module)s:%(funcName)s(): %(message)s",
            level=levels[min(sum(args.log_level), len(levels) - 1)],
        )

        yace = Compiler(args.target, args.output)
        ok = all(
            [
                yace.process(path, ["parse", "lint"] if args.lint else Compiler.STAGES)
                for path in args.idl
            ]
        )
    except Exception as exc:
        log.error("Unhandled Exception: message(%s)", exc)
        log.error("Unhandled Exception: increase log-level (-ll) for trace")
        log.error("Unhandled Exception(%s)", exc, exc_info=True)

    return sys.exit(0 if ok else 1)
