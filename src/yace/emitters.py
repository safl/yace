"""
YAML ==> Interface(List[Entities]) ==> Emitter() ==> CodeTarget
"""
import typing
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PackageLoader, Template

from yace.model.entities import Entity
from yace.model.interface import InterfaceModel, Meta


class Emitter(object):
    """
    The default approach to transforming :class:`.Entity` in
    :class:`.InterfaceModel: to source-code-text is inheriting **this** class
    and utilizing the Jinja templates made available in self.templates. It
    might seem naive to utilize templating-engine like Jinja for a
    code-emitter, however, so far it seems to be the an incredibly simple
    approach.

    This class populates ``self.templates`` with templates loaded for a given
    emitter-implementation. They work as Jinja usually does, a feature-addition
    allowing you to render a Jinja template **within** a Jinja template, via a
    custom-filter-function. For example, like so::

        {{ entity | render("typedecl") }}

    This works by seperating Jinja templates by filename-convention,
    template-names starting with "filter_{name}.template" are usable by this
    in-template renderer. Thus, for the example above, the template file is
    named ``filter_typedecl``.

    It assumes that 'entity' is an instance of :class:`.Entity` and uses a
    Jinja template to render it. This behavior is added as a means to keep
    **all** text-formating code inside the Jinja-templates, one does not need
    to goto the Python to see a different technique. Thus, **all**::

        Entity ==> SourceCodeText

    Is by default handled in one place: the Jinja templates.
    """

    def __init__(self, model: InterfaceModel, output: Path, name: str = "base"):
        self.model = model
        self.meta = model.meta
        self.output = output
        self.name = name

        filter_jenv = Environment(
            loader=PackageLoader(f"yace.targets.{self.name}", ".")
        )
        self.filter_templates = {
            Path(f).stem: filter_jenv.get_template(f)
            for f in filter_jenv.list_templates()
            if f.endswith(".template") and f.startswith("filter_")
        }

        jenv = Environment(loader=PackageLoader(f"yace.targets.{self.name}", "."))
        jenv.filters["render"] = lambda entity, template_name: self.filter_templates[
            f"filter_{template_name}"
        ].render(entity=entity)

        self.templates = {
            Path(f).stem: jenv.get_template(f)
            for f in jenv.list_templates()
            if f.endswith(".template") and not f.startswith("filter_")
        }

        self.func = lambda cls, parent, depth: print(f"%s{cls}" % ("\t" * depth))