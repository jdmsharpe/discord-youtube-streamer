import logging
from typing import Any, cast
from urllib.parse import urlsplit

from requests import head
from requests.exceptions import RequestException
from yt_dlp import YoutubeDL as yt

# yt_dlp re-exports DownloadError at package level but omits it from __all__,
# so it is not a typed public symbol there; yt_dlp.utils is where it is defined.
from yt_dlp.utils import DownloadError

# allowed_extractors keeps yt-dlp's generic extractor out of reach: without it,
# any http(s) URL passed to /play is fetched server-side (SSRF against localhost
# services) and response fragments leak into the "Queued" embed.
YTDL_OPTS = {
    "format": "bestaudio/best",
    "age_limit": 21,
    "noplaylist": True,
    "allowed_extractors": ["youtube", "youtube:tab", "youtube:search", "youtube:playlist"],
    "remote_components": ["ejs:github"],
}

REQUEST_TIMEOUT_S = 10


# Two shims for yt-dlp's inline type hints, which are narrower than its runtime
# contract. YoutubeDL.params is the private _Params TypedDict, which no options
# dict literal can satisfy, and extract_info is declared to return the private
# _InfoDict TypedDict — not assignable to dict, and it reports every optional
# key as possibly-missing even though the callers below already guard for that.
# Both are documented by yt-dlp as plain option/info dictionaries, so convert
# once here rather than threading private yt-dlp type names through the module.
def _ytdl(opts: dict[str, Any]) -> yt:
    return yt(cast("Any", opts))


def _extract(ytdl: yt, query: str) -> dict[str, Any] | None:
    return cast("dict[str, Any] | None", ytdl.extract_info(query, download=False))


# Replaces the unmaintained urlvalidator dependency (single release, 2017). The
# behaviour differs in BOTH directions, deliberately:
#   narrower on scheme — urlvalidator allowed ftp/ftps too, so "ftp://x.com/a"
#     was a URL and is now treated as a search query;
#   broader on host shape — urlvalidator required hostname+TLD, "localhost", or
#     an IP literal, so "https://randomword" and "http://foo:bar/" were rejected
#     and fell back to a YouTube search. They now count as URLs and go to
#     extract_info, where allowed_extractors rejects them, so a mistyped URL
#     surfaces "no results" instead of silently becoming a search.
# Neither direction is a security control — allowed_extractors above is what
# stops arbitrary URLs being fetched.
URL_SCHEMES = frozenset({"http", "https"})


def get_audio(query: str) -> dict[str, Any] | None:
    entry = _get_entry_from_youtube(query=query)
    if not entry:
        return None

    if entry.get("is_live"):
        logging.error("Unable to queue livestream: %s", entry.get("title"))
        return None
    if entry.get("duration") is None:
        logging.error("Unable to queue audio with unknown duration: %s", entry.get("title"))
        return None

    try:
        return {
            "audio_url": entry["url"],
            "webpage_url": entry["webpage_url"],
            "title": entry["title"],
            "length": entry["duration"],
            "thumbnail": entry["thumbnail"],
        }
    except KeyError as key_error:
        logging.error("Entry missing expected key: %s", key_error)
        return None


def get_playlist(playlist_url: str) -> dict[str, Any] | None:
    """Fetch a playlist's title and entry URLs in a single flat extraction.

    Returns {'title': str, 'urls': list[str]} or None. Blocking — run in an
    executor from async code.
    """
    opts = YTDL_OPTS | {"noplaylist": False, "extract_flat": "in_playlist"}
    with _ytdl(opts) as ytdl:
        try:
            info = _extract(ytdl, playlist_url)
        except DownloadError as download_error:
            logging.error("Error fetching playlist %s: %s", playlist_url, download_error)
            return None

    if info is None:
        logging.error("No playlist info returned for %s", playlist_url)
        return None

    entries = info.get("entries") or []
    urls = [entry["url"] for entry in entries if entry and entry.get("url")]
    if not urls:
        logging.error("No entries found in playlist %s", playlist_url)
        return None

    return {"title": info.get("title") or "Playlist", "urls": urls}


def _get_entry_from_youtube(query: str) -> dict[str, Any] | None:
    tries = 3

    while tries > 0:
        tries -= 1
        with _ytdl(YTDL_OPTS) as ytdl:
            try:
                if _is_url(query):
                    logging.info("Queuing by URL")
                    return _extract(ytdl, query)

                logging.info("Queuing by search")
                info = _extract(ytdl, f"ytsearch:{query}")
                if info is None:
                    # Previously reached the same return via a TypeError on
                    # None["entries"] caught below; make the path explicit
                    logging.error("No search results returned for %s", query)
                    return None
                first_entry = info["entries"][0]
                status_code = head(first_entry["url"], timeout=REQUEST_TIMEOUT_S).status_code
                logging.info("Query status code: %s", status_code)
                if status_code == 200:
                    return first_entry
                logging.warning("Stream URL returned %s, retrying", status_code)

            except (TypeError, IndexError, KeyError) as bad_entry:
                # Deterministic — retrying returns the same malformed entry
                logging.error("No usable entry found: %s", bad_entry)
                return None
            except RequestException as connection_error:
                logging.error("Unable to connect: %s", connection_error)
            except DownloadError as download_error:
                logging.error("Error downloading: %s", download_error)

    return None


def _is_url(query: str) -> bool:
    try:
        parts = urlsplit(query)
    except ValueError:
        # Only an unparseable bracketed IPv6 literal reaches here; urlsplit does
        # not validate ports (SplitResult.port would, but is never accessed).
        logging.debug("%s not a URL", query)
        return False

    if parts.scheme in URL_SCHEMES and parts.netloc:
        logging.debug("%s is a URL", query)
        return True

    logging.debug("%s not a URL", query)
    return False
