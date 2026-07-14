# Discord YouTube Streamer - Developer Reference

## Quick Start

```bash
uv sync --extra dev                   # creates .venv from uv.lock (no pip inside — use `uv pip` if needed)
cp .env.example .env                  # then fill in required values
git config core.hooksPath .githooks   # enable repo pre-commit hook
uv run discord-youtube-streamer       # or: python -m discord_youtube_streamer, or: docker compose up --build
```

## Gotchas

- Uses **`py-cord`** (not `discord.py`). The slash-command API differs; don't mix docs between the two.
- **`GUILD_IDS` is a hard requirement here** — unlike the sibling bots, `validate_required_config()` raises `RuntimeError` when it parses to an empty list; there is no global-registration fallback. It is also captured at import time by the slash-command decorators in `cogs/youtube/cog.py`.
- `config/auth.py` calls `load_dotenv()` at import time. Tests that control env state must monkeypatch (`monkeypatch.setattr("dotenv.load_dotenv", lambda *_, **__: None)` if a stray `.env` could interfere).
- FFmpeg and libopus are **runtime-only** dependencies (playback). Imports and the test suite need neither — py-cord binds natives lazily at playback time.
- **Attribution:** derived from Nick McGee's Discord Music Bot (upstream baseline commit `4917444`, recorded in README Attribution). MIT-licensed since 2026-07 per John's public-distribution decision; keep the Attribution section intact when editing the README.
- py-cord 2.8.0 caps at Python `<3.15`; do not extend the CI matrix past 3.14.

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `BOT_TOKEN` | Yes | Discord bot token |
| `GUILD_IDS` | Yes | Comma-separated Discord server IDs (empty is a startup error) |

## Supported Entry Points

- Console script: `discord-youtube-streamer` (= `discord_youtube_streamer.bot:main`); `python -m discord_youtube_streamer` is equivalent. There is no repo-root `src/bot.py` launcher.
- Cog composition contract:

  ```python
  from discord_youtube_streamer import YouTubeStreamerCog

  bot.add_cog(YouTubeStreamerCog(bot))
  ```

## Package Layout

```text
src/
└── discord_youtube_streamer/
    ├── __init__.py                  # lazy public exports (AudioStreamer = YouTubeStreamerCog)
    ├── __main__.py
    ├── bot.py                       # build_bot() + main()
    ├── logging_setup.py
    ├── config/
    │   ├── __init__.py
    │   ├── auth.py                  # load_dotenv at import; BOT_TOKEN / GUILD_IDS parsing + validation
    │   └── settings.py              # FFMPEG_OPTS, DELETE_TIMER constants (no env vars)
    └── cogs/
        ├── __init__.py
        └── youtube/
            ├── __init__.py
            ├── base_view.py
            ├── client.py            # yt-dlp extraction (YouTube-only URL validation)
            ├── cog.py               # slash commands, per-guild sessions
            ├── events.py            # EventBus
            ├── models.py            # Audio, AudioQueue (remove_at / skip_to semantics)
            ├── views.py
            └── voice.py             # playback, stale-URL refresh, after-callbacks
```

## Testing And Patch Targets

- `pytest` runs with `pythonpath = ["src"]`; suite needs no network, ffmpeg, opus, or real tokens.
- Module-aligned files: `tests/test_auth.py` (guild-id parsing + required-config validation), `tests/test_bot.py` (build_bot registers the cog), `tests/test_events.py` (EventBus isolation), `tests/test_models.py` (AudioQueue display-position semantics), `tests/test_package.py` (lazy export smoke test).
- Env state via `pytest` `monkeypatch`; Discord objects via `unittest.mock.MagicMock`.
- New tests and patches should target real owners under `discord_youtube_streamer...`.

## Validation Commands

```bash
ruff check src/ tests/
ruff format src/ tests/
pyright src/
pytest -q
```

- The repo pre-commit hook (`.githooks/pre-commit`) runs `ruff format` (auto-applied + re-staged), then `ruff check` (blocking), then `pyright` and `pytest --collect-only` as warning-only smoke tests. Resolves tools from `.venv/bin` or `.venv/Scripts` first, then `PATH`.

## Runtime Conventions

- Per-guild isolation: each configured guild gets its own queue, voice connection, event bus, and control-panel message.
- Blocking `yt-dlp` and network work runs off the Discord event loop (`asyncio.to_thread`); enforced by ruff `ASYNC` rules.
- Expired YouTube stream URLs are refreshed automatically in `voice.py` before playback resumes.
- `client.py` restricts extraction to YouTube URLs to avoid fetching arbitrary user-provided URLs.
