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

Failing means a traceback, a timeout or an ``internal-error`` diagnostic, and it
is a bug in yace. A rule broken is not; it is what a header written for yace
would have to change, and it shows which idioms are common in practice.

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

Useful flags:

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

The libraries span a broad range of domains. The table below lists each
library, the domain it belongs to, and whether it is known to have bindings in
other languages.

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

The survey identified **12 categories of C idioms** that affect FFI
friendliness, counted with yace 0.5.9. How yace treats each is now set by the
rules of the C subset, :ref:`sec-ir-rules`. They are listed below in order of prevalence, with a summary of
how FFI-friendly each idiom is and how many libraries use it.

1. Enum types in type positions (53 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Using bare ``enum`` types as function parameters, return types, or struct
fields without a typedef alias. Extremely common but straightforward to
support --- the enum values map directly to integers across all FFI
boundaries.

**FFI friendliness:** High --- enums are integers.

2. ``char`` without explicit sign (49 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Plain ``char`` (neither ``signed char`` nor ``unsigned char``). The C standard
leaves its signedness implementation-defined. yace keeps it as ``char``, and
each target maps it to its language's C character type, such as ``c_char`` in
Rust, so the binding has the signedness of the platform, as C does.

**FFI friendliness:** Medium --- works in practice but semantically ambiguous.

3. Symbolic alias macros (47 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``#define`` where the value is another macro name rather than a literal::

    #define BROTLI_DEFAULT_MODE  BROTLI_MODE_GENERIC
    #define Z_ASCII              Z_TEXT

Common for deprecation aliases, default values, and platform abstraction.
These cannot be represented as simple constants in FFI --- they require
resolving the reference chain.

**FFI friendliness:** Low --- requires compile-time resolution.

4. String constant macros (20 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``#define`` with a string literal value containing characters the parser's
regex doesn't yet match (dots, hyphens, slashes)::

    #define ZLIB_VERSION  "1.3.1"

**FFI friendliness:** High once parsed --- strings are universally supported.

5. Function/type alias macros (25 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``#define`` mapping one function or type name to another::

    #define SSLv23_method  TLS_method

Used for API versioning and platform abstraction. Requires policy decisions
about whether to emit the alias, the target, or both.

**FFI friendliness:** Low --- no direct FFI representation.

6. Docstring validation errors (10 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Doxygen comments with parameterless tags (``@returns``, ``@brief``, ``@see``)
failed to parse in yace 0.6.0 and earlier, dropping the declaration. They are
parsed now.

**FFI friendliness:** N/A --- metadata only.

7. ``const`` typedef in elaborated types (9 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``const``-qualified typedef names in type positions confuse the elaborated type
splitter::

    void draw(const point_t *p);

**FFI friendliness:** High once parsed --- ``const`` pointers are standard FFI.

8. Incomplete arrays (9 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Flexible array members (C99)::

    struct msg { int len; char data[]; };

These have no fixed size, making them awkward for FFI bindings that need to
know struct layout at compile time.

**FFI friendliness:** Low --- requires manual buffer management.

9. Anonymous unions/structs (12 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Unnamed struct or union members nested inside another struct. Common in
protocol and hardware definitions. Most FFI systems cannot represent these
directly and require flattening or synthetic names.

**FFI friendliness:** Low --- no direct representation in most languages.

10. Unnamed structs/unions (5 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Structs or unions with no tag name, typically used as fields of other structs.
Similar to anonymous members but at the type-definition level.

**FFI friendliness:** Low --- requires synthetic naming.

11. ``long double`` (1 library)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Extended-precision floating point. Only fftw3 uses it in this survey. Most FFI
systems do not support ``long double`` natively.

**FFI friendliness:** Very low --- no portable FFI representation.

12. ``TypeKind.INVALID`` (3 libraries)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Clang reports the type as ``INVALID``, usually for complex preprocessor
constructs or platform-specific builtins. Cannot be fixed in yace.

**FFI friendliness:** N/A --- clang limitation.

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
