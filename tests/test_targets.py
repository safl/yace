# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import os

from tests.conftest import HEADERS
from yace.compiler import process
from yace.ir import decls
from yace.targets import target as targets


def test_every_target_checks_with_a_relative_output(parser, tmp_path, monkeypatch):
    """The checks run tools in the output directory, which is given as a
    relative path"""

    model, _ = parser.parse(HEADERS / "valid.h")
    monkeypatch.chdir(tmp_path)
    installed = sorted(targets.targets())
    failures = process(model, installed, "out", include=[HEADERS])
    assert [
        f for f in failures if "toolchain" not in f and "no compiler" not in f
    ] == []
    assert os.path.isdir(tmp_path / "out")


def test_the_go_target_writes_only_its_own_directory(parser, tmp_path):
    model, _ = parser.parse(HEADERS / "valid.h")
    assert process(model, ["go"], tmp_path, check=False) == []
    assert [path.name for path in tmp_path.iterdir()] == ["go"]
    assert (tmp_path / "go" / "libvalid.h").is_file()


def test_a_packed_record_holding_bit_fields_checks_in_every_target(parse, tmp_path):
    """A packed record holds a record of bit-fields directly and inside a
    union, as xNVMe's records do. Most targets represent the record of
    bit-fields as its bytes."""

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
    failures = process(
        model, sorted(targets.targets()), tmp_path / "out", include=[tmp_path]
    )
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

# The text that the idiomatic layer of each target writes in the docs of
# api_open() and api_count(): the parameter that the caller passes, the error
# with what the C doc says api_open() returns, and the @note, @see and
# @deprecated tags
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


LISTED = (
    "/**\n * Run\n *\n * It fails with:\n *\n * - -EINTR: interrupted\n"
    " * - -EAGAIN: no resources\n *\n * @return 0\n */\nint api_run(void);\n"
)

LISTED_AS = {
    "capi": " * - -EINTR: interrupted\n * - -EAGAIN: no resources\n",
    "python": "    - -EINTR: interrupted\n    - -EAGAIN: no resources\n",
    "rust": "/// - -EINTR: interrupted\n    /// - -EAGAIN: no resources\n",
    "zig": "/// - -EINTR: interrupted\n/// - -EAGAIN: no resources\n",
    "cpp": " * - -EINTR: interrupted\n * - -EAGAIN: no resources\n",
    "go": "//   - -EINTR: interrupted\n//   - -EAGAIN: no resources\n",
}


def test_every_target_keeps_the_items_of_a_list_on_lines_of_their_own(parse, tmp_path):
    model, _ = parse(LISTED)
    for name, wanted in LISTED_AS.items():
        assert process(model, [name], tmp_path, check=False) == []
        generated = "\n".join(
            path.read_text() for path in (tmp_path / name).iterdir() if path.is_file()
        )
        assert wanted in generated, name


def test_every_target_but_capi_pp_builds_an_api_that_declares_its_own_printers(
    parse, tmp_path
):
    from tests.test_cparser import OWN_PRINTERS

    model, _ = parse(OWN_PRINTERS)
    # lib<prefix>_pp.h of capi_pp includes the parsed headers, whose printers
    # have the names of the printers that capi_pp generates
    names = [name for name in sorted(targets.targets()) if name != "capi_pp"]
    failures = process(model, names, tmp_path)
    assert [
        f for f in failures if "toolchain" not in f and "no compiler" not in f
    ] == []


def test_every_target_builds_an_api_whose_own_printers_are_tagged_nobind(
    parse, tmp_path
):
    """NOBIND declares three functions tagged @nobind, two of them with the
    names of generated printers and two taking a FILE *. No target binds them,
    and their names do not clash with the generated printers."""
    from tests.test_cparser import NOBIND

    model, _ = parse(NOBIND)
    assert not [e for e in model.entities if isinstance(e, decls.Function)]
    failures = process(
        model, sorted(targets.targets()), tmp_path / "out", include=[tmp_path]
    )
    assert [
        f for f in failures if "toolchain" not in f and "no compiler" not in f
    ] == []
