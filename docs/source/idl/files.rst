.. _sec-idl-files:

``yidl`` files
==============

A **yidl** file, is an YAML formated document where some keys in the document
have *special* meaning. This is what one might call an interface definition
language (:idl:`idl <>`). By design this is similar to the module definitions
you find in projects like :swig:`swig <>`.

However, unlike other **IDLs**, then ``yidl`` does not define a new grammer that
you have to learn. Rather it is object-oriented description of the entities
formated in YAML. Each document in the ``yidl`` thus refers to a class described
in :ref:`sec-idl-entities`.

.. _sec-idl-yaml-example:

Example
-------

The key ``meta`` is a *special key* described in greater detail in the
:py:class:`yace.idl.idl.Meta`.

The remainder of a ``yim`` document consists of lists under keys with arbitrary
names. These other top-level keys have no special meaning / signifinance, they
are there to serve as a means to organize the document. Conceptually,
seciton-headers for the YAML-document.

.. literalinclude:: ../../../models/example.yaml
   :language: yaml
   :lines: 1-

.. _idl-yaml-entities:

Entities
--------

At the top-level only ``meta`` is a *special key*, however, in the documents
representing interface/language symbols there are several **special keys**. The
primary one is ``cls`` which defines the specific entity the document idls.

``cls``, all entities have this key, it is the string identifier of the
**class** in the :ref:`sec-idl-entities`.

``dtype``, this is a member of an entity which has a
:py:class:`yace.idl.datatypes.Datatype` member. It can be a string in
shorthand-form with the ``cls`` identifier of the datatype. For example:
``dtype: u32`` or in the full form: ``dtype: {cls: u32, pointer: 1}``. The full
explicit form is intended for adding attributes such as pointer, const, array.

``lit``, this is a special literal-key. For those entities which have it, then
it can be provided in implicit short-form: ``lit: 10`` or the explicit
expansion ``lit: {cls: dec, val: 10}``. The explicit long-form is useful for
expressing literals which are not trivially represented such as ``lit: {cls:
hex, val: 10}``.

The following sections will cover the different entities.
