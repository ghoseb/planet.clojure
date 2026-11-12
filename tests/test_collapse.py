from planet.collapse import COLLAPSE_OVER_WORDS, split


def para(words: int, word: str = "word") -> str:
    return f"<p>{' '.join([word] * words)}</p>"


def test_short_entries_are_whole() -> None:
    html = para(100) * 3
    assert split(html).more is None


def test_long_entries_cut_after_the_block_reaching_the_visible_words() -> None:
    parts = split(para(100) * 6)
    assert parts.visible == para(100) * 2
    assert parts.more == para(100) * 4


def test_a_single_wrapper_div_is_looked_into() -> None:
    parts = split(f"<div>{para(100) * 6}</div>")
    assert parts.visible == para(100) * 2


def test_a_long_first_block_is_shown_whole() -> None:
    parts = split(para(500) + para(150))
    assert parts.visible == para(500)
    assert parts.more == para(150)


def test_no_read_more_for_a_short_rest() -> None:
    assert split(para(COLLAPSE_OVER_WORDS) + para(30)).more is None


def test_never_cuts_inside_code_or_loose_text() -> None:
    code = "<pre>" + "x " * 600 + "</pre>"
    assert split(code).more is None
    assert split("word " * 600).more is None
    parts = split(para(160) + code)
    assert parts.visible == para(160)
    assert parts.more is not None and parts.more.startswith("<pre>")
