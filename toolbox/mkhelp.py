#!/usr/bin/env python3

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""Print the description of every target of a Makefile"""

import argparse
import os
import re
import sys

TEXT_FMT_BOLD = "\033[1m"
TEXT_FMT_END = "\033[0m"
SEP = ";"


def expand_path(path):
    """Expand the variables and the home directory in the path, and make it
    absolute"""

    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))


def setup():
    """Parse command-line arguments"""

    prsr = argparse.ArgumentParser(
        description="Print the description of every target of a Makefile",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    prsr.add_argument(
        "--repos", help="Path to the directory holding the Makefile", required=True
    )
    prsr.add_argument(
        "--verbose",
        action="store_true",
        help="Print every line of each description, not only the first",
        required=False,
    )
    prsr.add_argument(
        "--no-colorize",
        action="store_true",
        default=False,
        help="Print the names of the targets without bold",
        required=False,
    )
    args = prsr.parse_args()
    args.repos = expand_path(args.repos)

    return args


def gen_help(args):
    """Read the description of each target, the lines between 'define
    <target>-help' and 'endef' in the Makefile, into args.help"""

    define_regex = re.compile("define (?P<target>.+)-help")
    endef_regex = re.compile("endef")
    args.help = {}
    key = ""
    desc = []
    with open(os.path.join(args.repos, "Makefile")) as makefile:
        for line in makefile.readlines():
            if define_regex.match(line):
                key = define_regex.match(line).group("target")
            elif endef_regex.match(line):
                args.help[key] = [
                    ln[1:].strip("\n") for ln in desc if ln.startswith("#")
                ]
                key = ""
                desc = []
            elif key:
                desc.append(line)
    return args


def print_help(args):
    """Print the usage and the description of every target"""

    print(
        "\n".join(
            [
                "Usage:",
                " ",
                f"  make help      {SEP} Print the description of every target",
                f"  make [target]  {SEP} Run the given target",
                " ",
                "Targets:",
                " ",
            ]
        )
    )

    width = max(len(k) for k in args.help)

    for key, desc in sorted(args.help.items()):
        short = "".join(
            [key.ljust(width), f" {SEP}{desc[0]}"]
            if args.no_colorize
            else [
                TEXT_FMT_BOLD,
                key.ljust(width),
                TEXT_FMT_END,
                f" {SEP}{desc[0]}",
            ]
        )
        print(short)
        if args.verbose and len(desc) > 1:
            for line in desc[1:]:
                print(line)
            print("")


def main(args):
    try:
        print_help(gen_help(args))
    except FileNotFoundError:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(setup()))
