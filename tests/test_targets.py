# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import os

from tests.conftest import HEADERS
from yace.compiler import process
from yace.targets import target as targets


def test_every_target_checks_with_a_relative_output(parser, tmp_path, monkeypatch):
    """The checks run tools in the output directory, given as a relative path"""

    model, _ = parser.parse(HEADERS / "valid.h")
    monkeypatch.chdir(tmp_path)
    installed = sorted(targets.targets())
    failures = process(model, installed, "out")
    assert [
        f for f in failures if "toolchain" not in f and "no compiler" not in f
    ] == []
    assert os.path.isdir(tmp_path / "out")


def test_a_packed_record_holding_bit_fields_checks_in_every_target(parse, tmp_path):
    """A packed record holding a record of bit-fields, which most targets keep
    as its bytes, directly and in a union, as xNVMe's do"""

    model, _ = parse(
        "#include <stdint.h>\n"
        "/** F */\nstruct api_f {\n\tuint8_t a : 4; ///< A\n"
        "\tuint8_t b : 4; ///< B\n};\n"
        "/** W, aligned to 4 */\nstruct api_w {\n\tuint32_t a : 4; ///< A\n"
        "\tuint32_t b : 28; ///< B\n};\n"
        "/** U */\nunion api_u {\n\tstruct api_f f; ///< F\n"
        "\tuint8_t val; ///< Val\n};\n"
        "/** H */\nstruct __attribute__((packed)) api_h {\n\tuint8_t t; ///< T\n"
        "\tstruct api_f f; ///< F\n\tunion api_u u; ///< U\n\tuint32_t v; ///< V\n"
        "\tstruct api_w w; ///< W\n};\n"
    )
    failures = process(model, sorted(targets.targets()), tmp_path)
    assert [
        f for f in failures if "toolchain" not in f and "no compiler" not in f
    ] == []


DOCUMENTED = (
    "#include <stddef.h>\nstruct api_h;\n"
    "/**\n * Open\n *\n * @param[in] name The name\n * @param[out] h Set to it\n"
    " *\n * @return 0 on success, -EINVAL when 'name' is NULL\n *\n"
    " * @note Not thread-safe\n * @see api_close()\n * @errno\n */\n"
    "int api_open(const char *name, struct api_h **h);\n"
    "/**\n * Close\n *\n * @param h The handle\n *\n * @destroys h\n */\n"
    "void api_close(struct api_h *h);\n"
    "/**\n * Count\n *\n * @param h The handle\n *\n * @return How many\n"
    " *\n * @deprecated\n */\n"
    "size_t api_count(const struct api_h *h);\n"
)

# What each target's idiomatic layer says of api_open() and api_count(): the
# parameter given, how it fails, as C says it returns, and the prose tags
DOCUMENTED_AS = {
    "cpp": [
        " * @note Not thread-safe\n * @see api_close()\n * @param name The name\n"
        " * @throws std::system_error api_open() returns: 0 on success, -EINVAL",
        "\t * @deprecated\n\t * @return How many\n",
    ],
    "python": [
        "Note: Not thread-safe\n\n    See also: api_close()\n\n    Args:\n"
        "        name: The name\n\n    Raises:\n        OSError: api_open() returns:",
        "Deprecated\n\n        Returns:\n            How many\n",
    ],
    "rust": [
        "/// Note: Not thread-safe\n        ///\n        /// See also: api_close()\n"
        "        ///\n        /// Calls [`super::api_open`].\n        ///\n"
        "        /// # Parameters\n        ///\n        /// * `name`: The name\n"
        "        ///\n        /// # Errors\n        ///\n"
        "        /// api_open() returns:",
        "/// Deprecated\n        ///\n        /// Calls [`super::api_count`].\n"
        "        ///\n        /// # Returns\n        ///\n        /// How many\n",
    ],
    "zig": [
        "/// Note: Not thread-safe\n    ///\n    /// See also: api_close()\n    ///\n"
        "    /// Parameters:\n    ///\n    /// * `name`: The name\n    ///\n"
        "    /// Errors: api_open() returns:",
        "/// Deprecated\n    ///\n    /// Returns How many\n",
    ],
    "go": [
        "// Note: Not thread-safe.\n//\n// See also: api_close().\n//\n// Parameters:\n"
        "//\n//   - name: The name\n//\n// Errors: api_open() returns:",
        "// Deprecated.\n//\n// Returns How many.\n",
    ],
}


def test_every_target_documents_the_call_it_generates(parse, tmp_path):
    model, _ = parse(DOCUMENTED)
    for name, wanted in DOCUMENTED_AS.items():
        assert process(model, [name], tmp_path, check=False) == []
        generated = "\n".join(
            path.read_text() for path in (tmp_path / name).iterdir() if path.is_file()
        )
        for text in wanted:
            assert text in generated, name


def test_an_apis_own_printer_formats_leave_every_target_building(parse, tmp_path):
    from tests.test_cparser import OWN_PRINTERS

    model, _ = parse(OWN_PRINTERS)
    failures = process(model, sorted(targets.targets()), tmp_path)
    assert [
        f for f in failures if "toolchain" not in f and "no compiler" not in f
    ] == []
