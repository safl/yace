#!/usr/bin/env python3
import argparse
import logging
from pathlib import Path
from pprint import pprint

import yaml

from yace.emitter import Emitter
from yace.model.interface import InterfaceModel


def parse_args():
    """Parse command-line arguments"""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--meta",
        type=Path,
        default=Path("meta.yaml"),
        help="Path to meta definitions such as namespace prefix",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("model"),
        help="Path to directory containing the data model",
    )
    parser.add_argument(
        "--targets",
        choices=["c", "python"],
        default=["c", "python"],
        help="Targets",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=Path("templates"),
        help="Path directory containing code-emitter-templates",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Path to store emitted code in",
    )

    return parser.parse_args()


def main():
    """Emit enums, structs, and pretty-printer functions for them"""

    args = parse_args()

    logging.basicConfig(level=logging.DEBUG)

    args.output.mkdir(parents=True, exist_ok=True)

    meta = {}
    with args.meta.open() as sfd:
        meta.update(yaml.safe_load(sfd))

    model = InterfaceModel.from_path(args.model)

    emitter = Emitter(model, meta, args.templates, args.output)
    emitter.emit_api_def()
    emitter.emit_api_pp()
    emitter.emit_api_test()
    emitter.emit_docgen()
