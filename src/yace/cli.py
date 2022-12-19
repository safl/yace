#!/usr/bin/env python3
import argparse
import logging
from pathlib import Path
from pprint import pprint

import yaml
from jinja2 import Template


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


def emit_code(templates, meta, model, current, parent):
    """
    Recursively emit code for the given 'model', using the given 'templates'
    for the given 'model'
    """

    ltype = current["ltype"]

    # If no parent or parent is "grouping"
    content = []

    # Top-level entities get a comment
    if (not parent and ltype != "grouping") or (
        parent and parent["ltype"] == "grouping"
    ):
        content.append(
            templates["comment"].render(meta=meta, topic=current, parent=parent)
        )

    if ltype in ["grouping"]:
        for member in current["members"]:
            content += emit_code(templates, meta, model, member, current)
    elif ltype in ["struct", "union"]:
        content.append(
            templates[f"{ltype}_enter"].render(meta=meta, topic=current, parent=parent)
        )
        for member in current["members"]:
            content += emit_code(templates, meta, model, member, current)
        content.append(
            templates[f"{ltype}_exit"].render(meta=meta, topic=current, parent=parent)
        )
    else:
        content.append(templates[ltype].render(meta=meta, topic=current, parent=parent))

    return content


def main():
    """Emit enums, structs, and pretty-printer functions for them"""

    args = parse_args()

    logging.basicConfig(level=logging.DEBUG)

    templates = {f.stem: Template(f.open("r").read()) for f in args.templates.iterdir()}

    args.output.mkdir(parents=True, exist_ok=True)

    model = {}
    for path in list(args.model.glob("**/*.yaml")):
        with path.open() as sfd:
            for key, val in yaml.safe_load(sfd).items():
                if key not in model:
                    model[key] = val
                elif key in model and isinstance(val, list):
                    model[key] += val
                else:
                    model[key].update(val)

    meta = {}
    with args.meta.open() as sfd:
        meta.update(yaml.safe_load(sfd))

    logging.info("The loaded model has the following 'topics'")
    for label in model.keys():
        logging.info(f"label({label})")

    files = {"hdr": "libxnvme_spec.h", "src": "xnvme_spec.c"}
    content = {"hdr": [], "src": []}

    for topic in (t for k in model.keys() for t in model[k]):
        content["hdr"].append("\n".join(emit_code(templates, meta, model, topic, None)))

    for ftype, fname in files.items():
        with (args.output / fname).open("w") as hfile:
            hfile.write(
                templates[ftype].render(content="\n".join(content[ftype]), meta=meta)
            )
