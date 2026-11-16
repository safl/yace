.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-survey:

================================
 C Library Survey
================================

yace includes a survey of popular C libraries, most of them packaged in
Debian. Their headers were not written for yace, so they are expected to step
outside the C subset, and the survey checks two things: that yace parses every
one of them without failing, and which rules of the subset they break, and how
often.

Failing means a traceback, a timeout or an ``internal-error`` diagnostic, and
is a bug in yace. A broken rule is not a bug in yace; it is what a header
written for yace would have to change, and the broken rules show which idioms
are common in practice.

The pipeline
------------

For each header the survey:

1. **Parses** it with ``yace``, which writes the IR and the diagnostics
2. With ``--with-capi``, **generates and checks** the C API from the IR. For a
   header outside the subset the C API may not build, for example when it
   depends on macros of the original header; that is reported, not counted as
   a failure of yace

Running the survey
------------------

The packaged libraries must be installed, with
``toolbox/survey/debian.packages.sh`` on Debian. Then::

    python3 toolbox/survey/survey.py --packaged-only --with-capi

These flags are useful:

``--skip-download``
    Reuse the downloaded headers and cloned repositories.
``--report-only``
    Regenerate the report from the last results.
``--packaged-only``, ``--vendored-only``, ``--repos-only``
    Survey only one source of libraries.

The report, with the diagnostics by rule and each library, is written to
``toolbox/survey/report.md``. The survey exits non-zero when yace failed on a
header.

Surveyed libraries
------------------

The libraries span 13 domains. The table below lists each library, the domain
it belongs to, and whether it is known to have bindings in other languages.

