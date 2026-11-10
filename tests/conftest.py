# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import importlib.util
import shutil
from pathlib import Path

import pytest

from yace.ir.cparser import CParser

HEADERS = Path(__file__).parent / "headers"

ESCAPED = '/** S */\n#define API_S "a\\n\\"b\\"\\x41\\t\\\\" "c\\xc3\\xa9"\n'
ESCAPED_VALUE = 'a\n"b"A\t\\cé'

# Records with a flexible array member, and records holding them, which ISO C
# allows in no array and no struct: a flexible array of one is left out where
# that keeps the alignment, the others are skipped, and so what uses them
FLEXIBLE = (
    "#include <stdint.h>\n"
    "struct api_fin { uint32_t n; uint8_t d[]; };\n"
    "struct api_fwide { uint64_t n; uint8_t d[]; };\n"
    "union api_feither { struct api_fin in; uint32_t n; };\n"
    "struct api_fout { uint32_t n; struct api_fin in[]; };\n"
    "struct api_falign { uint32_t n; struct api_fwide in[]; };\n"
    "struct api_fmember { struct api_fin in; uint32_t n; };\n"
    "struct api_farr { uint32_t n; union api_feither e[2]; };\n"
    "int api_fuse(struct api_fout *o, struct api_fmember *m);\n"
)

# Records the bindings cannot hold, and those that use them, all skipped, and a
# record with padding bits, kept
SKIPPED = (
    "#include <sys/time.h>\n"
    "struct api_r;\nint api_before(struct api_r *v);\n"
    "struct api_r { long double x; };\nint api_after(struct api_r *v);\n"
    "struct api_outer { long double x; struct api_inner { int a; } in; };\n"
    "int api_inner_a(struct api_inner *v);\n"
    "struct api_t { struct timeval tv; int n; };\nint api_t_n(struct api_t *v);\n"
    "struct api_nest;\nstruct api_host { struct api_nest { int a; } at; };\n"
    "struct api_flags { unsigned int a : 4; unsigned int : 4; unsigned int b : 8; };\n"
    "int api_flags_b(struct api_flags *v);\n"
    "#include <pthread.h>\nstruct api_lock { pthread_mutex_t m; int n; };\n"
    "int api_lock_n(struct api_lock *v);\n"
    "typedef void (*api_tick_cb)(struct timeval tv, void *ctx);\n"
    "struct timeval *api_now(void);\n"
    "struct api_z { unsigned int a : 4; unsigned int : 0; unsigned int b : 4; };\n"
    "struct api_m { unsigned char a; unsigned int : 4; unsigned char b; };\n"
    "int api_m_b(struct api_m *v);\n"
    "struct api_pad { unsigned int : 8; };\nint api_pad_n(struct api_pad *v);\n"
    "/** O */\nstruct api_o;\nstruct api_holder { struct api_o { int a; } o; };\n"
    "#include <sys/types.h>\n#include <stdint.h>\n"
    "struct api_proc { pid_t pid; time_t t; off_t off; int n; };\n"
    "off_t api_seek(struct api_proc *p, off_t off);\n"
    "int api_bytes(const u_char *data, u_int len);\n"
    "struct api_many { struct api_flags many[2]; int tail; };\n"
    "struct api_mix { uint8_t a : 4; uint16_t b : 12; };\n"
    "struct api_packed { unsigned int a : 4; uint8_t b; };\n"
    "int api_mix_b(struct api_mix *m, struct api_packed *p, struct api_many *n);\n"
    "struct api_pk1 { uint16_t a; uint32_t b : 16; };\n"
    "struct api_pk2 { uint8_t arr[3]; uint32_t b : 8; };\n"
    "struct api_chars { char a : 4; char b : 4; };\n"
    "int api_pk(struct api_pk1 *a, struct api_pk2 *b, struct api_chars *c);\n"
    "#include <stdarg.h>\n#include <setjmp.h>\n"
    "int api_vlog(const char *fmt, va_list ap);\nint api_jump(jmp_buf env);\n"
) + FLEXIBLE


