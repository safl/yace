"""
The :class:`.CAPI` emits a C API consisting of the following files:

* ``lib{meta.prefix}.h``        -- Library header bundle
* ``lib{meta.prefix}_core.h``   -- The core API declarations
* ``lib{meta.prefix}_pp.h``     -- Pretty-printer definitions
* ``{meta.prefix}_pp.c``        -- Pretty-printer implementation

additionally then:

* ``{meta.prefix}_check.c``     -- ``main()`` program checking generated code

This program is utilized by the 'check-stage' and is as such not part of the
emitted C API but rather a test of it.

Last then:

* ``doxygen.conf``              -- Doxygen configuration for the above

Is emitted, this is to produce DoxyGen documentation for API.

The 'format' stage also emits the files:

* ``hdr.clang-format`` -- clang-format rule-file for header-files
* ``src.clang-format`` -- clang-format rule-file for source-files

Thus, the above files are what you should expect to see in the output-directory
"""

import copy
import logging as log
import shutil
from pathlib import Path

from yace.emitters import Emitter
from yace.errors import TransformationError
from yace.targets.target import Target
from yace.tools import ClangFormat, Doxygen, Gcc
from yace.transformations import CStyle


_INTEGER_KEY_TO_FMT = {
    "i_tspec": "%d",
    "u_tspec": "%u",
    "ih_tspec": "%hd",
    "us_tspec": "%hu",
    "il_tspec": "%ld",
    "ul_tspec": "%lu",
    "ill_tspec": "%lld",
    "ull_tspec": "%llu",
}


def emit_cstr_fmt(typespec):
    # Arrays decay to pointers in C expressions
    if typespec.array:
        return "%p"
    # Check pointer/function-pointer first — a pointer-to-int is still a pointer
    if typespec.pointer or typespec.ret is not None:
        return "%p"
    elif typespec.character:
        return "%c"
    elif typespec.size:
        return "%zu" if typespec.unsigned else "%zd"
    elif typespec.integer and typespec.width and typespec.width_fixed:
        return f'%"PRIx{ typespec.width }"'
    elif typespec.integer:
        return _INTEGER_KEY_TO_FMT.get(typespec.key, "%d")
    elif typespec.boolean:
        return "%d"
    elif typespec.enum:
        return "%d"
    elif typespec.real:
        if typespec.width == 64:
            return "%lf"
        return "%f"

    return "%d"  # fallback


def emit_cstr_cast(typespec, accessor):
    """Wrap an accessor with a cast when needed for printf format safety."""
    if typespec.array:
        return f"(void *){accessor}"
    if typespec.ret is not None:
        # Function pointer: cast via intermediate to avoid ISO C warning
        return f"(void *)(uintptr_t){accessor}"
    if typespec.pointer:
        return f"(void *){accessor}"
    if typespec.pointee is not None:
        return f"(void *){accessor}"
    return accessor


def collect_forward_decls(entities):
    """Collect all struct/union types that need forward declarations."""
    entity_syms = {e.sym for e in entities if hasattr(e, 'key') and e.key in ("struct_decl", "union_decl")}
    seen = set()

    def _scan_typespec(typ):
        if typ is None:
            return
        if typ.struct and typ.sym and typ.sym not in entity_syms and typ.sym not in seen:
            seen.add(typ.sym)
        if typ.union and typ.sym and typ.sym not in entity_syms and typ.sym not in seen:
            seen.add(typ.sym)
        if typ.pointee:
            _scan_typespec(typ.pointee)
        if typ.ret:
            _scan_typespec(typ.ret)
        if typ.parameters:
            for p in typ.parameters:
                if isinstance(p, dict) and "typ" in p:
                    ptyp = p["typ"]
                    if isinstance(ptyp, dict):
                        from yace.ir.datatypes import Typespec
                        ptyp = Typespec(**ptyp)
                    _scan_typespec(ptyp)

    for entity in entities:
        # Scan function parameters
        if hasattr(entity, 'parameters') and entity.parameters:
            for param in entity.parameters:
                if hasattr(param, 'typ'):
                    _scan_typespec(param.typ)
        # Scan struct/union members
        if hasattr(entity, 'members') and entity.members:
            for member in entity.members:
                if hasattr(member, 'typ'):
                    _scan_typespec(member.typ)
        # Scan return types
        if hasattr(entity, 'ret') and entity.ret:
            _scan_typespec(entity.ret)

    return sorted(seen)