.. list-table::
   :header-rows: 1
   :widths: 24 20 18 18 20

   * - Library
     - Domain
     - Python
     - Rust
     - Go

   * - zlib
     - Compression
     - yes
     - yes (flate2)
     - yes (compress/zlib)
   * - bzip2
     - Compression
     - yes (bz2)
     - yes (bzip2)
     - yes (dsnet/compress)
   * - lz4
     - Compression
     - yes (lz4)
     - yes (lz4)
     - yes (pierrec/lz4)
   * - zstd
     - Compression
     - yes (zstandard)
     - yes (zstd)
     - yes (klauspost/compress)
   * - brotli
     - Compression
     - yes (brotli)
     - yes (brotli)
     - yes (google/brotli)
   * - snappy
     - Compression
     - yes (python-snappy)
     - yes (snap)
     - yes (golang/snappy)
   * - lzo
     - Compression
     - yes (python-lzo)
     -
     -

   * - mbedtls
     - Crypto / TLS
     -
     - yes (mbedtls)
     -
   * - openssl
     - Crypto / TLS
     - yes (pyOpenSSL)
     - yes (openssl)
     - yes (crypto/tls)
   * - gnutls
     - Crypto / TLS
     -
     -
     -
   * - libsodium
     - Crypto / TLS
     - yes (PyNaCl)
     - yes (sodiumoxide)
     - yes (jamesruan/sodium)
   * - nettle
     - Crypto / TLS
     -
     - yes (nettle)
     -
   * - libgcrypt
     - Crypto / TLS
     -
     -
     -

   * - cjson
     - Serialization
     -
     -
     -
   * - jansson
     - Serialization
     -
     - yes (jansson-sys)
     -
   * - protobuf_c
     - Serialization
     - yes (protobuf)
     - yes (prost)
     - yes (protobuf)
   * - msgpack
     - Serialization
     - yes (msgpack)
     - yes (rmp)
     - yes (msgpack-go)
   * - yaml
     - Serialization
     - yes (PyYAML)
     - yes (yaml-rust)
     - yes (go-yaml)
   * - expat
     - Serialization
     - yes (xml.parsers.expat)
     -
     - yes (encoding/xml)
   * - libxml2
     - Serialization
     - yes (lxml)
     - yes (libxml)
     -

   * - mosquitto
     - Networking / IO
     - yes (paho-mqtt)
     - yes (rumqttc)
     - yes (paho.mqtt.golang)
   * - nanomsg
     - Networking / IO
     - yes (nanomsg)
     - yes (nanomsg)
     - yes (go-nanomsg)
   * - nng
     - Networking / IO
     - yes (pynng)
     - yes (nng-rs)
     - yes (go-nng)
   * - event2
     - Networking / IO
     -
     -
     -
   * - uv
     - Networking / IO
     - yes (pyuv)
     - yes (uv)
     -
   * - curl
     - Networking / IO
     - yes (pycurl)
     - yes (curl-rust)
     - yes (net/http)
   * - libssh2
     - Networking / IO
     - yes (paramiko)
     - yes (ssh2)
     - yes (crypto/ssh)
   * - libssh
     - Networking / IO
     - yes (paramiko)
     -
     - yes (crypto/ssh)
   * - zeromq
     - Networking / IO
     - yes (pyzmq)
     - yes (zmq)
     - yes (pebbe/zmq4)
   * - libmicrohttpd
     - Networking / IO
     -
     -
     -
   * - libwebsockets
     - Networking / IO
     -
     -
     -

   * - lmdb
     - Database
     - yes (lmdb)
     - yes (lmdb)
     - yes (bmatsuo/lmdb-go)
   * - sqlite3
     - Database
     - yes (sqlite3)
     - yes (rusqlite)
     - yes (mattn/go-sqlite3)
   * - hiredis
     - Database
     - yes (redis-py)
     - yes (redis-rs)
     - yes (go-redis)
   * - libpq
     - Database
     - yes (psycopg2)
     - yes (postgres)
     - yes (lib/pq)

   * - lua
     - Scripting
     - yes (lupa)
     - yes (rlua)
     - yes (yuin/gopher-lua)

   * - utf8proc
     - String / Text
     -
     - yes (utf8proc)
     -
   * - cmark
     - String / Text
     - yes (cmark)
     - yes (comrak)
     - yes (yuin/goldmark)
   * - pcre2
     - String / Text
     -
     - yes (pcre2)
     -
   * - libonig
     - String / Text
     -
     - yes (onig)
     -

   * - libpng
     - Image / Graphics
     - yes (Pillow)
     - yes (png)
     - yes (image/png)
   * - libjpeg
     - Image / Graphics
     - yes (Pillow)
     - yes (jpeg-decoder)
     - yes (image/jpeg)
   * - giflib
     - Image / Graphics
     - yes (Pillow)
     -
     - yes (image/gif)
   * - cairo
     - Image / Graphics
     - yes (pycairo)
     - yes (cairo-rs)
     - yes (nicholasgasior/gocairo)
   * - sdl2
     - Image / Graphics
     - yes (pygame)
     - yes (sdl2)
     - yes (veandco/go-sdl2)
   * - libdrm
     - Image / Graphics
     -
     - yes (drm-rs)
     -
   * - opengl
     - Image / Graphics
     - yes (PyOpenGL)
     - yes (gl)
     - yes (go-gl)
   * - glew
     - Image / Graphics
     -
     -
     -

   * - libao
     - Audio
     -
     -
     -
   * - libsndfile
     - Audio
     - yes (soundfile)
     - yes (sndfile)
     -
   * - opus
     - Audio
     - yes (opuslib)
     - yes (opus)
     - yes (hraban/opus)
   * - vorbis
     - Audio
     -
     - yes (lewton)
     -

   * - libffi
     - System / Utility
     - yes (cffi)
     - yes (libffi)
     -
   * - libelf
     - System / Utility
     - yes (pyelftools)
     -
     - yes (debug/elf)
   * - libseccomp
     - System / Utility
     -
     - yes (libseccomp)
     - yes (seccomp-golang)
   * - libcap
     - System / Utility
     -
     - yes (caps-rs)
     - yes (syndtr/gocapability)
   * - libsystemd
     - System / Utility
     - yes (pystemd)
     - yes (zbus)
     - yes (coreos/go-systemd)
   * - libudev
     - System / Utility
     - yes (pyudev)
     - yes (udev-rs)
     -
   * - libbpf
     - System / Utility
     -
     - yes (libbpf-rs)
     - yes (cilium/ebpf)

   * - gsl
     - Math / Science
     -
     - yes (GSL)
     -
   * - fftw3
     - Math / Science
     - yes (pyFFTW)
     - yes (fftw)
     -

   * - libusb
     - Hardware / Embedded
     - yes (pyusb)
     - yes (rusb)
     - yes (google/gousb)
   * - hidapi
     - Hardware / Embedded
     - yes (hidapi)
     - yes (hidapi)
     - yes (karalabe/hid)
   * - libgpiod
     - Hardware / Embedded
     - yes (gpiod)
     - yes (gpiod)
     -

   * - libnvme
     - Storage
     - yes (libnvme)
     -
     -
   * - liburing
     - Storage
     -
     - yes (io-uring)
     -
   * - libaio
     - Storage
     -
     -
     -

The **Python**, **Rust**, and **Go** columns indicate whether the library
has well-known bindings or wrappers for those languages.

C idioms catalog
----------------

The survey, counted with yace 0.5.9, identified 12 categories of C idioms that
affect FFI friendliness. How yace treats each is now set by the rules of the C
subset, :ref:`sec-ir-rules`. Each category below says how FFI-friendly the
idiom is and how many libraries use it.

