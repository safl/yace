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
