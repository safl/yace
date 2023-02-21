"""
YAML ==> Interface(List[Entities]) ==> Emitter() ==> CodeTarget
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def camelcase(symbol, pascalcase=True):
    """Format the given 'symbol' as (C|c)amelCase"""

    camelized = "".join(
        [part[0].upper() + part[1:].lower() for part in symbol.split("_")]
    )
    if pascalcase:
        return camelized

    return camelized[0].lower() + camelized[1:]


class Emitter(object):
    """
    The default approach to transforming :class:`.Entity` in :class:`.Model`:
    to source-code-text is inheriting **this** class and utilizing the Jinja
    templates made available in self.templates. It might seem naive to utilize
    templating-engine like Jinja for a code-emitter, however, so far it seems
    to be the an incredibly simple approach.

    This class populates ``self.templates`` with templates loaded for a given
    emitter-implementation. They work as Jinja usually does, a feature-addition
    allowing you to render a Jinja template **within** a Jinja template, via a
    custom-filter-function. For example, like so::

        {{ entity | emit_entity }}

    And available::

        {{ entity | emit_typespec }}

    This works by seperating Jinja templates by filename-convention,
    template-names starting with "entity_{name}.template" are usable by this
    in-template renderer. Thus, for the example above, the template file is
    named ``entity_typedecl``.

    It assumes that 'entity' is an instance of :class:`.Entity` and uses a
    Jinja template to render it. This behavior is added as a means to keep
    **all** text-formating code inside the Jinja-templates, one does not need
    to goto the Python to see a different technique. Thus, **all**::

        Entity ==> SourceCodeText

    Is by default handled in one place: the Jinja templates.
    """

    def __init__(self, searchpath: Path):
        self.searchpath = searchpath.resolve()

    def render(self, template, args):
        """Renders the given template, passing args..."""

        typespec_jenv = Environment(
            loader=FileSystemLoader(self.searchpath),
            extensions=["jinja2.ext.do"],
        )
        typespec_jenv.globals.update(zip=zip, len=len)
        typespec_templates = {
            Path(f).stem.split(".")[0]: typespec_jenv.get_template(f)
            for f in typespec_jenv.list_templates()
            if f.endswith(".template") and f.startswith("typespec")
        }

        def emit_typespec(entity, anon: bool = False):
            args["entity"] = entity
            template = "typespec_anon" if anon else "typespec"

            return typespec_templates[template].render(**args)

        entity_jenv = Environment(
            loader=FileSystemLoader(self.searchpath),
            extensions=["jinja2.ext.do"],
        )
        entity_jenv.globals.update(zip=zip, len=len)
        entity_jenv.filters["camelcase"] = camelcase
        entity_jenv.filters["emit_typespec"] = emit_typespec
        entity_templates = {
            Path(f).stem: entity_jenv.get_template(f)
            for f in entity_jenv.list_templates()
            if f.endswith(".template") and f.startswith("entity_")
        }

        def emit_entity(entity, depth: int = 0):
            args["entity"] = entity
            args["depth"] = depth

            return entity_templates[f"entity_{entity.cls}.h"].render(**args)

        file_jenv = Environment(
            loader=FileSystemLoader(self.searchpath),
            extensions=["jinja2.ext.do"],
        )
        file_jenv.globals.update(zip=zip, len=len)
        file_jenv.filters["camelcase"] = camelcase
        file_jenv.filters["emit_typespec"] = emit_typespec
        file_jenv.filters["emit_entity"] = emit_entity
        file_templates = {
            Path(f).stem: file_jenv.get_template(f)
            for f in file_jenv.list_templates()
            if f.endswith(".template") and not f.startswith("entity_")
        }

        return file_templates[template].render(**args)
