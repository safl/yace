"""
The entities in the **yace** Interface Definition are enherit the
:class:`.Entity` and mix-in common attributes.

* Base-classes: :class:`.Entity` / :class:`.Typespec`

* Mixin-attributes: :class:`.Named` / :class:`.Documented` / :class:`.Typed`

The above are defined below.
"""

import re
from typing import List, Optional

from pydantic import BaseModel, Field


class Entity(BaseModel):
    """
    A baseclass for all entities in the Yace Interface Definition Language.

    * label; list of labels
    * annotations; User-defined annotations of any kind

    """

    key: str  # The Yace-IDL constructor keyword
    lbl: List[str] = ["nope"]  # Labels
    ant: Optional[dict] = Field(default_factory=dict)  # User annotations


class Documented(BaseModel):
    """
    Attribute-mixin; adding a required 'doc' describing the :class:`.Entity`
    """

    doc: str


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
