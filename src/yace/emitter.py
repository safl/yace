"""
YAML ==> Interface(List[Entities]) ==> Emitter() ==> CodeTarget
"""
import typing
from pathlib import Path

from jinja2 import Environment, PackageLoader

from .model.entities import Entity
from .model.interface import InterfaceModel, Meta


class Emitter(object):
    """Produces code from :class:`yace.model.InterfaceModel`"""

    def __init__(
        self,
        model: InterfaceModel,
        meta: Meta,
        templates: typing.List[Path],
        output: Path,
    ):
        jenv = Environment(loader=PackageLoader("yace", "templates"))

        self.templates = {
            Path(f).stem: jenv.get_template(f)
            for f in jenv.list_templates()
            if f.endswith(".template")
        }
        self.model = model
        self.meta = meta
        self.output = output

    def emit_code(self, current: Entity, parent: typing.Optional[Entity]) -> str:
        """
        Recursively emit code for the 'current' model entity using the given
        'templates' for the given 'model'
        """

        content = []

        # Top-level "container" entities get a comment
        if not parent and current.cls in ["struct", "union", "enum"]:
            content.append(
                self.templates["comment"].render(
                    meta=self.meta, entity=current, parent=parent
                )
            )

        if current.cls in ["struct", "union"]:
            content.append(
                self.templates[f"{current.cls}_enter"].render(
                    meta=self.meta, entity=current, parent=parent
                )
            )
            for member in current.members:
                content += self.emit_code(member, current)
            content.append(
                self.templates[f"{current.cls}_exit"].render(
                    meta=self.meta, entity=current, parent=parent
                )
            )
        else:
            content.append(
                self.templates[current.cls].render(
                    meta=self.meta, entity=current, parent=parent
                )
            )

        return content

    def emit_api_def(self):
        """Emit header definitions"""

        content = []
        for entity in self.model.entities:
            content.append("\n".join(self.emit_code(entity, None)))

        with (self.output / f"lib{self.meta.prefix}.h").open("w") as hfile:
            hfile.write(
                self.templates["api_hdr"].render(
                    content="\n\n".join(content), meta=self.meta
                )
            )

    def emit_api_pp(self):
        """Emit pretty-printer functions"""

        in_and_out = [
            ("api_pp_hdr", f"lib{self.meta.prefix}_pp.h"),
            ("api_pp_src", f"{self.meta.prefix}_pp.c"),
        ]
        for template_name, fname in in_and_out:
            content = self.templates[template_name].render(
                meta=self.meta, entities=self.model.entities
            )
            with (self.output / fname).open("w") as hfile:
                hfile.write(content)

    def emit_api_test(self):
        """Emit test-program using definitions and pretty-printers"""

        in_and_out = [
            ("api_test_src", "test.c"),
        ]
        headers = [
            {"filename": "libnvme.h"},
            {"filename": "libnvme_pp.h"},
            {"filename": "libxnvme.h"},
            {"filename": "libxnvme_pp.h"},
        ]
        for template_name, fname in in_and_out:
            content = self.templates[template_name].render(
                meta=self.meta, entities=self.model.entities, headers=headers
            )
            with (self.output / fname).open("w") as hfile:
                hfile.write(content)

    def emit_docgen(self):
        """Emit test-program using definitions and pretty-printers"""

        headers = [
            {"filename": "libnvme.h"},
            {"filename": "libnvme_pp.h"},
            {"filename": "libxnvme.h"},
            {"filename": "libxnvme_pp.h"},
        ]
        content = self.templates["doxygen"].render(
            meta=self.meta, entities=self.model.entities, headers=headers
        )
        with (self.output / "doxy.cfg").open("w") as hfile:
            hfile.write(content)
