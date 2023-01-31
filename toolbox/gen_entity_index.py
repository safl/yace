#!/usr/bin/env python3
from jinja2 import Environment, BaseLoader
from yace.idl.model import Model

TEMPLATE = """
==========
 Appendix
==========

{% for entity in entities %}
* ``{{ entity.cls }}``: :py:class:`{{ entity.mod }}`; {{ entity.doc }}
{% endfor %}
"""

def main():

    template = Environment(loader=BaseLoader()).from_string(TEMPLATE)

    entities = []
    for key, cls in Model.MAPPING.items():
        doc, *tail = [
            x.strip() for x in cls.__dict__.get("__doc__").split("\n") if x.strip()
        ]
        entities.append({
            "cls": key,
            "doc": doc,
            "mod": cls.__dict__["__module__"]
        })

    print(template.render(entities=entities))


if __name__ == "__main__":
    main()
