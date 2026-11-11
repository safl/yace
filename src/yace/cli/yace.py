#!/usr/bin/env python3

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The command-line interface of **yace**

Given C headers, parses them as one API into the IR, writing '<prefix>.yaml'
and the diagnostics to '<prefix>.status', and reports every place the headers
step outside the C subset. The prefix is that of the meta, or else the name of
the first header. Given IR files, '.yaml', reads them.
Either way, '--emit' then generates the code of the given targets and checks it.
A generator, '--generate', writes headers that are parsed with the headers given.
With '--toolchains', prints what those checks build with instead.
"""

import argparse
import json
import logging as log
import sys
from pathlib import Path

import yaml

from yace import __version__ as version
from yace import generators as gen
from yace.compiler import process
from yace.ir import model as ir
from yace.ir.cparser import MissingHeader, c_to_yace
from yace.targets.target import load, targets


def parse_args():
    parser = argparse.ArgumentParser(
        description="Describe a C API in a subset of C, and generate its bindings"
    )
    parser.add_argument(
        "filepath",
        nargs="*",
        type=Path,
        help="C headers (.h) to parse, as one API, or IR files (.yaml) to emit code"
        " from",
    )
    parser.add_argument(
        "--emit",
        nargs="+",
        default=[],
        metavar="TARGET",
        help=f"targets to generate code for; installed: {', '.join(sorted(targets()))}",
    )
    parser.add_argument(
        "--generate",
        action="append",
        default=[],
        metavar="GENERATOR",
        help="generator to write headers with, which are then parsed with the"
        " headers given, by its name or as <file.py or module>:<class>; installed: "
        + (", ".join(sorted(gen.generators())) or "none"),
    )
    parser.add_argument(
        "--generator-option",
        action="append",
        default=[],
        metavar="GENERATOR.KEY=VALUE",
        help="an option of a generator",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd(),
        help="directory to write the IR, the status and the generated code to",
    )
    parser.add_argument(
        "--meta",
        type=Path,
        help="YAML file of the IR meta, such as its name, prefix and license",
    )
    parser.add_argument(
        "-I",
        dest="include",
        action="append",
        default=[],
        help="include directory, for parsing headers and building the checks",
    )
    parser.add_argument(
        "--prelude",
        action="append",
        default=[],
        metavar="HEADER",
        help="system header, such as stdio.h, to include ahead of the headers, for"
        " what they use but do not include; what the API uses of it is still"
        " external",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when a header steps outside the C subset",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="emit the code, but do not build and check it",
    )
    parser.add_argument(
        "--schema", action="store_true", help="print the JSON Schema of the IR"
    )
    parser.add_argument(
        "--toolchains",
        action="store_true",
        help="print, as JSON, the toolchains the checks of the '--emit' targets, or"
        " of every target, build with: the command, where it is, and its version",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version}")
    parser.add_argument(
        "--log-level",
        "-l",
        action="count",
        default=0,
        help="increase the log level",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    levels = [log.WARNING, log.INFO, log.DEBUG]
    log.basicConfig(
        format="%(levelname)s: %(message)s",
        level=levels[min(args.log_level, len(levels) - 1)],
    )

    if args.schema:
        print(json.dumps(ir.schema(), indent=2))
        return 0

    unknown = [name for name in args.emit if name not in targets()]
    if unknown:
        log.error("no target %s; installed: %s", unknown, ", ".join(sorted(targets())))
        return 1

    if args.toolchains:
        names = args.emit or sorted(targets())
        found = {name: [tc.find() for tc in load(name).TOOLCHAINS] for name in names}
        print(json.dumps(found, indent=2))
        return 0

    if args.generate:
        try:
            generated = gen.generate(args.generate, args.output, args.generator_option)
        except (KeyError, ValueError) as error:
            log.error("%s", error.args[0])
            return 1
        for path in generated.headers + generated.sources:
            log.info("generated %s", path)
        if any(path.suffix == ".yaml" for path in args.filepath):
            log.error("generated headers are parsed with headers, not IR files")
            return 1
        args.filepath = list(args.filepath) + generated.headers
        args.include = list(args.include) + sorted(
            {str(path.parent) for path in generated.headers}
        )

    if not args.filepath:
        log.error("give C headers (.h) or IR files (.yaml), or a generator")
        return 1

    missing = [str(path) for path in args.filepath if not path.exists()]
    if missing:
        log.error("does not exist: %s", ", ".join(missing))
        return 1

    suffixes = {path.suffix for path in args.filepath}
    if len(suffixes) != 1 or not suffixes <= {".h", ".yaml"}:
        log.error("give either C headers (.h) or IR files (.yaml), not %s", suffixes)
        return 1

    if ".h" in suffixes:
        meta = yaml.safe_load(args.meta.read_text()) if args.meta else None
        args_clang = [f"-I{path}" for path in args.include]
        try:
            model, diagnostics = c_to_yace(
                args.filepath, args.output, meta, args_clang, args.prelude
            )
        except MissingHeader as error:
            log.error("%s", error.args[0])
            return 1
        for diagnostic in diagnostics:
            print(diagnostic, file=sys.stderr)
        log.info("%d entities, %d diagnostics", len(model.entities), len(diagnostics))
        if diagnostics:
            print(
                f"yace: {len(diagnostics)} diagnostics; the headers step outside the"
                f" C subset, see {model.meta.prefix}.status",
                file=sys.stderr,
            )
            if args.strict:
                return 1
        models = [model]
    else:
        models = [ir.load(path) for path in args.filepath]

    # The headers' own directories too, where the check of the signatures finds
    # them when they are given by path
    include = [Path(path) for path in args.include]
    if ".h" in suffixes:
        include += [p.parent for p in args.filepath if p.parent not in include]
    failures = []
    for model in models:
        failures += process(
            model, args.emit, args.output, check=not args.no_check, include=include
        )
    for failure in failures:
        print(f"yace: {failure}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