def emit_typespec(typespec, anon: bool = False):
    return typespec.c_spelling()


class CAPI(Target):
    """
    Several helper functions
    """

    NAME = "capi"
    CFLAGS = ["-std=c11", "-pedantic-errors", "-Wall", "-Werror"]

    def __init__(self, output):
        super().__init__(self.NAME, output)

        self.emitter = Emitter(Path(__file__).parent)

        self.tools["clang-format"] = ClangFormat(self.output)
        self.tools["doxygen"] = Doxygen(self.output)
        self.tools["gcc"] = Gcc(self.output)

    def transform(self, model):
        """
        Transform the given model

        * Transform symbols according to :class:`yace.transformation.CStyle`

        That it currently the only thing done to the **yace** IR.
        """

        transformed = copy.deepcopy(model)

        status = CStyle(transformed).walk()
        if not all([res for res in status]):
            raise TransformationError("The CStyle transformation failed")

        return transformed

    def emit(self, model):
        """Emit code"""

        def sanitize_comment(text):
            """Escape nested comment markers in doc strings."""
            return text.replace("/*", "/ *").replace("*/", "* /")

        def c_ident(text):
            """Sanitize text for use as a C identifier."""
            return text.replace("-", "_").replace(".", "_").replace(" ", "_")

        # Build set of known type symbols from entities
        _known_syms = set()
        for e in model.entities:
            sym = getattr(e, "sym", "")
            if sym:
                _known_syms.add(sym)

        # Build a set of struct/union syms that have members (complete types)
        _complete_records = set()
        for e in model.entities:
            ekey = getattr(e, "key", "")
            esym = getattr(e, "sym", "")
            if ekey in ("struct_decl", "union_decl") and esym:
                if getattr(e, "members", None):
                    _complete_records.add(esym)

        def _is_incomplete_field(typ):
            """Check if a type used as a struct field is incomplete (by-value)."""
            if typ.pointer:
                return False
            if (typ.struct or typ.union) and typ.sym:
                if typ.sym not in _complete_records:
                    return True
            return False

        _STDLIB_TYPES = {
            "size_t", "ssize_t", "ptrdiff_t", "intptr_t", "uintptr_t",
            "int8_t", "int16_t", "int32_t", "int64_t",
            "uint8_t", "uint16_t", "uint32_t", "uint64_t",
            "wchar_t", "FILE", "va_list",
        }

        def is_ffi_compatible(entity):
            """Check if an entity can be represented across an FFI boundary."""
            key = getattr(entity, "key", "")
            sym = getattr(entity, "sym", "")

            # Skip standard library types that should not be re-emitted
            if sym in _STDLIB_TYPES:
                return False

            # Anonymous enums can't be referenced by FFI
            if key == "enum" and not sym:
                return False

            # Function declarations with FFI-incompatible types
            if key == "function_decl":
                ret = getattr(entity, "ret", None)
                if ret and _has_ffi_issue(ret):
                    return False
                # Function returning a function pointer — can't emit in C
                if ret and ret.ret is not None:
                    return False
                for param in getattr(entity, "parameters", []) or []:
                    typ = getattr(param, "typ", None)
                    if typ and _has_ffi_issue(typ):
                        return False

            # Function pointer decls with FFI-incompatible parameter types
            if key == "function_pointer_decl":
                for param in getattr(entity, "parameters", []) or []:
                    typ = getattr(param, "typ", None)
                    if typ and _has_ffi_issue(typ):
                        return False

            # Struct/union members with FFI-incompatible types
            if key in ("struct_decl", "union_decl"):
                for member in getattr(entity, "members", []) or []:
                    typ = getattr(member, "typ", None)
                    if typ and _has_ffi_issue(typ):
                        return False
                    # Non-pointer struct/union field with incomplete type
                    if typ and _is_incomplete_field(typ):
                        return False

            return True

        def _has_ffi_issue(typ):
            """Check if a typespec has FFI-incompatible attributes."""
            # Anonymous enum type (no tag)
            if typ.enum and not typ.sym:
                return True
            # Bare enum used by tag (not typedef) — C forbids forward enum refs
            # and FFI tools can't resolve the enum without a typedef
            if typ.enum and typ.sym and not typ.pointer and typ.sym not in _known_syms:
                return True
            # Function pointer return type without typedef name
            if typ.ret is not None and not typ.pointer and not typ.sym:
                return True
            # Reference to a typedef/type not defined in our entity set
            if _is_undefined_type_ref(typ):
                return True
            # Check pointee recursively
            if typ.pointee and _has_ffi_issue(typ.pointee):
                return True
            # Check function pointer parameters recursively
            if typ.ret is not None and typ.parameters:
                for p in typ.parameters:
                    if isinstance(p, dict) and "typ" in p:
                        ptyp = p["typ"]
                        if isinstance(ptyp, dict):
                            from yace.ir.datatypes import Typespec as _Ts
                            ptyp = _Ts(**ptyp)
                        if _has_ffi_issue(ptyp):
                            return True
            return False

        def _is_undefined_type_ref(typ):
            """Check if a typespec references a type not in the entity set."""
            sym = getattr(typ, "sym", "")
            if not sym:
                return False
            # struct/union/enum types are forward-declared, so they're fine
            if typ.struct or typ.union or typ.enum:
                return False
            # Primitives with a sym (e.g. int, char) are fine
            if typ.integer or typ.boolean or typ.character or typ.real or typ.void or typ.size:
                return False
            # Pointers to known types are fine (the pointee carries the type)
            if typ.pointer and typ.pointee:
                return False
            # This is a typedef reference; check if it's in our entity set
            if sym not in _known_syms:
                return True
            return False

        filters = {
            "emit_cstr_fmt": emit_cstr_fmt,
            "emit_cstr_cast": emit_cstr_cast,
            "emit_typespec": emit_typespec,
            "collect_forward_decls": collect_forward_decls,
            "sanitize_comment": sanitize_comment,
            "c_ident": c_ident,
            "is_ffi_compatible": is_ffi_compatible,
        }

        files = [
            (f"lib{model.meta.prefix}_core.h", "file_core.h", self.headers),
            (f"lib{model.meta.prefix}_pp.h", "file_pp.h", self.headers),
            (f"lib{model.meta.prefix}.h", "file_bundle.h", self.headers),
            (f"{model.meta.prefix}_pp.c", "file_pp.c", self.sources),
            (f"{model.meta.prefix}_check.c", "file_check.c", self.sources),
            ("doxygen.conf", "doxygen", self.aux),
        ]
        for filename, template, container in files:
            path = (self.output / filename).resolve()
            with (path).open("w") as file:
                content = self.emitter.render(
                    template,
                    {
                        "meta": model.meta,
                        "entities": model.entities,
                        "headers": self.headers,
                    },
                    filters,
                )
                if content[-1] != "\n":
                    content += "\n"
                file.write(content)

            log.info("produced: %s", path)
            container.append(path)

    def format(self):
        """
        Transfer the clang-format definition from package to output and
        invokes the clang-formater
        """

        path = Path(__file__).parent
        for rules, container in [
            (ClangFormat.CLANGFORMAT_STYLE_C, self.sources),
            (ClangFormat.CLANGFORMAT_STYLE_H, self.headers),
        ]:
            shutil.copyfile(path / rules, self.output / rules)
            self.tools["clang-format"].run(
                [f"--style=file:{rules}", "-i"] + [str(f) for f in container],
            )

        self.tools["doxygen"].run([Doxygen.DOXYGEN_CONF])

    def check(self, model):
        """Build generated sources and run the generated test-program"""

        extra_cflags = []
        extra_ldflags = []
        if model.meta.pkg:
            from subprocess import check_output

            extra_cflags = (
                check_output(["pkg-config", "--cflags", model.meta.pkg])
                .decode()
                .split()
            )
            extra_ldflags = (
                check_output(["pkg-config", "--libs", model.meta.pkg])
                .decode()
                .split()
            )

        binary = self.output / f"{model.meta.prefix}_check"

        rcode, _ = self.tools["gcc"].run(
            CAPI.CFLAGS
            + ["-I", str(self.output)]
            + extra_cflags
            + [str(p) for p in self.sources]
            + ["-o", str(binary)]
            + extra_ldflags
        )
        if rcode:
            return rcode

        from subprocess import STDOUT, run as subprocess_run

        logpath = (self.output / "check.log").resolve()
        with logpath.open("w") as logfile:
            logfile.write(f"# running {binary}\n")
            logfile.flush()
            proc = subprocess_run(
                [str(binary)],
                stdout=logfile,
                stderr=STDOUT,
                check=False,
                cwd=str(self.output),
            )
        if proc.returncode:
            log.error(
                "check program %s exited with rcode(%d), see %s",
                binary,
                proc.returncode,
                logpath,
            )
            return proc.returncode

        return 0
