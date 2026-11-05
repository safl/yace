import pytest

from yace.ir import decls

RECORD = """
#include <stdint.h>

/** A status */
struct api_status {
	uint16_t code; ///< Status code, see API_STATUS_CODE_*
	uint8_t op;    ///< Opcode, one of API_OP_*
	int8_t sig;    ///< Signed, see API_STATUS_SIG_*
	uint8_t raw[2]; ///< Bytes, see API_STATUS_RAW_*
	uint8_t code_more; ///< Another, see API_STATUS_CODE_MORE_*
};
"""

LINKED = """
/** Kind of status; bits 2:0 of 'code' */
#define API_STATUS_CODE_TYPE 0x7
/** More in the log; bit 15 of 'code' */
#define API_STATUS_CODE_DNR 0x8000
/** Read */
#define API_OP_READ 0x2
"""


def masks_of(model, record="api_status") -> dict:
    found = model.find(record, decls.Struct)
    return {
        f.name: [(m.name, m.define, m.lo, m.width) for m in f.masks]
        for f in found.fields
    }


def bit_masks(diagnostics) -> list:
    return [d.message for d in diagnostics if d.rule == "bit-mask"]


def test_masks_are_linked_to_their_field_by_bit(parse):
    model, diagnostics = parse(RECORD + LINKED)
    assert bit_masks(diagnostics) == []

    masks = masks_of(model)
    assert masks["code"] == [
        ("type", "API_STATUS_CODE_TYPE", 0, 3),
        ("dnr", "API_STATUS_CODE_DNR", 15, 1),
    ]
    assert masks["op"] == [] and masks["sig"] == []
    (field,) = [f for f in model.find("api_status").fields if f.name == "code"]
    assert field.masks[0].value == 0x7 and field.masks[1].value == 0x8000
    assert field.masks[0].doc.brief == "Kind of status; bits 2:0 of 'code'"
    assert model.find("API_STATUS_CODE_TYPE", decls.Define) is not None


def test_masks_are_kept_in_the_stored_ir(parse, tmp_path):
    from yace.ir.model import load

    model, _ = parse(RECORD + LINKED)
    model.save(tmp_path / "api.yaml")
    assert masks_of(load(tmp_path / "api.yaml")) == masks_of(model)


def test_masks_of_a_multi_line_doc_and_a_longer_prefix(parse):
    model, diagnostics = parse(
        RECORD + "/**\n * Phase\n *\n * Flips on each pass; bit 1 of 'code_more'\n */\n"
        "#define API_STATUS_CODE_MORE_PHASE 0x2\n"
    )
    assert bit_masks(diagnostics) == []
    assert masks_of(model)["code_more"] == [
        ("phase", "API_STATUS_CODE_MORE_PHASE", 1, 1)
    ]
    assert masks_of(model)["code"] == []


