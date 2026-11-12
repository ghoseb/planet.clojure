import pytest

from planet.repeated_title import drop_repeated_title

TITLE = "Clojure in Google Sheets"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("<h1>Clojure in Google Sheets</h1><p>Body</p>", "<p>Body</p>"),
        ("<h3><a href='x'>Clojure</a> in Google Sheets!</h3><p>Body</p>", "<p>Body</p>"),
        ("Clojure in Google Sheets\n<p>Body</p>", "<p>Body</p>"),
        (
            "<div><article><header><h1>clojure in google sheets</h1></header><p>Body</p>"
            "</article></div>",
            "<div><article><header></header><p>Body</p></article></div>",
        ),
        ("<p>Clojure in Google Sheets &amp;</p><p>Body</p>", "<p>Body</p>"),
    ],
)
def test_repeated_title_is_dropped(content: str, expected: str) -> None:
    assert drop_repeated_title(content, TITLE) == expected


@pytest.mark.parametrize(
    "content",
    [
        "<p>Clojure in Google Sheets is now possible.</p>",  # a sentence, not the title
        "<p>Intro</p><h1>Clojure in Google Sheets</h1>",  # not at the start
        "<table><tr><td>Clojure in Google Sheets</td></tr></table>",
        "<figure><figcaption>Clojure in Google Sheets</figcaption></figure>",
        "",
    ],
)
def test_other_content_is_kept(content: str) -> None:
    assert drop_repeated_title(content, TITLE) == content


def test_empty_title_keeps_content() -> None:
    assert drop_repeated_title("<h1></h1><p>x</p>", "") == "<h1></h1><p>x</p>"
