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

    def render(self, template, args, filters):
        """Renders the given template, passing args..."""

        # Emitter jinja-environment, setup here such that the filter-function
        # 'emit_entity' can be utilized in the other jinja-environment
        entity_jenv = Environment(
            loader=FileSystemLoader(self.searchpath),
            extensions=["jinja2.ext.do"],
        )
        entity_jenv.globals.update(zip=zip, len=len)
        entity_jenv.filters["camelcase"] = camelcase
        for name, filter in filters.items():
            entity_jenv.filters[name] = filter

        entity_templates = {
            Path(f).stem: entity_jenv.get_template(f)
            for f in entity_jenv.list_templates()
            if f.endswith(".template") and f.startswith("entity_")
        }

        def emit_entity(entity, depth: int = 0):
            args["entity"] = entity
            args["depth"] = depth

            return entity_templates[f"entity_{entity.key}.h"].render(**args)

        # This is the jinja environment for files, e.g. the one that renders
        # "file_<thing>.jinja"
        file_jenv = Environment(
            loader=FileSystemLoader(self.searchpath),
            extensions=["jinja2.ext.do"],
        )
        file_jenv.globals.update(zip=zip, len=len)
        file_jenv.filters["camelcase"] = camelcase
        file_jenv.filters["emit_entity"] = emit_entity
        for name, filter in filters.items():
            file_jenv.filters[name] = filter

        file_templates = {
            Path(f).stem: file_jenv.get_template(f)
            for f in file_jenv.list_templates()
            if f.endswith(".template") and not f.startswith("entity_")
        }

        return file_templates[template].render(**args)
