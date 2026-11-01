"""yace docs tooling -- build, serve, and clean documentation."""

import shutil
import subprocess
import sys
from pathlib import Path


def find_docs_root():
    """Search upward from cwd for a directory containing src/conf.py."""

    cur = Path.cwd()
    while True:
        if (cur / "src" / "conf.py").exists():
            return cur
        if (cur / "docs" / "src" / "conf.py").exists():
            return cur / "docs"
        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    raise SystemExit("Unable to find docs root (no src/conf.py found)")


def _ensure_stubs(docs_root):
    """Create placeholder files for generated content that may not exist yet."""

    srcdir = docs_root / "src"
    repodir = docs_root.parent
    stub = "Not generated yet. Run the full docs pipeline to populate.\n"

    # kmdo-generated .out files
    for out_file in [
        srcdir / "codebase" / "900_make.out",
        srcdir / "install" / "100_help.out",
        srcdir / "targets" / "capi" / "300_output.out",
        srcdir / "targets" / "capi" / "400_check.out",
        srcdir / "usage" / "050_yace_help.out",
    ]:
        if not out_file.exists():
            out_file.write_text(stub)

    # example-generated output files
    for out_file in [
        repodir / "output" / "capi" / "libfoo.h",
        repodir / "output" / "capi" / "libfoo_core.h",
        repodir / "output" / "capi" / "libfoo_pp.h",
        repodir / "output" / "capi" / "foo_pp.c",
        repodir / "output" / "capi" / "foo_check.c",
        repodir / "output" / "ctypes" / "foo.py",
    ]:
        if not out_file.exists():
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(stub)


def build_html():
    """Build HTML documentation using sphinx-build."""

    docs_root = find_docs_root()
    srcdir = docs_root / "src"
    builddir = docs_root / "builddir" / "html"

    _ensure_stubs(docs_root)

    cmd = [
        sys.executable,
        "-m",
        "sphinx",
        "-b",
        "html",
        str(srcdir),
        str(builddir),
    ]
    raise SystemExit(subprocess.call(cmd))


def serve():
    """Serve documentation with live-reload using sphinx-autobuild."""

    docs_root = find_docs_root()
    srcdir = docs_root / "src"
    builddir = docs_root / "builddir" / "html"

    _ensure_stubs(docs_root)

    cmd = [
        sys.executable,
        "-m",
        "sphinx_autobuild",
        str(srcdir),
        str(builddir),
    ] + sys.argv[1:]
    raise SystemExit(subprocess.call(cmd))


def gen_entities():
    """Generate the listing of the IR entities and types, and of the C subset rules"""

    import typing

    from yace.ir import decls, types
    from yace.ir.diagnostics import RULES

    docs_root = find_docs_root()

    def classes(annotated):
        union = typing.get_args(annotated)[0]
        return typing.get_args(union)

    def first_line(cls):
        doc = (cls.__doc__ or "").strip()
        return doc.splitlines()[0].rstrip(".") if doc else ""

    lines = [
        ".. _sec-ir-list:",
        "",
        "Entity Listing",
        "==============",
        "",
        "Entities, by ``key``:",
        "",
    ]
    for cls in classes(decls.Entity):
        key = cls.model_fields["key"].default
        lines.append(f"* ``{key}``: :py:class:`{cls.__module__}.{cls.__name__}`")
    lines += ["", "Types, by ``key``:", ""]
    for cls in classes(types.Type):
        key = cls.model_fields["key"].default
        lines.append(f"* ``{key}``: :py:class:`{cls.__module__}.{cls.__name__}`")
    (docs_root / "src" / "ir" / "list.rst").write_text("\n".join(lines) + "\n")

    lines = [
        ".. _sec-ir-rules:",
        "",
        "Rules",
        "=====",
        "",
        "The rules of the C subset, by the name a diagnostic gives. A header",
        "breaking one is still parsed; ``--strict`` makes any diagnostic an error.",
        "",
    ]
    for rule, text in RULES.items():
        lines += [f"``{rule}``", f"  {text}.", ""]
    (docs_root / "src" / "ir" / "rules.rst").write_text("\n".join(lines))


def clean():
    """Remove the documentation build directory."""

    docs_root = find_docs_root()
    builddir = docs_root / "builddir"

    if builddir.exists():
        shutil.rmtree(builddir)
        print(f"Removed {builddir}")
    else:
        print(f"Nothing to clean ({builddir} does not exist)")
