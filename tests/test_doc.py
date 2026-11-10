# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

from yace.ir import doc


def test_brief_description_params_returns():
    parsed = doc.parse(
        """/**
         * Open the thing
         *
         * It opens the thing, which
         * takes a while.
         *
         * @param[in] path Where the thing is,
         *   relative to the cwd
         * @param flags How to open it
         *
         * @return 0 on success
         */"""
    )
    assert parsed.brief == "Open the thing"
    assert parsed.description == "It opens the thing, which takes a while."
    assert parsed.params == {
        "path": "Where the thing is, relative to the cwd",
        "flags": "How to open it",
    }
    assert parsed.returns == "0 on success"


def test_tag_without_text_is_kept():
    parsed = doc.parse("/**\n * Old\n *\n * @deprecated\n * @return zero\n */")
    assert parsed.tags == {"deprecated": ""}
    assert parsed.returns == "zero"


def test_text_after_the_tags_is_description():
    found = doc.parse("/**\n * Brief\n *\n * @param x X\n *\n * More text\n */")
    assert found.params == {"x": "X"}
    assert found.description == "More text"


def test_trailing_and_line_comments():
    assert doc.parse("///< The value").brief == "The value"
    assert doc.parse("/// First\n/// Second").brief == "First Second"


def test_structural_tags_are_dropped():
    parsed = doc.parse("/**\n * A point\n *\n * @struct point\n */")
    assert parsed.brief == "A point"
    assert parsed.tags == {}


def test_brief_tag():
    assert doc.parse("/** @brief Short\n *\n * Long */").brief == "Short"


def test_empty():
    assert doc.parse(None).is_empty()
    assert doc.parse("/** */").is_empty()
