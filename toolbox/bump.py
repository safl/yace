#!/usr/bin/env python3

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import re
from pathlib import Path

REGEX = (
    r"^.*(version|release).*=.*"
    r'"(?P<version>(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d).*)".*$'
)

PATHS = [
    Path.cwd() / "src" / "yace" / "__init__.py",
]


def main():
    """Main entry-point"""

    for path in PATHS:
        with path.open("r") as file:
            lines = [line.rstrip() for line in file]

        with path.open("w") as file:
            for line in lines:
                match = re.match(REGEX, line)
                if match:
                    version = ".".join(
                        [
                            match.group("major"),
                            match.group("minor"),
                            str(int(match.group("patch")) + 1),
                        ]
                    )
                    line = line.replace(match.group("version"), version)
                    print(f"path: {path}; bumped to: {version}")
                file.write(line + "\n")


if __name__ == "__main__":
    main()
