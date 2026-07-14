import logging

from requests import head
from requests.exceptions import RequestException
from yt_dlp import YoutubeDL as yt
from yt_dlp import DownloadError
from urlvalidator import validate_url, ValidationError

import config.logger

# allowed_extractors keeps yt-dlp's generic extractor out of reach: without it,
# any http(s) URL passed to /play is fetched server-side (SSRF against localhost
# services) and response fragments leak into the "Queued" embed.
YTDL_OPTS = {'format': 'bestaudio/best',
             'age_limit': 21,
             'noplaylist': True,
             'allowed_extractors': ['youtube', 'youtube:tab', 'youtube:search', 'youtube:playlist'],
             'remote_components': ['ejs:github']}

REQUEST_TIMEOUT_S = 10


def get_audio(query: str) -> dict | None:
    entry = _get_entry_from_youtube(query=query)
    if not entry:
        return None

    if entry.get('is_live'):
        logging.error('Unable to queue livestream: %s', entry.get('title'))
        return None
    if entry.get('duration') is None:
        logging.error('Unable to queue audio with unknown duration: %s', entry.get('title'))
        return None

    try:
        return {'audio_url': entry['url'],
                'webpage_url': entry['webpage_url'],
                'title': entry['title'],
                'length': entry['duration'],
                'thumbnail': entry['thumbnail']
        }
    except KeyError as key_error:
        logging.error('Entry missing expected key: %s', key_error)
        return None


def get_playlist(playlist_url: str) -> dict | None:
    """Fetch a playlist's title and entry URLs in a single flat extraction.

    Returns {'title': str, 'urls': list[str]} or None. Blocking — run in an
    executor from async code.
    """
    opts = YTDL_OPTS | {'noplaylist': False, 'extract_flat': 'in_playlist'}
    with yt(opts) as ytdl:
        try:
            info = ytdl.extract_info(playlist_url, download=False)
        except DownloadError as download_error:
            logging.error('Error fetching playlist %s: %s', playlist_url, download_error)
            return None

    entries = (info or {}).get('entries') or []
    urls = [entry['url'] for entry in entries if entry and entry.get('url')]
    if not urls:
        logging.error('No entries found in playlist %s', playlist_url)
        return None

    return {'title': info.get('title') or 'Playlist', 'urls': urls}


def _get_entry_from_youtube(query: str) -> dict | None:
    tries = 3

    while tries > 0:
        tries -= 1
        with yt(YTDL_OPTS) as ytdl:
            try:
                if _is_url(query):
                    logging.info('Queuing by URL')
                    return ytdl.extract_info(query, download=False)

                logging.info('Queuing by search')
                info = ytdl.extract_info(f'ytsearch:{query}', download=False)
                first_entry = info['entries'][0]
                status_code = head(first_entry['url'], timeout=REQUEST_TIMEOUT_S).status_code
                logging.info('Query status code: %s', status_code)
                if status_code == 200:
                    return first_entry
                logging.warning('Stream URL returned %s, retrying', status_code)

            except (TypeError, IndexError, KeyError) as bad_entry:
                # Deterministic — retrying returns the same malformed entry
                logging.error('No usable entry found: %s', bad_entry)
                return None
            except RequestException as connection_error:
                logging.error('Unable to connect: %s', connection_error)
            except DownloadError as download_error:
                logging.error('Error downloading: %s', download_error)

    return None


def _is_url(query: str) -> bool:
    try:
        validate_url(query)
        logging.debug('%s is a URL', query)
        return True
    except ValidationError:
        logging.debug('%s not a URL', query)
        return False
