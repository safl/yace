# C Idioms Not Yet Handled by yace

Summary of C language patterns that yace's parser does not yet fully support,
based on a survey of 67 Debian-packaged C libraries (current parse rate: 83.7%).

## 1. TypeKind.ENUM in Type Positions (582 skips, 53 libraries)

**What it is:** When an `enum` type is used directly as a function parameter,
return type, or struct field type — without a typedef alias.

```c
enum color { RED, GREEN, BLUE };
void paint(enum color c);           // parameter type is TypeKind.ENUM
enum color get_color(void);         // return type is TypeKind.ENUM
struct widget { enum color fg; };   // field type is TypeKind.ENUM
```

**Why it's skipped:** `typekind_to_typespec()` handles `ELABORATED` and `RECORD`
but does not match bare `TypeKind.ENUM` when it appears outside of an
`ELABORATED` wrapper. Clang sometimes presents enum types this way.

**Affected libraries:** Nearly all (53/67) — cairo, curl, gnutls, openssl,
sqlite3, libusb, pcre2, etc.

---

## 2. `char` Without Explicit Sign (469 skips, 49 libraries)

**What it is:** Plain `char` (not `signed char` or `unsigned char`). The C
standard leaves the signedness of `char` implementation-defined.

```c
const char *name;       // is this signed or unsigned?
char buf[256];
```

**Why it's skipped:** yace coerces `char` → `signed char` and emits a warning.
The entity IS parsed but counted as a skip because a warning is returned.
This is a deliberate design choice — yace wants to be explicit about signedness.

**Affected libraries:** Nearly all (49/67) — every library that uses `char *`
strings without an explicit `signed`/`unsigned` qualifier.

---

## 3. Symbolic Alias Macros (376 skips, 47 libraries)

**What it is:** `#define` where the value is another macro name, not a literal.

```c
#define BROTLI_DEFAULT_MODE     BROTLI_MODE_GENERIC
#define CMARK_NODE_HEADER       CMARK_NODE_HEADING      // deprecation alias
#define Z_ASCII                 Z_TEXT                   // compatibility alias
#define SSL_get_peer_certificate SSL_get1_peer_certificate
```

**Common use cases:**
- **Deprecation/compatibility aliases** (old name → new name)
- **Default value aliases** (DEFAULT → specific value)
- **Platform abstraction** (`#define EXPORT __attribute__((visibility("default")))`)

**Why it's skipped:** `literal_from_text()` only recognizes integer, hex, and
quoted string literals. A symbolic reference like `BROTLI_MODE_GENERIC` doesn't
match any of those patterns.

**Affected libraries:** 47/67 — extremely common pattern.

---

## 4. String Constant Macros (289 skips, 20 libraries)

**What it is:** `#define` where the value is a string literal, but the regex
in `literal_from_text()` doesn't match it.

```c
#define CAIRO_TAG_DEST          "cairo.dest"
#define ZLIB_VERSION            "1.3.1"
#define LIBSSH2_VERSION         "1.11.0"
#define MHD_HTTP_VERSION_1_1    "HTTP/1.1"
```

**Why it's skipped:** The string regex `\"[\s\wa-zA-Z0-9]+\"` doesn't match
strings containing dots, hyphens, slashes, or other punctuation. The regex
is too restrictive.

**Affected libraries:** 20/67 — cairo, gnutls, jansson, libpng, libssh2,
openssl, zlib, etc.

---

## 5. Function/Type Alias Macros (100 skips, 25 libraries)

**What it is:** `#define` where the value is a function name or type keyword.

```c
#define BZ_EXTERN              extern
#define _cairo_api              _cairo_import
#define cmark_node_get_header_level cmark_node_get_heading_level
#define SSLv23_method           TLS_method
```

**Common use cases:**
- **API versioning** (old function name → new function name)
- **Keyword abstraction** (`extern`, `inline`, visibility attributes)
- **Platform-specific aliases**

**Why it's skipped:** Same as symbolic aliases — `literal_from_text()` doesn't
handle these.

**Affected libraries:** 25/67

---

## 6. Docstring Validation Errors (190 skips, 10 libraries)

**What it is:** Doxygen-style comments that don't conform to yace's expected
tag structure, causing Pydantic validation failures.

```c
/**
 * @returns 0 on success, negative on error
 * @brief Do something
 * @see other_function
 */
```

**Why it's skipped:** The `Docstring.from_cursor()` parser stores tags as dicts,
but some tags (like `@returns`, `@brief`, `@see`) have no parameter — just a
description. The Pydantic model expects `tags` values to be `dict[str, str]` but
gets a plain `str` for parameterless tags.

**Affected libraries:** 10/67 — brotli, gnutls, libbpf, libmicrohttpd, lmdb,
lz4, opus, utf8proc, yaml, zstd.

