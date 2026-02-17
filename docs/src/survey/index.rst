.. _sec-survey:

================================
 C Library Survey
================================

yace includes a survey of **67 popular C libraries** packaged in Debian. The
survey examines the C idioms these libraries use and evaluates how
FFI-friendly each idiom is. The results guide yace's parser and emitter
priorities.

The survey data reflects the state of these libraries as distributed with
**Debian Trixie** (the current stable release of Debian), tested against
**yace v0.5.9**.

Why a survey?
-------------

C libraries are the bedrock of systems programming, but their headers use a
wide variety of idioms --- some of which do not translate well across language
boundaries. By cataloguing the idioms found in real-world, widely-used
libraries, yace can focus on the patterns that matter most.

The pipeline
------------

For each library the survey runs the full yace pipeline:

1. **Parse** --- ``yace`` reads the library's public headers via libclang and
   produces a YAML intermediate representation (IR).
2. **Emit** --- the CAPI target generates a self-contained C wrapper
   (``*_capi.h`` / ``*_capi.c``) from the IR.
3. **Format** --- ``clang-format`` validates that the emitted code is
   syntactically correct C.
4. **Compile** --- ``gcc`` compiles the wrapper against the real library
   headers and links it.
5. **Run** --- the compiled test binary is executed to verify runtime
   correctness.

A library **passes** only if all five stages succeed.

Running the survey
------------------

Prerequisites: the libraries must be installed via ``apt`` (Debian/Ubuntu).
Then::

    python3 toolbox/survey/survey.py --packaged-only --with-generators

Useful flags:

``--skip-download``
    Reuse previously cached data.
``--report-only``
    Regenerate the Markdown report without re-running the pipeline.
``--packaged-only``
    Only test Debian-packaged libraries (the default set of 67).

Results are written to ``toolbox/survey/report.md``.

Surveyed libraries
------------------

The 67 libraries span a broad range of domains. The table below lists each
library, the domain it belongs to, its current compatibility status with yace,
and whether the library is known to provide official FFI bindings to other
languages.

