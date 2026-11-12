import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from conftest import FeedServer
from planet.config_source import ConfigError, Source, download, resolve

IMAGE = "[Planet]\nname = Image\nlink = https://p.example/\n\n[https://a.example/feed]\nname = A\n"
REMOTE = (
    "[Planet]\nname = Remote\nlink = https://p.example/\n\n[https://b.example/feed]\nname = B\n"
)
URL = "https://raw.example/config.ini"


@pytest.fixture
def image(tmp_path: Path) -> Path:
    path = tmp_path / "config.ini"
    path.write_text(IMAGE)
    return path


def serving(text: str) -> Callable[[str], str]:
    def fetch(url: str) -> str:
        assert url == URL
        return text

    return fetch


def failing(_url: str) -> str:
    raise OSError("network down")


@pytest.mark.parametrize("url", [None, ""])
def test_no_url_uses_the_image_copy(image: Path, url: str | None) -> None:
    resolved = resolve(url, image, fetch=failing)
    assert resolved.source is Source.IMAGE
    assert resolved.config.settings.name == "Image"


def test_url_config_is_used(image: Path) -> None:
    resolved = resolve(URL, image, fetch=serving(REMOTE))
    assert resolved.source is Source.URL
    assert resolved.config.settings.name == "Remote"
    assert [f.url for f in resolved.config.feeds] == ["https://b.example/feed"]


@pytest.mark.parametrize(
    "text",
    [
        "not an ini file",
        "[https://b.example/feed]\nname = B\n",  # no [Planet]
        "[Planet]\nname = P\n",  # no feeds
        "[Planet]\nfeed_timeout = soon\n\n[https://b.example/feed]\n",  # not an int
        "[Planet]\n\n[https://b.example/feed]\nfilter = (clojure\n",  # bad regex
    ],
)
def test_unusable_config_falls_back_to_the_image(
    image: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        resolved = resolve(URL, image, fetch=serving(text))
    assert resolved.source is Source.FALLBACK
    assert resolved.config.settings.name == "Image"
    assert f"config: {URL} unusable" in caplog.text


def test_download_failure_falls_back_to_the_image(image: Path) -> None:
    resolved = resolve(URL, image, fetch=failing)
    assert resolved.source is Source.FALLBACK
    assert resolved.config.settings.name == "Image"


def test_download(server: FeedServer) -> None:
    assert download(server.url("/atom.xml")).startswith("<?xml")


def test_download_raises_on_http_error(server: FeedServer) -> None:
    with pytest.raises(OSError, match="404"):
        download(server.url("/missing"))


def test_download_rejects_other_schemes(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="http"):
        download((tmp_path / "x").as_uri())


def test_download_rejects_oversized_files(server: FeedServer) -> None:
    with pytest.raises(ConfigError, match="larger than 10 bytes"):
        download(server.url("/atom.xml"), max_bytes=10)
