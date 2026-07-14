# Discord YouTube Streamer

A focused Discord voice bot that streams YouTube audio from a URL, search query, or playlist. It uses slash commands, maintains an interactive now-playing message, and keeps playback isolated per Discord server.

## Features

- Separate queue, voice connection, event bus, and control panel for each configured server
- YouTube search, direct URLs, and background playlist queuing
- Pause/resume, previous/next, seek, skip-to-position, and queue removal controls
- Playback controls restricted to members in the bot's current voice channel
- Blocking `yt-dlp` and network work moved off Discord's event loop
- Automatic refresh of expired YouTube stream URLs
- YouTube-only URL extraction to avoid fetching arbitrary user-provided URLs
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

Python 3.12 and FFmpeg are recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python src/bot.py
```

## Attribution

This project is derived from [Nick McGee's Discord Music Bot](https://github.com/Nick-McGee/discord-bot). Nick McGee created the original Pycord YouTube music bot, queue, voice, and message UI foundation. See [NOTICE.md](NOTICE.md) for the recorded baseline and redistribution note.