# A record with fields of bits, and the masks of their parts
BITS = (
    "#include <stdint.h>\n"
    "/** A status */\nstruct api_status {\n"
    "\tuint16_t code; ///< Status code, see API_STATUS_CODE_*\n"
    "\tuint64_t wide; ///< All of the bits, see API_STATUS_WIDE_*\n};\n"
    "/** Kind; bits 2:0 of 'code' */\n#define API_STATUS_CODE_TYPE 0x7\n"
    "/** Delay; bits 11:8 of 'code' */\n#define API_STATUS_CODE_DELAY 0xf00\n"
    "/** Do not retry; bit 15 of 'code' */\n#define API_STATUS_CODE_DNR 0x8000\n"
    "/** Top; bit 63 of 'wide' */\n#define API_STATUS_WIDE_TOP 0x8000000000000000\n"
    "/** Low; bits 31:0 of 'wide' */\n#define API_STATUS_WIDE_LOW 0xffffffff\n"
)


# A packed record, no field after the first aligned, one of them a field of
# bits, and a packed union
PACKED = (
    "#include <stdint.h>\n"
    "/** P */\nstruct api_p {\n\tint32_t x; ///< X\n\tint32_t y; ///< Y\n};\n"
    "/** K */\nstruct __attribute__((packed)) api_k {\n"
    "\tuint8_t tag; ///< Tag\n\tuint32_t value; ///< Value\n"
    "\tstruct api_p at; ///< At\n\tstruct api_p path[2]; ///< Path\n"
    "\tuint16_t pair[2]; ///< Pair\n\tuint16_t type; ///< Type, see API_K_TYPE_*\n};\n"
    "/** Low; bits 3:0 of 'type' */\n#define API_K_TYPE_LOW 0xf\n"
    "/** U */\nunion __attribute__((packed)) api_ku {\n"
    "\tuint64_t n; ///< N\n\tstruct api_p p; ///< P\n};\n"
)

# An api_k of a value in every field, as each target fills it in, and printed
PACKED_C = (
    "{.tag = 1, .value = 0xdeadbeef, .at = {-2, 3}, .path = {{4, 5}, {6, 7}},"
    " .pair = {8, 9}, .type = 0x1a}"
)
PACKED_PRINTED = (
    "api_k:\n  tag: 1\n  value: 3735928559\n  at:\n    x: -2\n    y: 3\n"
    '  path: [{"x": 4, "y": 5}, {"x": 6, "y": 7}]\n  pair: [8, 9]\n'
    "  type: {val: 0x1a, low: 0xa}\n"
    '{"tag": 1, "value": 3735928559, "at": {"x": -2, "y": 3}, "path":'
    ' [{"x": 4, "y": 5}, {"x": 6, "y": 7}], "pair": [8, 9],'
    ' "type": {"val": 26, "low": 10}}\n'
)


@pytest.fixture(scope="session")
def parser():
    return CParser()


@pytest.fixture
def parse(parser, tmp_path):
    """Parse the C source text as a header; returns the (Model, [Diagnostic])"""

    def parse(text: str, name: str = "api.h"):
        path = tmp_path / name
        path.write_text(text)
        return parser.parse(path)

    return parse


needs_cc = pytest.mark.skipif(not shutil.which("cc"), reason="no C compiler")
needs_cargo = pytest.mark.skipif(not shutil.which("cargo"), reason="no Rust toolchain")
needs_zig = pytest.mark.skipif(not shutil.which("zig"), reason="no Zig toolchain")
needs_go = pytest.mark.skipif(not shutil.which("go"), reason="no Go toolchain")
needs_cython = pytest.mark.skipif(
    importlib.util.find_spec("Cython") is None, reason="no Cython"
)
