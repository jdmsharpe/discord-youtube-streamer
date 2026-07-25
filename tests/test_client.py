import pytest

from discord_youtube_streamer.cogs.youtube.client import _is_url


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("never gonna give you up", False),
        # Scheme-less: urlsplit sees no scheme and no netloc, so /play treats it
        # as a search query. The replaced urlvalidator rejected it too — this is
        # long-standing behaviour, not a regression.
        ("youtube.com/watch?v=dQw4w9WgXcQ", False),
        # Deliberate narrowing: urlvalidator accepted ftp/ftps, urlsplit-based
        # validation restricts the branch to http/https.
        ("ftp://example.invalid/audio.mp3", False),
        # Deliberate broadening, the other half of the swap: urlvalidator
        # required hostname+TLD/localhost/IP literal, so these fell back to a
        # YouTube search. They are now URLs, and allowed_extractors rejects them
        # downstream — a mistyped URL reports "no results" rather than searching.
        ("https://randomword", True),
        ("http://foo:bar/", True),
        # Bracketed IPv6 is the only input that makes urlsplit itself raise;
        # exercises the except ValueError branch.
        ("http://[::1", False),
    ],
)
def test_is_url_routes_between_direct_extraction_and_search(query: str, expected: bool) -> None:
    assert _is_url(query) is expected
