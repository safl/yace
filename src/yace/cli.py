#!/usr/bin/env python3
import argparse
import logging
from pathlib import Path
from pprint import pprint

import yaml

from yace import __version__ as version
from yace.emitter import Emitter
from yace.model.interface import InterfaceModel


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
        "--targets",
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
        help="Code generator targets",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Path to output directory, for emitted code / artifacts",
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

    logging.basicConfig(level=logging.DEBUG)

    args.output.mkdir(parents=True, exist_ok=True)

    for model in [InterfaceModel.from_path(model) for model in args.model]:
        emitter = Emitter(model, model.meta, args.targets, args.output)
        emitter.emit_api_def()
        emitter.emit_api_pp()
        emitter.emit_api_test()
        emitter.emit_docgen()
