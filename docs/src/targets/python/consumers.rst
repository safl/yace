.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-targets-python-consumers:

Python consumers
================

The Python bindings of a C library are used together with other Python
libraries, and those libraries set requirements on the bindings: how memory
is passed between them without a copy, who frees it, when it may be reused,
and which thread waits for IO. This page surveys the libraries that the
bindings of a storage library such as xNVMe are used with, and lists the
requirements they set. The requirements motivate the design of the
``python`` and ``cython`` targets.

The libraries
-------------

NumPy
  Arrays in host memory. NumPy takes and exports memory through the buffer
  protocol of :pep:`3118`, the `array interface`_, and DLPack
  (``numpy.from_dlpack()``). An array made with ``numpy.frombuffer()``
  shares the memory of the object it is made from and keeps a reference to
  that object as its ``base``.

PyTorch
  Tensors in host or GPU memory. ``torch.frombuffer()`` makes a tensor that
  shares the memory of an object with the buffer protocol, and its behaviour
  is undefined for memory that is not on the CPU (`torch.frombuffer`_).
  ``torch.from_dlpack()`` takes memory on any device. Host memory that a GPU
  copies from asynchronously must be pinned; memory that PyTorch did not
  allocate is pinned with ``torch.cuda.cudart().cudaHostRegister()``
  (`pinned memory`_). The caching allocator of PyTorch reuses the memory of a
  tensor as soon as the tensor is freed.

CuPy
  Arrays in GPU memory, exchanged through the `CUDA array interface`_ and
  DLPack. ``cupy.cuda.UnownedMemory`` takes a pointer, a size and an owner,
  an object that CuPy keeps referenced while it uses the memory. CuPy also
  allocates pinned host memory, ``cupy.cuda.alloc_pinned_memory()``
  (`CuPy memory`_).

PyCUDA
  GPU memory, and page-locked host memory as NumPy arrays:
  ``pycuda.driver.pagelocked_empty()`` allocates one, and
  ``pycuda.driver.register_host_memory()`` page-locks the memory of an
  existing array (`PyCUDA`_).

RAPIDS
  GPU dataframes and arrays: cuDF, cuML and others, which allocate device
  memory through RMM. RMM allocates in stream order, and its
  ``rmm_cupy_allocator`` wraps an ``rmm.DeviceBuffer`` in a CuPy
  ``UnownedMemory`` (`RMM and CuPy`_). The libraries exchange arrays through
  the CUDA array interface.

KvikIO
  The file IO of RAPIDS, through GPUDirect Storage (cuFile) where it is
  available, and through POSIX IO otherwise. ``CuFile.pread()`` and
  ``CuFile.pwrite()`` take a host or device buffer, split the IO into tasks
  run by a pool of threads, and return an ``IOFuture``, whose ``get()``
  waits for the IO and returns the number of bytes (`KvikIO`_). GPUDirect
  Storage is used only for IO aligned to a page.

Triton
  GPU kernels written in Python. A kernel argument that has a ``data_ptr()``
  method and a ``dtype`` attribute is passed to the kernel as a pointer
  (`triton.jit`_).

CuTe DSL
  The Python DSL of CUTLASS for GPU kernels. ``cute.runtime.from_dlpack()``
  makes a tensor of the memory of any DLPack tensor, without a copy. The
  tensor is valid only while the tensor it is made from is alive, and
  ``assumed_align`` must divide its address (`CuTe DSL`_).

ggml
  A C library of tensors for machine learning, the base of llama.cpp. Its
  Python bindings, ``llama-cpp-python`` and ``ggml-python``, are ctypes
  bindings written by hand. The ``gguf`` package of llama.cpp reads a GGUF
  model file through ``numpy.memmap``, and each tensor it reads is a view of
  the mapped file.

vLLM
  LLM inference on PyTorch. A KV connector moves the KV cache of vLLM to and
  from other storage, through methods vLLM calls during the forward pass:
  ``start_load_kv()``, ``wait_for_layer_load()``, ``save_kv_layer()`` and
  ``wait_for_save()``. ``wait_for_save()`` blocks until every save is done,
  so that the paged KV buffer is not overwritten before it is saved (`vLLM KV
  connector`_). The API is marked experimental. vLLM can run a worker
  process for each GPU.

LMCache
  A KV cache layer for vLLM, which stores KV cache in CPU memory, on local
  disk, through GPUDirect Storage, and in remote stores. A storage backend
  implements ``submit_put_task()``, which stores a ``MemoryObj`` and returns a
  future, ``submit_prefetch_task()`` and ``get_blocking()`` (`LMCache
  backend`_). The hot cache of LMCache is a pinned CPU buffer.

Jupyter
  Interactive use. IPython shows an object by its ``_repr_pretty_()``,
  ``_repr_html_()`` or other ``_repr_*_()`` method, and by ``repr()``
  otherwise (`IPython display`_). Help and completion read docstrings and
  signatures.

The requirements
----------------

1. Memory the library allocates, such as a buffer for IO, is an object with
   the buffer protocol, so NumPy, PyTorch, KvikIO and the bindings of other
   libraries use it without a copy. The object frees the memory when it is
   collected, and not while an array made from it is alive.
2. A parameter that C reads or writes as an array of bytes takes any object
   with the buffer protocol, its size in bytes.
3. Memory a GPU reads or writes asynchronously is pinned. Memory the library
   allocates may be pinned already, or be pinned by the caller with
   ``cudaHostRegister()``. A copy that the bindings make is neither, so the
   bindings pass the caller's memory to C, not a copy.
4. GPU memory is exchanged through DLPack and the CUDA array interface, which
   NumPy, PyTorch, CuPy, RAPIDS and the CuTe DSL take; the buffer protocol
   covers host memory only. Both carry a stream, on which the
   consumer synchronizes before using the memory.
5. Memory given to an IO that completes after the call returns is kept alive
   until the IO completes. The caching allocator of PyTorch reuses freed
   memory at once, and vLLM and LMCache wait for saves to complete before the
   memory is reused. KvikIO and LMCache return a future for each IO.
6. Waiting for IO does not hold the GIL, so that the Python threads of vLLM
   and LMCache run meanwhile, and KvikIO waits in threads of its own.
7. A process opens its own devices and queues, as vLLM can run a process
   for each GPU.
8. Sizes and addresses are aligned as the device requires. GPUDirect Storage
   and the CuTe DSL require alignment too.
9. An object shows its value in Jupyter, and every function has a docstring
   and a signature.

The bindings today
------------------

Requirements 1, 2 and 3 are met by both targets. Memory that ``<stem>_alloc``
allocates is a ``Buffer``, and a ``void *`` ``@arrparam`` and a registration
take the memory of the caller's object, not a copy. The ``cython`` module also
takes any buffer for an array of numbers. Requirement 4 is met in one
direction: the bindings take a DLPack tensor and a CUDA array, but a
``Buffer`` gives its memory through the buffer protocol only, as nothing in
the C API says whether the memory is a device's. The bindings ask
``__dlpack__()`` for no stream, so the caller synchronizes before the call.
Requirement 9 is met: records print as YAML, and the functions of both modules
have docstrings and signatures. Under requirement 6, the ``cython`` module
holds the GIL during a call; Cython code that calls C through the ``.pxd`` may
release it.

Requirement 5 is not met. The bindings keep memory that C uses after a call
returns alive only while it is registered. Requirements 7 and 8 are for the
caller and the C library; the bindings do not check them.

.. _array interface: https://numpy.org/doc/stable/reference/arrays.interface.html
.. _torch.frombuffer: https://docs.pytorch.org/docs/main/generated/torch.frombuffer.html
.. _pinned memory: https://docs.pytorch.org/devlogs/eager/2026-08-09-pinned-memory-allocator/
.. _CUDA array interface: https://nvidia.github.io/numba-cuda/user/cuda_array_interface.html
.. _CuPy memory: https://docs.cupy.dev/en/stable/user_guide/memory.html
.. _PyCUDA: https://documen.tician.de/pycuda/driver.html
.. _RMM and CuPy: https://medium.com/rapids-ai/using-rapids-memory-manager-with-cupy-8d08fe8f58fa
.. _KvikIO: https://docs.nvidia.com/kvikio/latest/python/
.. _triton.jit: https://triton-lang.org/main/python-api/generated/triton.jit.html
.. _CuTe DSL: https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/framework_integration.html
.. _vLLM KV connector: https://docs.vllm.ai/api/vllm/distributed/kv_transfer/kv_connector/v1/base.html
.. _LMCache backend: https://docs.lmcache.ai/developer_tutorial/BackendInterface.html
.. _IPython display: https://ipython.readthedocs.io/en/stable/config/integrating.html
