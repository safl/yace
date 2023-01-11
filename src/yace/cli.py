#!/usr/bin/env python3
import argparse
import logging
from dataclasses import asdict
from pathlib import Path
from pprint import pprint

import yaml

from yace import __version__ as version
from yace.emitters.capi import CAPI
from yace.model.interface import InterfaceModel, data_from_yaml


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
        "--visualize",
        action="store_true",
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

    for model in [InterfaceModel.from_path(path) for path in args.model]:
        emitter = CAPI(model, args.output)

        if args.visualize:
            print("# Visualize")
            for entity in model.entities:
                emitter.traverse(entity, None)
            continue

        emitter.emit()
        emitter.format()
        emitter.check()
