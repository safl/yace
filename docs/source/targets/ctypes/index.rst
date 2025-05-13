.. _sec-targets-ctypes:

ctypes
======

The :class:`.Ctypes` target emits a pure-Python API using the builtin
:ctypes:`Python/ctypes <>` module.

What is produced:

* :ref:`sec-targets-ctypes-sugar` for :ctypes:`Python/ctypes <>` (``ctypes_sugar.py``)

  * This is an expansion of the :ctypes:`Python/ctypes <>` module

* Utility (``util.py``)

  * Loading libraries using the :ctypes:`Python/ctypes <>` module
  * Architecture check, which ensures that the target architecture matches the
    architecture, the bindings were built on.

* Initialisers (``__init__.py`` and ``raw/__init__.py``)

  * Necessary files for initialising the Python module.

* C API Wrappers for each module (``raw/{submodule}.py``)

  * Python module mapping the :ref:`sec-ir` to :class:`yace.target.ctypes`
  * Entities are grouped in submodules by extracting the module name from the entity name.
    It is assumed that entity names follow the format ``{meta.prefix}_{module}_{name}``.
  * :ref:`sec-ir-constants` become global variables in the ``{prefix}`` module,
    such as ``{prefix}.MIN_X``.
  * :ref:`Enum types<sec-ir-enumtypes>` mapped to :class:`yace.targets.ctypes.ctypes_sugar.Enum`
  * :ref:`Struct types<sec-ir-structtypes>` mapped to :class:`yace.targets.ctypes.ctypes_sugar.Structure`
  * :ref:`Union types<sec-ir-uniontypes>` mapped to :class:`yace.targets.ctypes.ctypes_sugar.Union`

* Test (``{meta.prefix}_check.py``)

  * Imports and does basic library/loader verification of the C API Wrapper

Thus, the above files are what you should expect to see in the output-directory

System-Tools
------------

The target uses the following system-tools to format the emitted code and
verify it:

* :class:`yace.tools.Black`
* :class:`yace.tools.Isort`
* :class:`yace.tools.Python3`

.. _sec-targets-ctypes-implementation:

Implementation
--------------

.. automodule:: yace.targets.ctypes.target
   :inherited-members:
   :members:
   :undoc-members:

.. _sec-targets-ctypes-sugar:

sugar
~~~~~

.. automodule:: yace.targets.ctypes.ctypes_sugar
   :inherited-members:
   :members:
   :undoc-members:
