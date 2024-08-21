#!/usr/bin/env python3
from jinja2 import BaseLoader, Environment
from yace.model import Model

TEMPLATE = """\
.. _sec-idl-list:

================
 Entity Listing
================

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
        entities.append(
            {
                "key": key,
                "doc": doc.replace(":", ""),
                "mod": ".".join([cls.__module__, cls.__name__]),
            }
        )

    print(template.render(entities=entities))


if __name__ == "__main__":
    main()
