"""
The entities in the **yace** Interface Definition are enherit the
:class:`.Entity` and mix-in common attributes.

* Base-classes: :class:`.Entity` / :class:`.Typespec`

* Mixin-attributes: :class:`.Named` / :class:`.Documented` / :class:`.Typed`

The above are defined below.
"""

import re
from typing import Dict, Optional

from pydantic import BaseModel, Field


class Docstring(BaseModel):
    """
    An enrichment of a raw-comment-text

    The raw comment-text is parsed into the components of brief, description, and tags.
    """

    brief: str
    description: str
    tags: Dict[str, Dict[str, str]]

    @classmethod
    def from_cursor(cls, cursor):
        data = {"brief": "", "description": "", "tags": {}}

        raw_comment = ""
        if cursor.raw_comment:
            raw_comment = ("".join(list(cursor.raw_comment))).strip()

        if raw_comment.startswith("///<"):
            data["brief"] = raw_comment[4:].strip()
            return cls(**data)

        # Remove comment markers (/**, */, and leading *)
        cleaned_docstring = re.sub(r"\/\*\*|\*\/", "", raw_comment)
        cleaned_docstring = re.sub(
            r"^\s*\*\s?", "", cleaned_docstring, flags=re.MULTILINE
        ).strip()

        # Split into lines
        lines = cleaned_docstring.split("\n")

        # Extract brief description (first non-empty line)
        brief_description = lines[0].strip()
        data["brief"] = brief_description

        # Extract full description (everything after the first line,
        # before any tag like @param/@return
        description_lines = []
        for line in lines[1:]:
            if line.strip().startswith("@"):
                break
            if line.strip():
                description_lines.append(line.strip())

        data["description"] = " ".join(description_lines)

        # Generic tag pattern to match any tag starting with @
        tag_pattern = re.compile(r"@(\w+)\s+(\w+)?\s*(.*?)\n\s*\*", re.DOTALL)
        matches = re.findall(tag_pattern, raw_comment)

        tags = {}
        for tag, param, desc in matches:
            if tag not in tags:
                tags[tag] = {}
            if param:
                tags[tag][param] = desc.strip()
            else:
                tags[tag] = desc.strip()

        data["tags"] = tags

        return data


class Entity(BaseModel):
    """
    A baseclass for all entities in the Yace Interface Definition Language.

    * label; list of labels
    * annotations; User-defined annotations of any kind

    """

    key: str  # The Yace-IR constructor keyword
    ant: Optional[dict] = Field(default_factory=dict)  # User annotations


class Documented(BaseModel):
    """
    Attribute-mixin; adding a required 'doc' describing the :class:`.Entity`
    """

    doc: Docstring


class Named(BaseModel):
    """
    Attribute-mixin; adding a required 'sym' to be used as identifier
    """

    sym: str

    def is_valid_sym(self):
        """Check whether the symbol is a valid C identifier"""

        if self.sym is None:
            return False, f"Invalid attr: sym == None; for {self.as_dict()}"

        match = re.match(r"[_a-z][_a-z0-9]{0,30}", str(self.sym))
        if match:
            return True, "OK"

        return False, f"Invalid attr: '{self.sym}'; for {self.as_dict()}"
