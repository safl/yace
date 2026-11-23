# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The documentation of an entity in the **yace** IR, parsed from the Doxygen-style
comment above the declaration in the header, or trailing it ('///<')
"""

import re
from typing import Dict, List, Literal, Tuple

from pydantic import BaseModel, ConfigDict

TAG = re.compile(r"^[@\\](\w+)(?:\[([^\]]*)\])?\s*(.*)$")

# Tags whose first word is a name
NAMED_TAGS = ("param", "recparam", "arrparam", "tparam", "retval")
PARAM_TAGS = ("param", "recparam", "arrparam")

# Inline commands naming the parameter of a size, length or count: @len_at{n}
REFERENCES = ("nbytes_at", "len_at", "nwritten_at")
REFERENCE = re.compile(r"\s*[@\\](%s)\{([^}]*)\}" % "|".join(REFERENCES))
# A command of REFERENCES, also one without the parameter in braces
MARKER = re.compile(r"[@\\](%s)\b(?:\{([^}]*)\})?" % "|".join(REFERENCES))

# The start of a Doxygen list item, which the description keeps on its own line
LIST_ITEM = re.compile(r"^(?:[-*+]|-#|\d+\.)\s")

Direction = Literal["in", "out", "inout"]

DIRECTIONS: Dict[str, Direction] = {
    "in": "in",
    "out": "out",
    "in,out": "inout",
    "out,in": "inout",
}

# Doxygen's commands naming what is documented; the declaration says that itself
STRUCTURAL_TAGS = ("enum", "struct", "union", "typedef", "fn", "def", "var", "file")

# Doxygen's commands whose text every binding shows, by the label shown with it
PROSE_TAGS = {"note": "Note", "see": "See also", "deprecated": "Deprecated"}


class Doc(BaseModel):
    """
    The documentation of a declaration: the brief; the description, as
    paragraphs separated by a blank line, with each item of a list on a line of
    its own; the text and the direction of each parameter, by name; what is
    returned; and every other tag, by name.

    'stray' holds the ``@nbytes_at``, ``@len_at`` and ``@nwritten_at`` that are
    not in the text of a parameter or name none in braces, 'repeated' those
    given twice for one parameter, and 'twice' the parameters documented by two
    tags, one of them ``@arrparam`` or ``@recparam``.
    """

    model_config = ConfigDict(extra="forbid")

    brief: str = ""
    description: str = ""
    params: Dict[str, str] = {}
    directions: Dict[str, str] = {}
    returns: str = ""
    records: List[str] = []  # the parameters documented with @recparam
    arrays: List[str] = []  # the parameters documented with @arrparam
    references: Dict[str, Dict[str, str]] = {}  # by parameter, by command
    stray: List[str] = []  # as written, such as '@len_at{n}'
    repeated: List[Tuple[str, str]] = []  # (parameter, command)
    twice: List[str] = []
    tags: Dict[str, str] = {}

    def prose(self) -> List[str]:
        """The tags of :data:`PROSE_TAGS` it has, each as its label and text, or
        its label alone, as a bare '@deprecated' says"""

        return [
            f"{label}: {self.tags[tag]}" if self.tags[tag] else label
            for tag, label in PROSE_TAGS.items()
            if tag in self.tags
        ]

    def is_empty(self) -> bool:
        return not (
            self.brief or self.description or self.params or self.returns or self.tags
        )


def strip_markers(raw: str) -> str:
    """The text of a comment, without its markers, such as ``/**`` and ``*/``"""

    text = raw.strip()
    if text.startswith("/*"):
        text = re.sub(r"^/\*+!?<?", "", text)
        text = re.sub(r"\*+/$", "", text)
        lines = [re.sub(r"^\s*\*? ?", "", line) for line in text.splitlines()]
    else:
        lines = [re.sub(r"^\s*//+[!<]*<? ?", "", line) for line in text.splitlines()]

    return "\n".join(line.rstrip() for line in lines).strip()


def joint(tag: str, text: str) -> str:
    """The separator between the texts of a repeated prose 'tag': ', ' for @see, and the
    end of a sentence otherwise. parse() joins yace's own tags by a space, as their text
    is read word by word"""

    if tag == "see":
        return ", "
    return " " if text.endswith((".", "!", "?", ":", ";")) else ". "


def joined(line: str) -> str:
    """What joins 'line' to the text before it: a newline, where it starts an
    item of a list, else a space, as the line continues a sentence"""

    return "\n" if LIST_ITEM.match(line.strip()) else " "


def parse(raw) -> Doc:
    """Parse the raw comment text, as libclang gives it, into a :class:`.Doc`"""

    if not raw:
        return Doc()

    paragraphs: List[str] = []
    tagged: List[List[str]] = []  # [tag, name, text]
    in_tag = False
    directions = {}
    for line in strip_markers(raw).splitlines():
        match = TAG.match(line.strip())
        if match and match.group(1) in REFERENCES:
            # A wrapped line of the tag before, or else a line of a paragraph
            match = None
        if match:
            in_tag = True
            tag, attr, rest = match.group(1), match.group(2), match.group(3)
            if tag == "brief":
                tagged.append(["brief", "", rest])
            elif tag in NAMED_TAGS:
                name, _, text = rest.partition(" ")
                tagged.append([tag, name, text.strip()])
                if tag in PARAM_TAGS and attr is not None:
                    directions[name] = re.sub(r"\s", "", attr)
            else:
                tagged.append([tag, "", rest])
        elif in_tag and line.strip():
            tagged[-1][2] = f"{tagged[-1][2]} {line.strip()}".strip()
        elif in_tag:
            in_tag = False
            if paragraphs and paragraphs[-1]:
                paragraphs.append("")
        elif line.strip():
            if paragraphs and paragraphs[-1]:
                paragraphs[-1] += joined(line) + line.strip()
            else:
                paragraphs.append(line.strip())
        elif paragraphs and paragraphs[-1]:
            paragraphs.append("")

    paragraphs = [para for para in paragraphs if para]

    doc = Doc()
    for tag, name, text in tagged:
        if tag in STRUCTURAL_TAGS:
            continue
        if tag == "brief":
            doc.brief = text
        elif tag in PARAM_TAGS:
            special = tag != "param" or name in doc.records + doc.arrays
            if name in doc.params and special and name not in doc.twice:
                doc.twice.append(name)
            found = dict(doc.references.get(name, {}))
            for marker in MARKER.finditer(text):
                command, named = marker.group(1), marker.group(2)
                if named is None:
                    doc.stray.append(marker.group(0))
                elif command in found:
                    doc.repeated.append((name, command))
                else:
                    found[command] = named.strip()
            if found:
                doc.references[name] = found
            doc.params[name] = REFERENCE.sub("", text).strip()
            if tag == "recparam" and name not in doc.records:
                doc.records.append(name)
            elif tag == "arrparam" and name not in doc.arrays:
                doc.arrays.append(name)
        elif tag in ("return", "returns"):
            doc.returns = text
        elif tag in doc.tags and tag in PROSE_TAGS and doc.tags[tag] and text:
            doc.tags[tag] = f"{doc.tags[tag]}{joint(tag, doc.tags[tag])}{text}"
        elif tag in doc.tags:
            doc.tags[tag] = f"{doc.tags[tag]} {text}".strip()
        else:
            doc.tags[tag] = text if not name else f"{name} {text}".strip()

    doc.directions = directions
    if not doc.brief and paragraphs:
        doc.brief = paragraphs.pop(0)
    doc.description = "\n\n".join(paragraphs)
    for text in [doc.brief, doc.description, doc.returns, *doc.tags.values()]:
        doc.stray += [marker.group(0) for marker in MARKER.finditer(text)]

    return doc
