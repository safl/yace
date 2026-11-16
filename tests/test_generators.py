# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

from importlib.metadata import EntryPoint

import pytest

import yace.generators
from yace.cli import yace as cli
from yace.generators import Generated, Generator

HEADER = """#include <stdint.h>

/** A command of a toy specification */
struct toy_cmd {
	uint32_t cdw0; ///< Command dword 0, see TOY_CMD_CDW0_*
};

/** Opcode; bits 7:0 of 'cdw0' */
#define TOY_CMD_CDW0_OPC 0xff
/** Command identifier; bits 31:16 of 'cdw0' */
#define TOY_CMD_CDW0_CID 0xffff0000

/**
 * Make 'cmd' a command of 'opcode'
 *
 * @param cmd The command to make
 * @param opcode Its opcode
 */
void
toy_cmd_init(struct toy_cmd *cmd, uint8_t opcode);
"""


class Toy(Generator):
    """A generator that writes the header of a toy specification to
    '<name>.h', where 'name' is the generator option of that name, and a
    source to 'toy.c'"""

    NAME = "toy"

    def generate(self) -> Generated:
        header = self.output / f"{self.options.get('name', 'toy')}.h"
        header.write_text(HEADER)
        source = self.output / "toy.c"
        source.write_text('#include "toy.h"\n')
        return Generated(headers=[header], sources=[source])


@pytest.fixture
def toy(monkeypatch):
    """Install Toy as the only generator, under the entry point 'toy'"""

    found = [
        EntryPoint(
            name="toy", value="tests.test_generators:Toy", group="yace.generators"
        )
    ]
    monkeypatch.setattr(yace.generators, "entry_points", lambda group: found)


def run(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["yace", *map(str, args)])
    return cli.main()


def test_a_generated_header_is_parsed_as_a_header_written_by_hand(
    toy, monkeypatch, tmp_path
):
    assert run(monkeypatch, "--generate", "toy", "--output", tmp_path) == 0

    assert (tmp_path / "toy" / "toy.h").exists()
    assert (tmp_path / "toy" / "toy.c").exists()
    ir = (tmp_path / "toy.yaml").read_text()
    assert "toy_cmd_init" in ir
    assert "TOY_CMD_CDW0_OPC" in ir


def test_a_generator_option_reaches_its_generator(toy, monkeypatch, tmp_path):
    args = ["--generate", "toy", "--generator-option", "toy.name=spec"]
    assert run(monkeypatch, *args, "--output", tmp_path) == 0
    assert (tmp_path / "toy" / "spec.h").exists()
    assert (tmp_path / "spec.yaml").exists()


def test_the_targets_emit_and_check_what_a_generator_wrote(toy, monkeypatch, tmp_path):
    args = ["--generate", "toy", "--emit", "capi", "--output", tmp_path]
    assert run(monkeypatch, *args) == 0
    assert list((tmp_path / "capi").glob("*.h"))


def test_an_unknown_generator_or_a_wrong_generator_option_fails_the_run(
    toy, monkeypatch, tmp_path
):
    assert run(monkeypatch, "--generate", "nothing", "--output", tmp_path) == 1
    args = ["--generate", "toy", "--generator-option", "other.name=x"]
    assert run(monkeypatch, *args, "--output", tmp_path) == 1
    args = ["--generate", "toy", "--generator-option", "toy.name"]
    assert run(monkeypatch, *args, "--output", tmp_path) == 1


def test_options_are_grouped_by_generator():
    assert yace.generators.options_of(["a.x=1", "a.y=2", "b.x=3"]) == {
        "a": {"x": "1", "y": "2"},
        "b": {"x": "3"},
    }


def test_the_error_for_a_malformed_option_names_the_kind_of_option():
    with pytest.raises(ValueError, match="target option 't.k' is not <target>"):
        yace.generators.options_of(["t.k"], "target")


def test_a_generator_is_loaded_from_its_file_or_module_without_installing_it(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(yace.generators, "entry_points", lambda group: [])
    source = tmp_path / "toolbox" / "gen.py"
    source.parent.mkdir()
    source.write_text(
        "from tests.test_generators import Toy\n\nclass Spec(Toy):\n    pass\n"
    )
    args = ["--generate", f"{source}:Spec", "--generator-option", "toy.name=spec"]
    assert run(monkeypatch, *args, "--output", tmp_path / "out") == 0
    assert (tmp_path / "out" / "toy" / "spec.h").exists()

    assert yace.generators.load("tests.test_generators:Toy") is Toy
    for missing in (f"{tmp_path}/none.py:Spec", f"{source}:None", "nomodule:X"):
        with pytest.raises(KeyError):
            yace.generators.load(missing)
