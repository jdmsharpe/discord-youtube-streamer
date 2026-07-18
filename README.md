# Discord YouTube Streamer

![Hits](https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2Fjdmsharpe%2Fdiscord-youtube-streamer%2F&label=discord-youtube-streamer&icon=github&color=%23198754&message=&style=flat&tz=UTC)
[![Version](https://img.shields.io/github/v/tag/jdmsharpe/discord-youtube-streamer?sort=semver&label=version)](https://github.com/jdmsharpe/discord-youtube-streamer/tags)
[![License](https://img.shields.io/github/license/jdmsharpe/discord-youtube-streamer?label=license)](./LICENSE)
[![CI](https://github.com/jdmsharpe/discord-youtube-streamer/actions/workflows/main.yml/badge.svg)](https://github.com/jdmsharpe/discord-youtube-streamer/actions/workflows/main.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/jsgreen152/discord-youtube-streamer?logo=docker&logoColor=white)](https://hub.docker.com/r/jsgreen152/discord-youtube-streamer)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)

## Overview

A focused Discord voice bot and reusable Pycord cog that streams YouTube audio from a URL, search query, or playlist. It uses slash commands, maintains an interactive now-playing message, and keeps playback isolated per Discord server.

## Features

- Separate queue, voice connection, event bus, and control panel for each configured server
- YouTube search, direct URLs, and background playlist queuing
- Pause/resume, previous/next, seek, skip-to-position, and queue removal controls
- Playback controls restricted to members in the bot's current voice channel
- Blocking `yt-dlp` and network work moved off Discord's event loop
- Automatic refresh of expired YouTube stream URLs
- YouTube-only URL extraction to avoid fetching arbitrary user-provided URLs
- Installable `discord_youtube_streamer` package with a public cog interface
- Docker and local Python workflows

## Commands

| Command | Description |
| --- | --- |
| `/play` | Queue a YouTube URL or search result |
| `/play_next` | Insert a YouTube URL or search result at the front of the queue |
| `/playlist` | Queue all entries from a YouTube playlist |
| `/pause` / `/resume` | Pause or resume playback |
| `/remove_at` | Remove an upcoming item by its displayed position |
| `/skip_to` | Jump to an upcoming item by its displayed position |
| `/restart_queue` | Replay the current and previous queue |
| `/go_to` | Seek to an hour, minute, and second offset |
| `/clear_queue` | Clear upcoming items and cancel active playlist queuing |
| `/clear_previous_queue` | Clear playback history |
| `/remove` | Remove the current item and advance |
| `/reset` | Reset the queue, voice client, and control panel |
| `/reconnect_bot` | Reconnect voice and recreate the control panel |

## Discord setup

1. Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Invite it with the `bot` and `applications.commands` scopes.
3. Grant it permission to view channels, send messages, embed links, connect, and speak.
4. Copy `.env.example` to `.env`, then set `BOT_TOKEN` and the comma-separated `GUILD_IDS` where commands should be registered.

Do not commit `.env`; it is ignored by Git and Docker.

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

## Run from source

Python 3.11 or newer and FFmpeg are required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
discord-youtube-streamer
```

The module entry point is equivalent:

```bash
python -m discord_youtube_streamer
```

## Use as a cog

Install the package, then add its public cog to an existing Pycord bot:

```python
from discord_youtube_streamer import YouTubeStreamerCog

bot.add_cog(YouTubeStreamerCog(bot))
```

`GUILD_IDS` must be set in the host process environment (or its `.env`) **before importing** the package — the slash commands bind to it at import time, and the cog raises `RuntimeError` at construction if it is empty.

## Development

```bash
uv sync --extra dev
uv run ruff check src/ tests/
uv run pyright src/
uv run pytest -q
```

*Run `git config core.hooksPath .githooks` after cloning to enable the pre-commit hook.*

## Attribution

This project is derived from [Nick McGee's Discord Music Bot](https://github.com/Nick-McGee/discord-bot). Nick McGee created the original Pycord YouTube music bot, queue, voice, and message UI foundation. The extraction baseline is upstream commit `4917444` ("Update requirements", 2023-09-23).
