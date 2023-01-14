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
from pathlib import Path

from yace import __version__ as version
from yace.model.interface import InterfaceModel
from yace.targets.capi.target import CAPI


def parse_args():
    """Parse command-line arguments"""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "model",
        nargs="+",
        type=Path,
        help="Path to Yace Interface Model (yim) file",
    )
    parser.add_argument(
        "--target",
        nargs="+",
        choices=[
            "capi",
            "cpp",
            "ctypes",
            "cython",
            "go",
            "rust",
        ],
        default=["capi"],
        help="Yace Emitter Targets (yets)",
    )
    parser.add_argument(
        "--stage",
        nargs="+",
        default=["lint", "emit", "format", "test"],
        choices=["lint", "emit", "format", "test"],
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
        help="Increase log-level.",
    )

    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Produce model visualization in in output directory",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
    )

    return parser.parse_args()


def main():
    """Emit enums, structs, and pretty-printer functions for them"""

    args = parse_args()

    log.basicConfig(
        format="%(levelname)s:%(module)s:%(funcName)s(): %(message)s",
        level=[log.ERROR, log.INFO, log.WARNING, log.DEBUG][
            sum(args.log_level) if args.log_level else 0
        ],
    )

    args.output.mkdir(parents=True, exist_ok=True)

    for model in [InterfaceModel.from_path(path) for path in args.model]:
        target = CAPI(model, args.output)

        if "lint" in args.stage:
            target.lint()
        if "emit" in args.stage:
            target.emit()

        if "format" in args.stage:
            target.format()
        if "check" in args.stage:
            target.check()
