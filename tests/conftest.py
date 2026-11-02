import shutil
from pathlib import Path

import pytest

from yace.ir.cparser import CParser

HEADERS = Path(__file__).parent / "headers"

ESCAPED = '/** S */\n#define API_S "a\\n\\"b\\"\\x41\\t\\\\" "c\\xc3\\xa9"\n'
ESCAPED_VALUE = 'a\n"b"A\t\\cé'

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