.. list-table::
   :header-rows: 1
   :widths: 22 18 14 14 14 14

   * - Library
     - Domain
     - Parse rate
     - Python
     - Rust
     - Go

   * - zlib
     - Compression
     - 97.8%
     - yes
     - yes (flate2)
     - yes (compress/zlib)
   * - bzip2
     - Compression
     - 80.4%
     - yes (bz2)
     - yes (bzip2)
     - yes (dsnet/compress)
   * - lz4
     - Compression
     - 57.1%
     - yes (lz4)
     - yes (lz4)
     - yes (pierrec/lz4)
   * - zstd
     - Compression
     - 80.8%
     - yes (zstandard)
     - yes (zstd)
     - yes (klauspost/compress)
   * - brotli
     - Compression
     - 75.8%
     - yes (brotli)
     - yes (brotli)
     - yes (google/brotli)
   * - snappy
     - Compression
     - 71.4%
     - yes (python-snappy)
     - yes (snap)
     - yes (golang/snappy)
   * - lzo
     - Compression
     - 100.0%
     - yes (python-lzo)
     -
     -

   * - mbedtls
     - Crypto / TLS
     - 97.6%
     -
     - yes (mbedtls)
     -
   * - openssl
     - Crypto / TLS
     - 99.4%
     - yes (pyOpenSSL)
     - yes (openssl)
     - yes (crypto/tls)
   * - gnutls
     - Crypto / TLS
     - 85.0%
     -
     -
     -
   * - libsodium
     - Crypto / TLS
     - 100.0%
     - yes (PyNaCl)
     - yes (sodiumoxide)
     - yes (jamesruan/sodium)
   * - nettle
     - Crypto / TLS
     - 24.7%
     -
     - yes (nettle)
     -
   * - libgcrypt
     - Crypto / TLS
     - 98.1%
     -
     -
     -

   * - cjson
     - Serialization
     - 92.1%
     -
     -
     -
   * - jansson
     - Serialization
     - 96.2%
     -
     - yes (jansson-sys)
     -
   * - protobuf_c
     - Serialization
     - 98.6%
     - yes (protobuf)
     - yes (prost)
     - yes (protobuf)
   * - msgpack
     - Serialization
     - 100.0%
     - yes (msgpack)
     - yes (rmp)
     - yes (msgpack-go)
   * - yaml
     - Serialization
     - 65.9%
     - yes (PyYAML)
     - yes (yaml-rust)
     - yes (go-yaml)
   * - expat
     - Serialization
     - 72.3%
     - yes (xml.parsers.expat)
     -
     - yes (encoding/xml)
   * - libxml2
     - Serialization
     - 56.9%
     - yes (lxml)
     - yes (libxml)
     -

   * - mosquitto
     - Networking / IO
     - 92.7%
     - yes (paho-mqtt)
     - yes (rumqttc)
     - yes (paho.mqtt.golang)
   * - nanomsg
     - Networking / IO
     - 100.0%
     - yes (nanomsg)
     - yes (nanomsg)
     - yes (go-nanomsg)
   * - nng
     - Networking / IO
     - 96.4%
     - yes (pynng)
     - yes (nng-rs)
     - yes (go-nng)
   * - event2
     - Networking / IO
     - 100.0%
     -
     -
     -
   * - uv
     - Networking / IO
     - 78.6%
     - yes (pyuv)
     - yes (uv)
     -
   * - curl
     - Networking / IO
     - 96.5%
     - yes (pycurl)
     - yes (curl-rust)
     - yes (net/http)
   * - libssh2
     - Networking / IO
     - 97.0%
     - yes (paramiko)
     - yes (ssh2)
     - yes (crypto/ssh)
   * - libssh
     - Networking / IO
     - 92.7%
     - yes (paramiko)
     -
     - yes (crypto/ssh)
   * - zeromq
     - Networking / IO
     - 98.9%
     - yes (pyzmq)
     - yes (zmq)
     - yes (pebbe/zmq4)
   * - libmicrohttpd
     - Networking / IO
     - 85.0%
     -
     -
     -
   * - libwebsockets
     - Networking / IO
     - 100.0%
     -
     -
     -

   * - lmdb
     - Database
     - 95.9%
     - yes (lmdb)
     - yes (lmdb)
     - yes (bmatsuo/lmdb-go)
   * - sqlite3
     - Database
     - 97.7%
     - yes (sqlite3)
     - yes (rusqlite)
     - yes (mattn/go-sqlite3)
   * - hiredis
     - Database
     - 85.5%
     - yes (redis-py)
     - yes (redis-rs)
     - yes (go-redis)
   * - libpq
     - Database
     - 82.2%
     - yes (psycopg2)
     - yes (postgres)
     - yes (lib/pq)

   * - lua
     - Scripting
     - 98.6%
     - yes (lupa)
     - yes (rlua)
     - yes (yuin/gopher-lua)

   * - utf8proc
     - String / Text
     - 88.5%
     -
     - yes (utf8proc)
     -
   * - cmark
     - String / Text
     - 95.0%
     - yes (cmark)
     - yes (comrak)
     - yes (yuin/goldmark)
   * - pcre2
     - String / Text
     - 100.0%
     -
     - yes (pcre2)
     -
   * - libonig
     - String / Text
     - 85.7%
     -
     - yes (onig)
     -

   * - libpng
     - Image / Graphics
     - 96.8%
     - yes (Pillow)
     - yes (png)
     - yes (image/png)
   * - libjpeg
     - Image / Graphics
     - 94.6%
     - yes (Pillow)
     - yes (jpeg-decoder)
     - yes (image/jpeg)
   * - giflib
     - Image / Graphics
     - 96.6%
     - yes (Pillow)
     -
     - yes (image/gif)
   * - cairo
     - Image / Graphics
     - 95.8%
     - yes (pycairo)
     - yes (cairo-rs)
     - yes (nicholasgasior/gocairo)
   * - sdl2
     - Image / Graphics
     - 100.0%
     - yes (pygame)
     - yes (sdl2)
     - yes (veandco/go-sdl2)
   * - libdrm
     - Image / Graphics
     - 92.0%
     -
     - yes (drm-rs)
     -
   * - opengl
     - Image / Graphics
     - 100.0%
     - yes (PyOpenGL)
     - yes (gl)
     - yes (go-gl)
   * - glew
     - Image / Graphics
     - 78.6%
     -
     -
     -

   * - libao
     - Audio
     - 89.5%
     -
     -
     -
   * - libsndfile
     - Audio
     - 89.9%
     - yes (soundfile)
     - yes (sndfile)
     -
   * - opus
     - Audio
     - 42.6%
     - yes (opuslib)
     - yes (opus)
     - yes (hraban/opus)
   * - vorbis
     - Audio
     - 100.0%
     -
     - yes (lewton)
     -

   * - libffi
     - System / Utility
     - 50.6%
     - yes (cffi)
     - yes (libffi)
     -
   * - libelf
     - System / Utility
     - 67.8%
     - yes (pyelftools)
     -
     - yes (debug/elf)
   * - libseccomp
     - System / Utility
     - 99.4%
     -
     - yes (libseccomp)
     - yes (seccomp-golang)
   * - libcap
     - System / Utility
     - 95.7%
     -
     - yes (caps-rs)
     - yes (syndtr/gocapability)
   * - libsystemd
     - System / Utility
     - 81.0%
     - yes (pystemd)
     - yes (zbus)
     - yes (coreos/go-systemd)
   * - libudev
     - System / Utility
     - 98.1%
     - yes (pyudev)
     - yes (udev-rs)
     -
   * - libbpf
     - System / Utility
     - 76.1%
     -
     - yes (libbpf-rs)
     - yes (cilium/ebpf)

   * - gsl
     - Math / Science
     - 100.0%
     -
     - yes (GSL)
     -
   * - fftw3
     - Math / Science
     - 59.1%
     - yes (pyFFTW)
     - yes (fftw)
     -

   * - libusb
     - Hardware / Embedded
     - 96.6%
     - yes (pyusb)
     - yes (rusb)
     - yes (google/gousb)
   * - hidapi
     - Hardware / Embedded
     - 97.4%
     - yes (hidapi)
     - yes (hidapi)
     - yes (karalabe/hid)
   * - libgpiod
     - Hardware / Embedded
     - 100.0%
     - yes (gpiod)
     - yes (gpiod)
     -

   * - libnvme
     - Storage
     - 100.0%
     - yes (libnvme)
     -
     -
   * - liburing
     - Storage
     - 95.7%
     -
     - yes (io-uring)
     -
   * - libaio
     - Storage
     - 93.8%
     -
     -
     -

