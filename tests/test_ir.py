# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import pydantic
import pytest

from yace.ir import decls, model, types


def make():
    return model.Model(
        meta=model.Meta(name="api", prefix="api"),
        entities=[
            decls.Struct(
                name="s",
                fields=[
                    decls.Field(
                        name="data",
                        typ=types.Array(of=types.Builtin(name="uint8_t"), length=None),
                    )
                ],
            ),
            decls.Union(name="u", fields=[]),
            decls.Define(name="X", value=decls.IntLiteral(value=16, base=16)),
            decls.Function(
                name="f",
                ret=types.Builtin(name="void"),
                params=[
                    decls.Param(
                        name="cb",
                        typ=types.Pointer(
                            to=types.FunctionType(
                                ret=types.Builtin(name="int"),
                                params=[
                                    types.TypeParam(
                                        name="arg", typ=types.Builtin(name="int")
                                    )
                                ],
                            )
                        ),
                    )
                ],
            ),
        ],
    )


def test_roundtrip_keeps_the_kinds(tmp_path):
    original = make()
    original.save(tmp_path / "api.yaml")
    loaded = model.load(tmp_path / "api.yaml")

    assert loaded == original
    assert [type(e) for e in loaded.entities] == [
        decls.Struct,
        decls.Union,
        decls.Define,
        decls.Function,
    ]
    assert loaded.entities[0].fields[0].typ.length is None


def test_entities_from_dicts_by_key():
    data = make().model_dump(mode="json")
    assert [type(e) for e in model.Model.model_validate(data).entities][:2] == [
        decls.Struct,
        decls.Union,
    ]


def test_unknown_attributes_are_rejected():
    with pytest.raises(pydantic.ValidationError):
        types.Builtin(name="int", signed=True)
    with pytest.raises(pydantic.ValidationError):
        types.Builtin(name="__int128")


def test_schema_describes_the_entities():
    schema = model.schema()
    assert {"Struct", "Union", "Function", "Typedef", "Define", "Enum"} <= set(
        schema["$defs"]
    )