@pytest.mark.parametrize(
    "define, message",
    [
        (
            "/** Gap; bits 6:4 of 'code' */\n#define API_STATUS_CODE_GAP 0x50\n",
            "'API_STATUS_CODE_GAP' is 0x50, whose bits are not contiguous",
        ),
        (
            "/** Off; bits 5:4 of 'code' */\n#define API_STATUS_CODE_OFF 0x70\n",
            "'API_STATUS_CODE_OFF' is 0x70, bits 6:4 of 'code', but its doc says"
            " 'bits 5:4 of 'code''",
        ),
        (
            "/** One; bits 4 of 'code' */\n#define API_STATUS_CODE_ONE 0x10\n",
            "'API_STATUS_CODE_ONE' is 0x10, bit 4 of 'code', but its doc says"
            " 'bits 4 of 'code''",
        ),
        (
            "/** Wide; bits 16:15 of 'code' */\n#define API_STATUS_CODE_WIDE 0x18000\n",
            "'API_STATUS_CODE_WIDE' is 0x18000, wider than 'api_status.code', of 16"
            " bits",
        ),
        (
            "/** None; bit 0 of 'code' */\n#define API_STATUS_CODE_NONE 0\n",
            "'API_STATUS_CODE_NONE' is 0, which masks no bits",
        ),
        (
            "/** Else; bit 3 of 'op' */\n#define API_STATUS_CODE_ELSE 0x8\n",
            "'API_STATUS_CODE_ELSE' says it is of 'op', but its name puts it under"
            " 'api_status.code'",
        ),
        (
            "/** Orphan; bit 3 of 'op' */\n#define API_OP_ORPHAN 0x8\n",
            "'API_OP_ORPHAN' says it is of 'op', but no field documents its masks as"
            " 'see <PREFIX>_*' with a prefix of the name",
        ),
        (
            "/** Signed; bit 3 of 'sig' */\n#define API_STATUS_SIG_X 0x8\n",
            "'API_STATUS_SIG_X' is of bits of 'api_status.sig', which is not an"
            " unsigned integer",
        ),
        (
            "/** Array; bit 3 of 'raw' */\n#define API_STATUS_RAW_X 0x8\n",
            "'API_STATUS_RAW_X' is of bits of 'api_status.raw', which is not an"
            " unsigned integer",
        ),
        (
            "/** Value; bit 3 of 'code' */\n#define API_STATUS_CODE_VAL 0x8\n",
            "'API_STATUS_CODE_VAL' names the part 'val', which the pretty-printers"
            " print the value of 'code' as",
        ),
        (
            "/** Digit; bit 3 of 'code' */\n#define API_STATUS_CODE_3X 0x8\n",
            "'API_STATUS_CODE_3X' names the part '3x', which is no identifier",
        ),
        (
            "/** Over; bits 3:2 of 'code' */\n#define API_STATUS_CODE_OVER 0xc\n",
            "'API_STATUS_CODE_OVER' overlaps 'API_STATUS_CODE_TYPE' in 'code'",
        ),
        (
            "/** Misspelled; bitz 3 of 'code' */\n#define API_STATUS_CODE_MISS 0x8\n",
            "'API_STATUS_CODE_MISS' is under the masks of 'api_status.code', but its"
            " doc does not end in 'bits <hi>:<lo> of 'code'' or 'bit <n> of"
            " 'code''",
        ),
    ],
)
def test_a_mask_that_does_not_agree_is_reported_and_not_linked(parse, define, message):
    model, diagnostics = parse(RECORD + LINKED + define)
    assert bit_masks(diagnostics) == [message]

    (diag,) = [d for d in diagnostics if d.rule == "bit-mask"]
    assert diag.file == "api.h" and diag.line > 0
    assert [m[0] for m in masks_of(model)["code"]] == ["type", "dnr"]


def test_a_prefix_not_ending_in_the_field_name_is_reported(parse):
    model, diagnostics = parse(
        "#include <stdint.h>\n/** A */\nstruct api_a {\n"
        "\tuint32_t val; ///< Value, see API_A_*\n};\n"
        "/** Size; bits 6:0 of 'val' */\n#define API_A_SIZE 0x7f\n"
    )
    assert bit_masks(diagnostics) == [
        "'API_A_SIZE' is under 'API_A_*', which does not end in the name of"
        " 'api_a.val'"
    ]
    assert masks_of(model, "api_a")["val"] == []


def test_a_prefix_two_fields_name_is_ambiguous(parse):
    model, diagnostics = parse(
        "#include <stdint.h>\n/** A */\nstruct api_a {\n"
        "\tuint8_t flags; ///< Flags, see API_FLAGS_*\n};\n"
        "/** B */\nstruct api_b {\n"
        "\tuint8_t flags; ///< Flags, see API_FLAGS_*\n};\n"
        "/** On; bit 0 of 'flags' */\n#define API_FLAGS_ON 0x1\n"
    )
    assert bit_masks(diagnostics) == [
        "'API_FLAGS_ON' is under the masks of each of 'api_a.flags', 'api_b.flags'"
    ]
    assert masks_of(model, "api_a")["flags"] == []


def test_a_part_read_as_another_field_is_reported(parse):
    model, diagnostics = parse(
        "#include <stdint.h>\n/** A */\nstruct api_a {\n"
        "\tuint8_t mode; ///< Mode, see API_A_MODE_*\n"
        "\tuint8_t mode_fast; ///< Fast\n};\n"
        "/** Fast; bit 0 of 'mode' */\n#define API_A_MODE_FAST 0x1\n"
        "/** Slow; bit 1 of 'mode' */\n#define API_A_MODE_SLOW 0x2\n"
    )
    assert bit_masks(diagnostics) == [
        "'API_A_MODE_FAST' is read as 'mode_fast', which 'api_a' has already"
    ]
    assert masks_of(model, "api_a")["mode"] == [("slow", "API_A_MODE_SLOW", 1, 1)]


def test_constants_of_the_values_of_a_field_are_no_masks(parse):
    """A field naming the constants of its values, and none says which bits it
    is, has no masks, and is not reported"""

    _, diagnostics = parse(
        "#include <stdint.h>\n/** A */\nstruct api_a {\n"
        "\tuint8_t opc; ///< Opcode, see API_A_OPC_*\n};\n"
        "/** Read */\n#define API_A_OPC_READ 0x2\n"
        "/** Write */\n#define API_A_OPC_WRITE 0x1\n"
    )
    assert bit_masks(diagnostics) == []
