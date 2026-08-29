import os

import pytest

from discord_youtube_streamer.cogs.youtube.client import YTDL_OPTS, _is_url, _ytdl


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


def test_ytdl_opts_enable_deno_runtime_and_remote_ejs_components() -> None:
    # YoutubeDL keeps (and mutates) the dict it is handed — it adds js_runtimes,
    # http_headers, etc. and turns remote_components into a set — so hand it a
    # copy and compare the resolved params against the pristine constant.
    params = _ytdl(dict(YTDL_OPTS)).params

    # js_runtimes is deliberately absent from YTDL_OPTS: yt-dlp enables deno by
    # default and locates the yt-dlp[deno] binary in the interpreter's scripts
    # dir on its own. Pinning the resolved default means a yt-dlp release that
    # changes it fails here instead of silently falling back to JS-less mode.
    assert params["js_runtimes"] == {"deno": {}}
    # yt-dlp[deno] does not pull in the yt-dlp-ejs package, so this is what lets
    # yt-dlp fetch the challenge-solver lib script that deno executes.
    assert params["remote_components"] == {"ejs:github"}
    for key in ("format", "age_limit", "noplaylist", "allowed_extractors"):
        assert params[key] == YTDL_OPTS[key]


def test_deno_runtime_is_discoverable_by_yt_dlp() -> None:
    deno = pytest.importorskip("deno", reason="yt-dlp[deno] extra is not installed")
    binary = deno.find_deno_bin()
    assert os.access(binary, os.X_OK)

    # Resolve the runtime exactly the way YoutubeDL does at extraction time
    # (interpreter scripts dir first), so this fails if the yt-dlp[deno] binary
    # stops landing where yt-dlp looks or drops below its supported version.
    info = _ytdl(dict(YTDL_OPTS))._js_runtimes["deno"].info
    assert info is not None
    assert info.name == "deno"
    assert info.path == binary
    assert info.supported, f"deno {info.version} is below yt-dlp's minimum supported version"
