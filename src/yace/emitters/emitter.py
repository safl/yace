"""
YAML ==> Interface(List[Entities]) ==> Emitter() ==> CodeTarget
"""
import typing
from pathlib import Path

from jinja2 import Environment, PackageLoader

from yace.model.entities import Entity
from yace.model.interface import InterfaceModel, Meta


def render(entity, template_name):
    """
    Returns the "entity" rendered using the Jinja template named
    "template_name"
    """

    these = ["typedecl", "param"]

    jenv = Environment(loader=PackageLoader("yace", "templates"))
    templates = {
        Path(f).stem: jenv.get_template(f)
        for f in jenv.list_templates()
        if f.endswith(".template") and Path(f).stem in these
    }

    return templates[template_name].render(entity=entity)


class Emitter(object):
    """
    Base class for emitting code from :class:`yace.model.InterfaceModel` in
    :class:`.Emitter.emit()`, formats the code using :class:`.Emitter.format()`
    and checks via :class:`.Emitter.check()`.
    """

    def __init__(
        self,
        model: InterfaceModel,
        output: Path,
    ):
        jenv = Environment(loader=PackageLoader("yace", "templates"))
        jenv.filters["render"] = render

        self.templates = {
            Path(f).stem: jenv.get_template(f)
            for f in jenv.list_templates()
            if f.endswith(".template")
        }
        self.model = model
        self.meta = model.meta
        self.output = output

        self.func = lambda cls, parent, depth: print(f"%s{cls}" % ("\t" * depth))

    def traverse(
        self, current: Entity, parent: typing.Optional[Entity], depth: int = 0
    ) -> str:
        """
        Recursive walk of the 'current' entity
        """

        self.func(current.cls, parent, depth)
        if getattr(current, "members", None):
            for member in getattr(current, "members"):
                self.traverse(member, current, depth + 1)

    def emit(self):
        """Emit code"""

        raise NotImplementedError()

    def format(self):
        """Format emitted code"""

        raise NotImplementedError()

    def check(self):
        """Check the emitted code"""

        raise NotImplementedError()