---

## 7. `const struct/union` in Type Positions (73 skips, 9 libraries)

**What it is:** When a `const`-qualified typedef name appears as a type, the
elaborated type parser splits on spaces and gets confused.

```c
typedef struct { int x; } point_t;
void draw(const point_t *p);       // type is "const point_t"
```

**Why it's skipped:** The `ELABORATED | RECORD` handler does
`*head, keyword, sym = tobj.spelling.split()` — when `const` is involved and
the type is a typedef (not a raw `struct`/`union`), the split produces
unexpected tokens.

**Affected libraries:** 9/67 — cairo, gnutls, expat, hiredis, libpq,
libsystemd, uv.

---

## 8. Incomplete Arrays (35 skips, 9 libraries)

**What it is:** Flexible array members or arrays without a specified size.

```c
struct msg {
    int len;
    char data[];    // TypeKind.INCOMPLETEARRAY — flexible array member (C99)
};
```

**Why it's skipped:** `typekind_to_typespec()` handles `CONSTANTARRAY` but not
`INCOMPLETEARRAY`.

**Affected libraries:** 9/67 — giflib, glew, libaio, libcap, libdrm, libonig,
libusb, opus, uv.

---

## 9. Anonymous Unions/Structs Inside Structs (17 skips, 12 libraries)

**What it is:** Unnamed struct or union members nested inside another struct.

```c
struct packet {
    int type;
    union {                     // anonymous union
        struct { int x, y; };   // anonymous struct
        float data[2];
    };
};
```

**Why it's skipped:** `parse_record()` rejects `UNION_DECL`/`STRUCT_DECL` child
cursors that have their own children (i.e., are inline definitions rather than
forward declarations).

**Affected libraries:** 12/67 — hiredis, libaio, libffi, libjpeg, libpq,
libssh2, libusb, uv, cairo, libcap, sqlite3, yaml.

---

## 10. Unnamed (Anonymous) Structs/Unions (26 skips, 5 libraries)

**What it is:** Structs or unions with no tag name, typically used inside
other structs.

```c
struct elf_section {
    struct {                    // unnamed — "(unnamed struct at file.h:42:5)"
        void *start;
        void *end;
    } data;
};
```

**Why it's skipped:** The elaborated type parser tries to split the spelling
into `keyword` and `sym`, but unnamed types have spellings like
`"struct (unnamed struct at ...)"` which don't match the expected pattern.

**Affected libraries:** 5/67 — gnutls, libelf, libgcrypt, libpng, mbedtls.

---

## 11. `long double` (27 skips, 1 library)

**What it is:** The extended-precision floating point type.

```c
long double fftw_cost(const fftw_plan p);
```

**Why it's skipped:** No `TypeKind.LONGDOUBLE` case in `typekind_to_typespec()`.

**Affected libraries:** 1/67 — fftw3 only.

---

## 12. TypeKind.INVALID (70 skips, 3 libraries)

**What it is:** Clang reports the type as `INVALID`, usually for complex
preprocessor-generated declarations or platform-specific builtins.

**Affected libraries:** 3/67 — fftw3, libpng, openssl.

---

## Summary Table

| # | Pattern | Skips | Libraries | Fixable? |
|---|---------|------:|----------:|----------|
| 1 | Enum types in type positions | 582 | 53 | Yes (add TypeKind.ENUM case) |
| 2 | `char` without sign | 469 | 49 | Design choice (already parsed, just warned) |
| 3 | Symbolic alias macros | 376 | 47 | Partial (resolve through enum trick or chain lookup) |
| 4 | String constant macros | 289 | 20 | Yes (fix regex in literal_from_text) |
| 5 | Function/type alias macros | 100 | 25 | Partial (function aliases could be mapped) |
| 6 | Docstring validation | 190 | 10 | Yes (fix Pydantic model for tags) |
| 7 | `const` typedef elaborated | 73 | 9 | Yes (handle const in elaborated split) |
| 8 | Incomplete arrays | 35 | 9 | Yes (add TypeKind.INCOMPLETEARRAY) |
| 9 | Anonymous unions/structs | 17 | 12 | Medium (need recursive struct parsing) |
| 10 | Unnamed structs/unions | 26 | 5 | Medium (need synthetic names) |
| 11 | `long double` | 27 | 1 | Yes (add TypeKind.LONGDOUBLE case) |
| 12 | TypeKind.INVALID | 70 | 3 | No (clang limitation) |

**Quick wins (items 1, 4, 8, 11):** ~933 additional entities, would bring
overall parse rate from 83.7% to ~86.3%.

**Medium effort (items 6, 7, 9, 10):** ~306 additional entities.

**Design decisions (items 2, 3, 5):** ~945 entities, but require policy choices
about how to represent these in the IR.
