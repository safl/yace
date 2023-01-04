.. _model-yaml:

YAML
====

A **yace** Interface Model (``yim``) file, is a plain text document formated in
YAML. The document is layed out as:

.. literalinclude:: 000_layout.yaml
   :language: yaml
   :lines: 1-

The key ``meta`` is a *special key* described in greater detail in the
:py:class:`yace.model.interface.Meta`.

The remainder of a ``yim`` document consists of lists under keys with arbitrary
names. These other top-level keys have no special meaning / signifinance, they
are there to serve as a means to organize the document. Conceptually,
seciton-headers for the YAML-document.

.. _model-yaml-entities:

Entities
--------

At the top-level only ``meta`` is a *special key*, however, in the documents
representing interface/language symbols there are several **special keys**. The
primary one is ``cls`` which defines the specific entity the document models.

``cls``

``dtype``

``val``

Stuff::

  label:
  - {cls: 'foo', ...}

