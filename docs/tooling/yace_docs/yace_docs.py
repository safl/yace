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
    """Generate the IR entity listing RST file."""

    from jinja2 import BaseLoader, Environment

    from yace.model import Model

    template_str = """\
.. _sec-ir-list:

Entity Listing
==============

{% for entity in entities %}
* ``{{ entity.key }}``: :py:class:`{{ entity.mod }}`; {{ entity.doc }}
{% endfor %}
"""
    docs_root = find_docs_root()
    output_path = docs_root / "src" / "ir" / "list.rst"

    template = Environment(loader=BaseLoader()).from_string(template_str)

    entities = []
    for key, cls in Model.MAPPING.items():
        doc, *_ = [
            x.strip() for x in cls.__dict__.get("__doc__").split("\n") if x.strip()
        ]
        entities.append(
            {
                "key": key,
                "mod": ".".join([cls.__module__, cls.__name__]),
                "doc": doc.replace(":", ""),
            }
        )

    output_path.write_text(template.render(entities=entities))


def clean():
    """Remove the documentation build directory."""

    docs_root = find_docs_root()
    builddir = docs_root / "builddir"

    if builddir.exists():
        shutil.rmtree(builddir)
        print(f"Removed {builddir}")
    else:
        print(f"Nothing to clean ({builddir} does not exist)")