1. Enum types in type positions (53 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These headers use bare ``enum`` types as function parameters, return types, or
struct fields, without a typedef alias. The idiom is straightforward to
support, as the values of an enum map directly to integers across all FFI
boundaries, so its FFI friendliness is high.

2. ``char`` without explicit sign (49 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These headers use plain ``char``, neither ``signed char`` nor ``unsigned
char``. The C standard leaves its signedness implementation-defined. yace keeps
it as ``char``, and each target maps it to its language's C character type,
such as ``c_char`` in Rust, so the binding has the signedness of the platform,
as C does.

The FFI friendliness of plain ``char`` is medium: it works in practice, but its
signedness is ambiguous.

3. Symbolic alias macros (47 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The value of such a ``#define`` is the name of another macro rather than a
literal::

    #define BROTLI_DEFAULT_MODE  BROTLI_MODE_GENERIC
    #define Z_ASCII              Z_TEXT

Headers use these aliases for deprecated names, default values, and platform
abstraction. An alias cannot be represented as a simple constant in an FFI,
as the chain of references has to be resolved at compile time, so its FFI
friendliness is low.

4. String constant macros (20 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The value of such a ``#define`` is a string literal. yace 0.5.9 matched the
value with a regular expression that did not accept dots, hyphens or slashes,
and skipped the define. yace now reads the value from its tokens::

    #define ZLIB_VERSION  "1.3.1"

Once parsed, the FFI friendliness of a string constant is high, as every FFI
supports strings.

5. Function/type alias macros (25 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Such a ``#define`` maps the name of one function or type to another::

    #define SSLv23_method  TLS_method

Headers use these aliases for API versioning and platform abstraction. A
binding generator has to decide whether to emit the alias, its target, or both.
Their FFI friendliness is low, as an FFI has no direct representation of them.

6. Docstring validation errors (10 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Doxygen comments with parameterless tags (``@returns``, ``@brief``, ``@see``)
failed to parse in yace 0.6.0 and earlier, dropping the declaration. They are
parsed now. FFI friendliness does not apply to them, as they are metadata only.

7. ``const`` typedef in elaborated types (9 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

yace 0.5.9 split the spelling of an elaborated type into words, and a
``const``-qualified typedef name in a type position did not fit that split.
yace now resolves the elaborated type through Clang::

    void draw(const point_t *p);

Once parsed, their FFI friendliness is high, as ``const`` pointers are standard
in FFI.

8. Incomplete arrays (9 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These are the flexible array members of C99::

    struct msg { int len; char data[]; };

A flexible array member has no fixed size, which makes it awkward for an FFI
binding that needs to know the layout of the struct at compile time. Its FFI
friendliness is low, as the binding has to manage the buffer by hand.

9. Anonymous unions/structs (12 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These are struct or union members without a name, nested inside another
struct. Protocol and hardware definitions use them. Most FFI systems cannot
represent them directly, and require flattening or synthetic names. Their FFI
friendliness is low, as most languages have no direct representation of them.

10. Unnamed structs/unions (5 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These are structs or unions with no tag name, typically used as fields of other
structs. They are similar to anonymous members, but at the level of the type
definition. Their FFI friendliness is low, as a binding has to give them
synthetic names.

11. ``long double`` (1 library)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``long double`` is an extended-precision floating-point type. Of the surveyed
libraries, only fftw3 uses it. Most FFI systems do not support ``long double``
natively. Its FFI friendliness is very low, as it has no portable FFI
representation.

12. ``TypeKind.INVALID`` (3 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Clang reports the type as ``INVALID``, usually for complex preprocessor
constructs or platform-specific builtins. yace cannot correct a type that Clang
reports as invalid. FFI friendliness does not apply, as the cause is a
limitation of Clang.

Summary
^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 5 45 15 20

   * - #
     - Pattern
     - Libraries
     - FFI friendliness
   * - 1
     - Enum types in type positions
     - 53
     - High
   * - 2
     - ``char`` without sign
     - 49
     - Medium
   * - 3
     - Symbolic alias macros
     - 47
     - Low
   * - 4
     - String constant macros
     - 20
     - High
   * - 5
     - Function/type alias macros
     - 25
     - Low
   * - 6
     - Docstring validation
     - 10
     - N/A
   * - 7
     - ``const`` typedef elaborated
     - 9
     - High
   * - 8
     - Incomplete arrays
     - 9
     - Low
   * - 9
     - Anonymous unions/structs
     - 12
     - Low
   * - 10
     - Unnamed structs/unions
     - 5
     - Low
   * - 11
     - ``long double``
     - 1
     - Very low
   * - 12
     - ``TypeKind.INVALID``
     - 3
     - N/A
