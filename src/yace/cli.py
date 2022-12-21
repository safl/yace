#!/usr/bin/env python3
import argparse
import logging
from pathlib import Path
from pprint import pprint

import yaml
from jinja2 import Environment, FileSystemLoader

from yace.model.interface import Interface


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


def emit_code(templates, meta, current, parent):
    """
    Recursively emit code for the given 'current' model entity using the given
    'templates' for the given 'model'
    """

    content = []

    # Top-level "container" entities get a comment
    if not parent and current.cls in ["struct", "union", "enum"]:
        content.append(
            templates["comment"].render(meta=meta, entity=current, parent=parent)
        )

    if current.cls in ["struct", "union"]:
        content.append(
            templates[f"{current.cls}_enter"].render(meta=meta, entity=current, parent=parent)
        )
        for member in current.members:
            content += emit_code(templates, meta, member, current)
        content.append(
            templates[f"{current.cls}_exit"].render(meta=meta, entity=current, parent=parent)
        )
    else:
        content.append(templates[current.cls].render(meta=meta, entity=current, parent=parent))

    return content


def emit_api_def(args, templates, meta, model):
    """Emit header definitions"""

    content = []
    for entity in model.entities:
        content.append("\n".join(emit_code(templates, meta, entity, None)))

    with (args.output / f"lib{meta['prefix']}.h").open("w") as hfile:
        hfile.write(templates["api_hdr"].render(content="\n".join(content), meta=meta))


def emit_api_pp(args, templates, meta, model):
    """Emit pretty-printer functions"""

    in_and_out = [
        ("api_pp_hdr", f"lib{meta['prefix']}_pp.h"),
        ("api_pp_src", f"{meta['prefix']}_pp.c"),
    ]
    for template_name, fname in in_and_out:
        content = templates[template_name].render(
            meta=meta,
            entities=model.entities
        )
        with (args.output / fname).open("w") as hfile:
            hfile.write(content)


def emit_api_test(args, templates, meta, model):
    """Emit test-program using definitions and pretty-printers"""

    in_and_out = [
        ("api_test_src", "test.c"),
    ]
    headers = [
        {"filename": "libnvme.h"},
        {"filename": "libnvme_pp.h"},
        {"filename": "libxnvme.h"},
        {"filename": "libxnvme_pp.h"},
    ]
    for template_name, fname in in_and_out:
        content = templates[template_name].render(
            meta=meta, entities=model.entities, headers=headers
        )
        with (args.output / fname).open("w") as hfile:
            hfile.write(content)


def emit_docgen(args, templates, meta, model):
    """Emit test-program using definitions and pretty-printers"""

    headers = [
        {"filename": "libnvme.h"},
        {"filename": "libnvme_pp.h"},
        {"filename": "libxnvme.h"},
        {"filename": "libxnvme_pp.h"},
    ]
    content = templates["doxygen"].render(meta=meta, entities=model.entities, headers=headers)
    with (args.output / "doxy.cfg").open("w") as hfile:
        hfile.write(content)


def dtype_to_ctype(value):
    """Convert dtype to ctype"""

    if "int" in value.dtype:
        return f"{value.dtype}{value.width}_t"

    return value.dtype


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

    model = Interface.from_path(args.model)

    emit_api_def(args, templates, meta, model)

    emit_api_pp(args, templates, meta, model)

    emit_api_test(args, templates, meta, model)

    emit_docgen(args, templates, meta, model)
