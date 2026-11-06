"""
Diagnostics: where a header steps outside the C subset that **yace** describes an
FFI boundary with

A header outside the subset is still parsed, and everything that can be
represented is; every place it steps outside is reported as a
:class:`.Diagnostic`, naming the rule it breaks. Nothing is dropped or changed
without one. With ``--strict``, any diagnostic fails the conversion.

The rules, by name, with why each exists, are :data:`.RULES`.
"""

from pydantic import BaseModel, ConfigDict

RULES = {
    "anonymous-record": (
        "A struct, union or enum must have a tag. Anonymous ones have no name to"
        " refer to them by in other languages; a record is given a generated"
        " name, and the members of an anonymous enum are made constants"
    ),
    "nested-record": (
        "A struct or union must be defined at the top level, not inside another"
        " record; the record is hoisted to the top level"
    ),
    "bitfield": (
        "Bit-fields have no equivalent in Rust or Zig; use a fixed-width integer"
        " and document the bits"
    ),
    "bit-mask": (
        "A field of bits is an unsigned integer whose doc names the prefix of"
        " its masks, 'see <PREFIX>_*', and each mask a #define of contiguous"
        " bits that fit it, named by the prefix and the part, whose doc ends in"
        " 'bits <hi>:<lo> of '<field>'' or 'bit <n> of '<field>''; a mask that"
        " does not agree is not linked to the field"
    ),
    "flexible-array": (
        "A flexible array member has no length to bind; use a pointer and a"
        " length. A record with one is allowed in no array and no struct, as ISO"
        " C requires; a flexible array of them is left out where that keeps the"
        " layout, and otherwise the record holding it is skipped"
    ),
    "attribute": (
        "Attributes other than packed, such as aligned, change the layout, and"
        " others the calling, in ways the targets cannot all express; they are"
        " ignored"
    ),
    "cxx-keyword": (
        "A name must not be a keyword of C++, which includes the generated C API"
        " as it is; parameters are renamed, other names cannot be"
    ),
    "enum-value": (
        "An enumerator must fit an int, as C99 requires; compilers that allow"
        " more disagree on the type of the enum"
    ),
    "array-parameter": ("An array parameter is a pointer in C; declare it as one"),
    "variadic-function": (
        "Variadic functions cannot be called idiomatically from other languages"
    ),
    "record-by-value": ("Pass and return structs and unions by pointer, not by value"),
    "enum-in-signature": (
        "Do not pass or return an enum; a C enum does not restrict the values,"
        " use an integer and document the enum it takes its values from"
    ),
    "typedef": (
        "Only function pointers may be typedef'd; refer to other types by"
        " their own name"
    ),
    "callback-name": (
        "A function pointer typedef must end in _cb, _callback, _fn, _fun,"
        " _func or _function"
    ),
    "callback-typedef": (
        "A function pointer must be named by a typedef, as a callback; one"
        " written inline is bound only as a raw function pointer"
    ),
    "callback-lifetime": (
        "A callback parameter must say with @lifetime how long the library may"
        " invoke it, which nothing else can tell; without, it is bound only as"
        " a raw pointer"
    ),
    "callback-param-name": ("The parameters of a function pointer must be named"),
    "param-name": (
        "The parameters of a function must be named, for its documentation and"
        " the bindings to name them"
    ),
    "function-like-macro": (
        "Function-like macros are code, not part of the FFI boundary; they"
        " are skipped"
    ),
    "macro-value": (
        "A #define must be a string literal or an integer constant expression;"
        " others are skipped"
    ),
    "unsupported-type": (
        "The type has no equivalent across the targets; the declaration using"
        " it is skipped"
    ),
    "unsupported-declaration": (
        "Only types, functions and constants form the FFI boundary; variables"
        " and inline or static functions are skipped"
    ),
    "external-type": (
        "The type is declared outside the headers and outside the C subset, so"
        " other languages cannot bind it"
    ),
    "string-return": (
        "A returned string is borrowed, never the caller's to free, so it is"
        " returned as const char *"
    ),
    "callback-context": (
        "A callback takes exactly one void * context, and a function taking a"
        " callback takes its context as the next parameter, so other languages"
        " can pass a closure"
    ),
    "annotation": (
        "The documentation says what C cannot: @param[in], [out] or [in,out],"
        " @nullable, @len, @errno, @destroys and @lifetime; each must name what"
        " exists and fits"
    ),
    "handle-lifecycle": (
        "An opaque record a function creates through an [out] pointer must have"
        " a function that @destroys it, so other languages can release it"
    ),
    "missing-doc": ("Declarations on the FFI boundary must be documented"),
    "doc-comment": (
        "A declaration has one doc comment; adjacent ones are joined into one"
    ),
    "parse-error": (
        "The compiler could not parse the headers, together in the order given;"
        " the result is incomplete. Every error is reported, each once"
    ),
    "internal-error": (
        "yace failed on this declaration; it is skipped. This is a bug in yace"
    ),
}


class Diagnostic(BaseModel):
    """Where a header breaks a rule of the C subset, and how"""

    model_config = ConfigDict(extra="forbid")

    rule: str
    message: str
    file: str = ""
    line: int = 0
    column: int = 0

    def __str__(self):
        where = f"{self.file}:{self.line}:{self.column}" if self.file else "<header>"
        return f"{where}: {self.rule}: {self.message}"
