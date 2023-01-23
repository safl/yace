.. _sec-targets-ctypes:

ctypes
======

The :class:`.Ctypes` target emits a pure-Python API using the builtin
:ctypes:`Python/ctypes <>` module.

What is produced:

* :ref:`sec-targets-ctypes-sugar` for :ctypes:`Python/ctypes <>` (``ctypes_sugar.py``)

  * This is an expansion of the :ctypes:`Python/ctypes <>` module

* C API Wrapper (``{meta.prefix}.py``)

  * Python module mapping the :ref:`sec-model` to :class:`yace.target.ctypes`
  * :ref:`sec-model-macros` become global variables in the ``{prefix}`` module,
    such as ``{prefix}.MIN_X``.
  * :ref:`sec-model-enumtypes` mapped to :class:`yace.targets.ctypes.ctypes_sugar.Enum`
  * :ref:`sec-model-structtypes` mapped to :class:`yace.targets.ctypes.ctypes_sugar.Structure`
  * :ref:`sec-model-uniontypes` mapped to :class:`yace.targets.ctypes.ctypes_sugar.Union`

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

Implementation
--------------

.. automodule:: yace.targets.ctypes.target
   :inherited-members:
   :members:
   :undoc-members:

.. _sec-targets-ctypes-sugar:

sugar
-----

.. automodule:: yace.targets.ctypes.ctypes_sugar
   :inherited-members:
   :members:
   :undoc-members:
