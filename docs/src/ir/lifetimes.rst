.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-ir-lifetimes:

Callback lifetimes
==================

A C library calls back into its caller through a function pointer, and gives
the callback a ``void *`` the caller chose, its context. In C the caller owns
both, and keeps the context alive for as long as the library may use it. How
long that is, the header does not say. It is in the documentation, if
anywhere, and the C programmer reads it there.

A binding in another language has to know. There, a callback is a closure: a
Python lambda, a Rust ``FnMut``, a Go func. The binding turns the closure into
a function pointer and a context, and it owns that context on the caller's
behalf. If it frees the context too soon, the library calls into freed memory.
If it never frees it, every callback given leaks. Only the duration the
library uses it is right, and nothing in C says what that is.

**yace** does not guess. The header promises the lifetime of each callback,
with ``@lifetime``, and the bindings keep the closure exactly that long.

The promise
-----------

``@lifetime`` names a callback parameter and how long the library may invoke
it::

  /**
   * Visit the points in the order they were added
   *
   * @param handle The handle
   * @param visit Called for each point, until it returns non-zero
   * @param arg Given to 'visit'
   *
   * @return The number of points visited, -EINVAL when 'visit' is NULL
   *
   * @nullable arg
   * @lifetime visit call
   * @errno
   */
  ssize_t
  foo_point_visit(struct foo_handle *handle, foo_visit_cb visit, void *arg);

A function taking several callbacks names each, as in
``@lifetime first call second once``. The callback must be a ``typedef``'d
function pointer taking one ``void *``, its context, and the function must
take that context as the parameter right after it, see :ref:`sec-ir-csubset`.

**yace** checks that the promise is well formed: that it names a callback,
that the lifetime is one it knows, and that a lifetime tied to a handle is on
a method of one. It cannot check that the promise is true. A wrong one is a
bug in the header, as a wrong ``@param[out]`` or ``@len`` would be, and the
bindings will free a closure the library still calls, or keep one it will
never call.

A callback without a ``@lifetime`` breaks the ``callback-lifetime`` rule, see
:ref:`sec-ir-rules`. It is still bound, but only raw: as the function pointer
and the ``void *``, for the caller to manage as in C.

The lifetimes
-------------

========================  ===============================  ===================
Lifetime                  The library may call it          As, in libfoo
========================  ===============================  ===================
``call``                  during the call only             a visitor
``once``                  once, after the call             a completion
``handle``                any number of times, until the   a watcher
                          handle is destroyed
========================  ===============================  ===================

``call``
  The library calls it only while the call it was given to runs, any number
  of times, and never after that call returns. A visitor, a comparison for a
  sort, a function applied to each element. The binding keeps the closure for
  the call and no longer, and in most languages it need not be boxed or
  copied at all: ``foo_point_visit()`` above.

``once``
  The library calls it at most once, after the call has returned, from a later
  call such as a poll. The completion of a command submitted. The binding
  moves the closure to the heap and frees it when the library has called it.
  A callback the library never calls, as when the handle is closed with the
  command still pending, is never freed: nothing tells the binding it will
  not be called, so freeing it could be a use after free, and it leaks
  instead.

``handle``
  The library may call it any number of times, until the handle the function
  is a method of is destroyed. A handler registered for the life of the
  handle. The binding keeps the closure with the handle, and frees it when it
  destroys the handle::

    /**
     * Watch the points added to the handle, from now until it is closed
     *
     * ...
     * @lifetime added handle
     */
    int
    foo_point_watch(struct foo_handle *handle, foo_added_cb added, void *arg);

When the call fails
-------------------

A callback given to a call that fails is not called, whatever its lifetime: a
call with ``@errno`` that returns a negative errno has not taken it. The
binding frees the closure at once. A handle the call was a method of keeps
what it had.

Which thread
------------

The library calls a callback during a call into the library, on the thread of
that call. A ``call`` callback runs during the call itself. The others run,
when the function is a method, during a later call given the same handle, or
as the handle is destroyed, and when it is not a method, during any later
call.

That is what lets a binding keep a closure that is not safe to share between
threads. A handle in Rust is neither ``Send`` nor ``Sync``, so the calls that
may run its closures are made on the thread that owns it, and those closures
need not be ``Send``. A ``once`` closure given to a function of no handle can
be run by a call from any thread, and in Rust it must be ``Send``.

A library that calls back from a thread of its own, as when a command
completes on a thread the library started, cannot say so yet. Leave such a
callback without a ``@lifetime``, and it is bound raw.

In each target
--------------

What the bindings do with the promise, in brief. Each target's page says more.

C
  The C API declares the callback as the header does. A C caller keeps the
  context alive as the ``@lifetime`` says, as with the header itself.

C++
  Any callable, called through a ``noexcept`` trampoline. One of ``call`` is
  referenced for the call, one of ``once`` moved to the heap, one of
  ``handle`` kept by the handle in a ``std::shared_ptr``.

Python
  Any callable. One the library keeps is held by the module, under a key
  given to C as the context, and dropped when the lifetime ends.

Rust
  ``call`` is a ``&mut dyn FnMut``, ``once`` a ``Box<dyn FnOnce>``, ``handle``
  a ``Box<dyn FnMut>`` the handle keeps. The borrow checker sees
  to it that a ``call`` closure lives as long as the call, and nothing longer
  is asked of it.

Zig
  A context pointer and a comptime function. The caller owns the context, so
  the binding keeps nothing, and the documentation of each function says how
  long the context must live.

Go
  A func, kept in a ``runtime/cgo.Handle`` held in C memory, as cgo lets C
  hold no Go pointer. The handle is deleted and the memory freed when the
  lifetime ends.

Where the handle cannot be destroyed, as when its destructor fails or the
header gives it none, the closures it keeps are kept for good: C may still
call them.

What it cannot say yet
----------------------

``@lifetime`` names a parameter. A callback stored in a field of a record
passed in, such as an options struct, cannot be named, and the function is
bound with the record as is. Nor can a lifetime be tied to a handle the
function creates rather than one it is given, or end when another function is
called. Re-entrancy, a callback calling back into the library, is the
caller's to get right, as in C.
