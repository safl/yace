#!/usr/bin/env python3
import argparse
import logging
from pathlib import Path
from pprint import pprint

import yaml
from jinja2 import Environment, FileSystemLoader


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


def model_from_path(path: Path):
    """
    Returns a dict composed of the merged content of all yaml-files in the
    given 'path'
    """

    model = {}
    for path in list(path.glob("**/*.yaml")):
        with path.open() as sfd:
            for key, val in yaml.safe_load(sfd).items():
                if key not in model:
                    model[key] = val
                elif key in model and isinstance(val, list):
                    model[key] += val
                else:
                    model[key].update(val)

    logging.info("The loaded model has the following 'topics'")
    for label in model.keys():
        logging.info(f"label({label})")

    return model


def emit_code(templates, meta, current, parent):
    """
    Recursively emit code for the given 'current' model entity using the given
    'templates' for the given 'model'
    """

    ltype = current["ltype"]

    content = []

    if not parent:  # Top-level entities get a comment
        content.append(
            templates["comment"].render(meta=meta, topic=current, parent=parent)
        )

    if ltype in ["struct", "union"]:
        content.append(
            templates[f"{ltype}_enter"].render(meta=meta, topic=current, parent=parent)
        )
        for member in current["members"]:
            content += emit_code(templates, meta, member, current)
        content.append(
            templates[f"{ltype}_exit"].render(meta=meta, topic=current, parent=parent)
        )
    else:
        content.append(templates[ltype].render(meta=meta, topic=current, parent=parent))

    return content


def emit_api_def(args, templates, meta, model):
    """Emit header definitions"""

    content = []
    for topic in (t for k in model.keys() for t in model[k]):
        content.append("\n".join(emit_code(templates, meta, topic, None)))

    with (args.output / f"lib{meta['prefix']}.h").open("w") as hfile:
        hfile.write(templates["api_hdr"].render(content="\n".join(content), meta=meta))


def emit_api_pp(args, templates, meta, model):
    """Emit pretty-printer functions"""

    topics = [topic for topic in (t for k in model.keys() for t in model[k])]

    in_and_out = [
        ("api_pp_hdr", f"lib{meta['prefix']}_pp.h"),
        ("api_pp_src", f"{meta['prefix']}_pp.c"),
    ]
    for template_name, fname in in_and_out:
        content = templates[template_name].render(meta=meta, topics=topics)
        with (args.output / fname).open("w") as hfile:
            hfile.write(content)


def dtype_to_ctype(value):
    """Convert dtype to ctype"""

    if "int" in value["dtype"]:
        return f"{value['dtype']}{value['width']}_t"

    return value["dtype"]


def main():
    """Emit enums, structs, and pretty-printer functions for them"""

    args = parse_args()

    logging.basicConfig(level=logging.DEBUG)

    jinja_env = Environment(loader=FileSystemLoader(searchpath=args.templates))
    jinja_env.filters["dtype_to_ctype"] = dtype_to_ctype

    templates = {
        Path(f).stem: jinja_env.get_template(f) for f in jinja_env.list_templates()
    }

    args.output.mkdir(parents=True, exist_ok=True)

    meta = {}
    with args.meta.open() as sfd:
        meta.update(yaml.safe_load(sfd))

    model = model_from_path(args.model)

    emit_api_def(args, templates, meta, model)

    emit_api_pp(args, templates, meta, model)
