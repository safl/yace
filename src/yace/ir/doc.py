"""
Documentation attached to an entity in the **yace** IR, parsed from the Doxygen
style comment above, or trailing ('///<'), the declaration in the header
"""

import re
from typing import Dict

from pydantic import BaseModel, ConfigDict

TAG = re.compile(r"^[@\\](\w+)(?:\[([^\]]*)\])?\s*(.*)$")

NAMED_TAGS = ("param", "tparam", "retval")  # tags whose first word is a name

DIRECTIONS = {"in": "in", "out": "out", "in,out": "inout", "out,in": "inout"}

# Doxygen's commands naming what is documented; the declaration says that itself
STRUCTURAL_TAGS = ("enum", "struct", "union", "typedef", "fn", "def", "var", "file")


class Doc(BaseModel):
    """
    The brief, the description after it, the parameters by name, the direction
    of those documented with one, as ``@param[out]``, what is returned, and any
    other tag, by tag name, with its text
    """

    model_config = ConfigDict(extra="forbid")

    brief: str = ""
    description: str = ""
    params: Dict[str, str] = {}
    directions: Dict[str, str] = {}
    returns: str = ""
    tags: Dict[str, str] = {}

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


def parse(raw) -> Doc:
    """Parse the raw comment text, as libclang gives it, into a :class:`.Doc`"""

    if not raw:
        return Doc()

    paragraphs = []  # untagged text, as paragraphs
    tagged = []  # [tag, name, text]
    in_tag = False
    directions = {}
    for line in strip_markers(raw).splitlines():
        match = TAG.match(line.strip())
        if match:
            in_tag = True
            tag, attr, rest = match.group(1), match.group(2), match.group(3)
            if tag == "brief":
                tagged.append(["brief", "", rest])
            elif tag in NAMED_TAGS:
                name, _, text = rest.partition(" ")
                tagged.append([tag, name, text.strip()])
                if tag == "param" and attr is not None:
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
                paragraphs[-1] += " " + line.strip()
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
        elif tag == "param":
            doc.params[name] = text
        elif tag in ("return", "returns"):
            doc.returns = text
        elif tag in doc.tags:
            doc.tags[tag] = f"{doc.tags[tag]} {text}".strip()
        else:
            doc.tags[tag] = text if not name else f"{name} {text}".strip()

    doc.directions = directions
    if not doc.brief and paragraphs:
        doc.brief = paragraphs.pop(0)
    doc.description = "\n\n".join(paragraphs)

    return doc
