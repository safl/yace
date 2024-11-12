.. _sec-idl-files:

Storage Format
==============

In **Yace**, the C API and FFI are defined by a **Yace**-file. The content of a
**Yace**-file is described in the following sections. **Yace**-file can be
written manually, or with assistance from other tools, such as the
:ref:`sec-idl-cparser`.

The storage format for the **Yace** Interface Defitinion is in **YAML**. Thus,
no extra tooling for linting and visualizing it, just use regular formaters and
visualization tools such as **jless**. The content is validated when loaded.

The descriptions inside the **Yace**-file consists of meta-data and then
descriptions of symbolic constants, data types, derived types, and function
types. These are referred to as :ref:`sec-idl-entities` and a
:ref:`sec-idl-list` for quick lookup is also available.

Files
=====

A **Yace** Interface Definition File, is an YAML formated document where some
keys in the document have *special* meaning. This is what one might call an
interface definition language (:idl:`idl <>`). By design this is similar to the
module definitions you find in projects like :swig:`swig <>`.

However, unlike other **IDLs**, then **Yace** does not define a new grammer
that you have to learn. Rather it is object-oriented description of the
entities formated in YAML. Each document in a **Yace** file thus refers to a
class described in :ref:`sec-idl-entities`.

.. _sec-idl-files-yaml-example:

Example
-------

The key ``meta`` is a *special key* described in greater detail in the
:py:class:`yace.idl.idl.Meta`.

The remainder of a **yace** file consists of entities, under a key. These
top-level keys have no special meaning / signifinance, they are there to serve
as a means to organize the document. Conceptually, see all the top-level keys
as "section-headers" in the document.

.. literalinclude:: ../../../models/example.yaml
   :language: yaml
   :lines: 1-

.. _sec-idl-files-entities:

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