The **Parse rate** column shows the percentage of entities in the library's
headers that yace successfully parses. A rate below 100% means some C idioms
in that library are not yet handled (see the next section for details). The
**Python**, **Rust**, and **Go** columns indicate whether the library
has well-known bindings or wrappers for those languages --- these are the
languages where yace-generated FFI can complement or replace hand-written
bindings.

C idioms catalog
----------------

The survey identified **12 categories of C idioms** that affect FFI
friendliness. They are listed below in order of prevalence, with a summary of
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
leaves signedness implementation-defined, which creates ambiguity for FFI. yace
deliberately coerces ``char`` to ``signed char`` and emits a warning.

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
that don't conform to yace's expected structure. A parser limitation, not an
inherent FFI issue.

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
   :widths: 5 40 10 10 20

   * - #
     - Pattern
     - Skips
     - Libraries
     - FFI friendliness
   * - 1
     - Enum types in type positions
     - 582
     - 53
     - High
   * - 2
     - ``char`` without sign
     - 469
     - 49
     - Medium
   * - 3
     - Symbolic alias macros
     - 376
     - 47
     - Low
   * - 4
     - String constant macros
     - 289
     - 20
     - High
   * - 5
     - Function/type alias macros
     - 100
     - 25
     - Low
   * - 6
     - Docstring validation
     - 190
     - 10
     - N/A
   * - 7
     - ``const`` typedef elaborated
     - 73
     - 9
     - High
   * - 8
     - Incomplete arrays
     - 35
     - 9
     - Low
   * - 9
     - Anonymous unions/structs
     - 17
     - 12
     - Low
   * - 10
     - Unnamed structs/unions
     - 26
     - 5
     - Low
   * - 11
     - ``long double``
     - 27
     - 1
     - Very low
   * - 12
     - ``TypeKind.INVALID``
     - 70
     - 3
     - N/A
