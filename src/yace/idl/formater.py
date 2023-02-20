#!/usr/bin/env python3
"""
This module provides helpers to format a **Yace**-file, that is, a
``.yaml``-file with Yace Interface Definition entities. A formater provides a
tool-based approach to maintain a canonical format for **Yace**-files.

Since there is a lot of flexibility in **.yaml**-files, a canonical format makes it
easier to read what others have written. Here is what the canonical format
entails:

* The document starts with ``---``

* The ``meta``-key is the first key in the document

  * Raionale: when reading a **Yace**-file, the meta-data should provide the
    introduction to the **Yace**-file, and thus be the first thing int the document

* Top-level keys has an empty line above it

  * Rationale: the top-level keys in **Yace**-file have no significance except
    for the 'meta' key, the intent of all other keys is to provide a "header" /
    "topic" for the list of entities 

* Entity-keys are sorted by an explicit :class:`yace.idl.formater.ORDER`:

  * Rationale: this is done for consistency, always provide a well-known
    ordering, makes it easier to read **Yace**-file files written by others
  * See the :class:`.ORDER` for the explicit ordering used

* Print "flattened", when there are no nested nested structures

  * Rationale: this is typically function-arguments or field-members, as such,
    one would usually read these in a flattened form

Example::

  foo: {cls: dec, sym: min_x, val: 128, doc: Foo Bar Baz}

* Prints block, entities in a block they contain nested values

Example::

  foo:
    cls: dec
    sym: min_x
    val: 128
    doc: Foo Bar Baz

Ideally, then the ``yaml.dump()``, could be parametetrized, or some other
tool/api could do the above. However, I have not found anything which could.

Thus this module. In case somebody reads this, and knows of a simpler approach
achieving the above, please to send a PR.
"""
from pathlib import Path
import typing
import string
import yaml
import os
import logging as log

ORDER = [
    "meta",
    "cls",
    "sym",
    "typ",
    "val",
    "width",
    "width_fixed",
    "fmt",
    "doc",
    "project",
    "version",
    "brief",
    "full",
    "prefix",
    "author",
    "lic",
]


def reorder(data, order):
    """Manipulate the given 'data' adjusting key-order according to 'order'"""

    new = dict()
    for key in (key for key in order if key in data):
        new[key] = data[key]
        del data[key]
    for key in list(data.keys()):
        new[key] = data[key]
        del data[key]

    new.update(data)
    data.update(new)


def ydata_from_file(path: Path) -> dict:
    """Returns a yaml-file in without any transformation"""

    with path.open() as yfile:
        return yaml.safe_load(yfile)


def hascontainer(items):
    """Checks whether a dict or list is in the given list of items"""

    for item in items:
        if isinstance(item, (dict, list)):
            return True

    return False


def yfmt(data, depth):
    """Format the given data"""

    content = ""

    if data is None:
        return "null"

    elif isinstance(data, bool):
        return f"{data}".lower()

    elif isinstance(data, (bool, int, float)):
        return f"{data}"

    elif isinstance(data, str):
        """Render a string..."""

        # TODO: add support for
        # * multi-line strings
        # * Auto-detect whether ' or " should be used

        if not data:
            return "''"

        quote = ""
        if list(set(data) - set(string.ascii_letters + string.digits + "._- ")):
            quote = "'"

        return f"{quote}{data}{quote}"

    elif isinstance(data, dict):
        if depth:
            reorder(data, ORDER)

        # Flat / single-line
        if not hascontainer(list(data.values())):
            inner = ", ".join([f"{key}: " + yfmt(val, 0) for key, val in data.items()])
            return "{" + f"{inner}" + "}"

        # Block / multi-line
        lines = []
        for index, (key, val) in enumerate(data.items()):
            prefix = " " * int(depth // 2) * 2 if index else ""
            lines.append(f"{prefix}{key}: " + yfmt(val, depth + 1))

        linesep = "\n" if depth else "\n\n"
        content += linesep.join(lines)

    elif isinstance(data, list):
        lines = []
        for val in data:
            prefix = " " * int(depth // 2) * 2 + "- "
            lines.append(prefix + yfmt(val, depth + 1))

        content += "\n" + "\n".join(lines)

    else:
        print("[[[%s]]]", data)
        content += str(data)

    return content


def ydata_to_file(ydata: dict, path: Path):
    """Dump Yace-data to file"""

    with path.open("w") as file:
        file.write("---\n")

        meta = ydata.pop("meta", None)  # To ensure "meta" is the first key
        if meta:
            reorder(meta, ORDER)
            file.write(
                yaml.safe_dump(
                    {"meta": meta}, default_flow_style=False, sort_keys=False
                )
            )
            file.write("\n")

        file.write("\n".join([line.rstrip() for line in yfmt(ydata, 0).splitlines()]))
        file.write("\n")


def do_format(paths: typing.List[Path]):
    """Format a list of paths in-place"""

    for path in paths:
        path_backup = path.resolve().with_name(f"{path.name}.bck")
        ydata = ydata_from_file(path)
        ydata_to_file(ydata, path_backup)

        # Open and compare
        old = ydata_from_file(path)
        new = ydata_from_file(path_backup)
        if old != new:
            log.error(f"Content altered, aborting. See({path}, {path_backup})")
            return 1

        os.replace(path_backup, path)

    return 0
