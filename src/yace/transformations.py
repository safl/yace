"""
These are Yace Interface Definition transformations, transforming the loaded
definitions into a different representation, this is usually done in order to
produce an equivalent model with a representation better suited for emitting
code.

E.g. symbols are snake_case in Yace Files, however, when emitting Rust or Python
code, then it is very useful to have this transformed to CamelCase. By doings
so at the IDL-level, then the code-emitters need not concern inself with
UPPERCASE/lowercase/snake_case/camelCase/PascalCase etc. this makes emitters a
lot simpler.

Also, at the IDL-level, then coding-conventions such as CamelCase can be
shared by multiple targets.
"""
from yace.emitters import camelcase
from yace.idl.derivedtypes import Struct, Union
from yace.model import ModelWalker


class CStyle(ModelWalker):
    """
    Transform symbols:

    * All ``.sym`` in top-level entities are prefixed with ``meta.prefix_``
    * :class:`yace.idl.constants.Define` -> upper()
    * :class:`yace.idl.constants.EnumValue` -> upper()

    This transformation assumes a valid **Yace**-file according to the linter.
    Thus, the symbols are all lower-snake_case, and transformation not
    described above is not performed.
    """

    def visit(self, current, ancestors, depth):
        """..."""

        if "sym" not in current.all:
            return (True, None)

        if depth == 0:
            current.sym = f"{self.model.meta.prefix}_{current.sym}"
            pass

        if current.cls in ["define"]:
            current.sym = current.sym.upper()
        elif current.cls in ["enum_value"]:
            current.sym = ancestors[-1].sym.upper() + "_" + current.sym.upper()

        return (True, None)


class Camelizer(ModelWalker):
    """
    Transform symbols:

    * Enum -> camelize()
    * EnumValue -> upper()
    * Struct|Enum|Bitfield -> camelize()

    Additionally, then Enum / Struct / Union is added  "postfix" to
    ``entity.sym``. This is done for non-C languages, as enum/struct/union
    C-types rarely has equivalents in "foreign" languages. Rather, these are
    objects with subclasses encapsulating them, e.g. the Python ctypes.

    Thus, the Enum/Struct/Union needs to be added to the identifier, since it
    will otherwise potentially collide with other entities.

    This transformation assumes a valid **Yace**-file according to the linter.
    Thus, the symbols are all lower-snake_case, and transformation not
    described above is not performed.
    """

    def visit(self, current, ancestors, depth):
        if "sym" not in current.all:
            return (True, None)

        if current.cls in ["define"]:
            current.sym = current.sym.upper()
        elif current.cls in ["enum", "struct", "union"]:
            current.sym = "_".join([current.sym, current.cls])
            current.sym = camelcase(current.sym)
        elif current.cls in ["enum_value"]:
            current.sym = current.sym.upper()

        return (True, None)


class HoistAnonMembers(ModelWalker):
    """
    Extract nested entities, that is, struct/union/bitfield which from nested
    to top-level declaration, leaving behind a replace of the entity with a
    field with a typespec matching the extracted entity"""

    def visit(self, current, ancestors, depth):
        if depth != 0:
            return (True, None)

        if type(current) not in [Struct, Union]:
            return (True, None)

        # TODO: top-level struct or union
