# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

from yace.ir import doc


def test_the_brief_description_params_and_returns_are_parsed():
    parsed = doc.parse("""/**
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
         */""")
    assert parsed.brief == "Open the thing"
    assert parsed.description == "It opens the thing, which takes a while."
    assert parsed.params == {
        "path": "Where the thing is, relative to the cwd",
        "flags": "How to open it",
    }
    assert parsed.returns == "0 on success"


def test_an_item_of_a_list_is_a_line_of_its_own():
    parsed = doc.parse("""/**
         * Reap
         *
         * Three errors, after which
         * it is called again:
         *
         * - -EINTR: a signal interrupted
         *   the call
         * - -EAGAIN: no resources
         * 1. first
         * -# second
         * -EBUSY continues the item, not starting one
         *
         * @param[out] n One of:
         * - zero
         * - more
         */""")
    assert parsed.description == (
        "Three errors, after which it is called again:\n\n"
        "- -EINTR: a signal interrupted the call\n"
        "- -EAGAIN: no resources\n"
        "1. first\n"
        "-# second -EBUSY continues the item, not starting one"
    )
    assert parsed.params == {"n": "One of: - zero - more"}


def test_a_tag_without_text_is_kept():
    parsed = doc.parse("/**\n * Old\n *\n * @deprecated\n * @return zero\n */")
    assert parsed.tags == {"deprecated": ""}
    assert parsed.returns == "zero"


def test_text_after_the_tags_is_part_of_the_description():
    found = doc.parse("/**\n * Brief\n *\n * @param x X\n *\n * More text\n */")
    assert found.params == {"x": "X"}
    assert found.description == "More text"


def test_trailing_and_line_comments_give_a_brief():
    assert doc.parse("///< The value").brief == "The value"
    assert doc.parse("/// First\n/// Second").brief == "First Second"


def test_structural_tags_are_dropped():
    parsed = doc.parse("/**\n * A point\n *\n * @struct point\n */")
    assert parsed.brief == "A point"
    assert parsed.tags == {}


def test_the_brief_tag_gives_the_brief():
    assert doc.parse("/** @brief Short\n *\n * Long */").brief == "Short"


def test_no_doc_and_an_empty_doc_comment_are_empty():
    assert doc.parse(None).is_empty()
    assert doc.parse("/** */").is_empty()


def test_prose_is_the_note_see_and_deprecation_in_that_order():
    parsed = doc.parse(
        "/**\n * Old\n *\n * @deprecated\n * @see api_new()\n"
        " * @note Not thread-safe\n * @todo Ours\n */"
    )
    assert parsed.prose() == [
        "Note: Not thread-safe",
        "See also: api_new()",
        "Deprecated",
    ]


def test_a_repeated_tag_keeps_its_sentences_and_lists_its_references():
    parsed = doc.parse(
        "/**\n * Get\n *\n * @note Return it with put()\n * @note Not thread-safe\n"
        " * @note Fast.\n * @note Simple\n * @see put()\n * @see reap()\n"
        " * @nullable a\n * @nullable b\n */"
    )
    assert parsed.tags == {
        "note": "Return it with put(). Not thread-safe. Fast. Simple",
        "see": "put(), reap()",
        "nullable": "a b",
    }
