"""
These are Yace Interface Definition transformations, transforming the loaded
definitions into a different representation, this is usually done in order to
produce an equivalent model with a representation better suited for emitting
code.

E.g. symbols are snake_case in Yace Files, however, when emitting Rust or Python
code, then it is very useful to have this transformed to CamelCase. By doings
so at the IR-level, then the code-emitters need not concern inself with
UPPERCASE/lowercase/snake_case/camelCase/PascalCase etc. this makes emitters a
lot simpler.

Also, at the IR-level, then coding-conventions such as CamelCase can be
shared by multiple targets.
"""

import logging as log

from yace.emitters import camelcase
from yace.ir.derivedtypes import Struct, Union
from yace.model import ModelWalker


class CStyle(ModelWalker):
    """
    Transform symbols:

    * :class:`yace.ir.constants.Define` -> upper()
    * :class:`yace.ir.constants.EnumValue` -> upper()

    This transformation assumes a valid **Yace**-file according to the linter.
    Thus, the symbols are all lower-snake_case, and transformation not
    described above is not performed.
    """

    def visit(self, current, ancestors, depth):
        """..."""

        if "sym" not in list(current.model_dump().keys()):
            return (True, None)

        if current.key in ["define"]:
            current.sym = current.sym.upper()
        elif current.key in ["enum_value"]:
            current.sym = current.sym.upper()

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
        if "sym" not in list(current.model_dump().keys()):
            return (True, None)

        if current.key in ["define"]:
            current.sym = current.sym.upper()
        elif current.key in ["enum", "struct", "union"]:
            current.sym = "_".join([current.sym, current.key])
            current.sym = camelcase(current.sym)
        elif current.key in ["enum_value"]:
            current.sym = current.sym.upper()

        return (True, None)


class Modulizer(ModelWalker):
    """
    Add module to entities when applicable.

    Module names are extracted from from entity.sym, assuming syms 
    to be of format <prefix>_<module>_<entity_name>.
    """

    def visit(self, current, ancestors, depth):
        if "sym" not in list(current.model_dump().keys()):
            return (True, None)

        if not current.sym:
            return (True, None)
        
        prefix = self.model.meta.prefix

        has_prefix = current.sym.lower().startswith(prefix + "_")
        part_of_module = not ("tspec" in current.key or current.key in ["parameter_decl", "field_decl"])
        if part_of_module and not has_prefix:
            log.error(f"Entity does not begin with model prefix({prefix}): {current.sym}.")
            return (False, None)
        
        if has_prefix:
            prefix, module, *_ = current.sym.split("_")
            
            current.module = module.lower()
            ancestor_modules = [a.module for a in ancestors if a.module]

            if not part_of_module and current.module != ancestor_modules[-1]:
                current.sym = f'{prefix}.raw.{module}.{current.sym}'

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
