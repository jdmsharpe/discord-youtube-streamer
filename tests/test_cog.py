import asyncio
from unittest.mock import MagicMock

import pytest

from discord_youtube_streamer.cogs.youtube.cog import GuildSession, YouTubeStreamerCog
from discord_youtube_streamer.cogs.youtube.events import EventBus
from discord_youtube_streamer.cogs.youtube.models import Audio, AudioQueue


def make_audio(title: str) -> Audio:
    return Audio(
        author=MagicMock(),
        voice_channel=MagicMock(),
        text_channel=MagicMock(),
        audio_url=f"https://example.invalid/{title}",
        webpage_url=f"https://youtube.com/watch?v={title}",
        title=title,
        length=120,
        thumbnail="https://example.invalid/thumbnail.jpg",
    )


def make_session_with_queue() -> GuildSession:
    # __init__ builds Voice and the control-panel UI, which subscribe to the
    # bus and would react to queue events; the change_audio guard only needs
    # the queue, so build a bare session around one.
    session = GuildSession.__new__(GuildSession)
    session.queue = AudioQueue(event_loop=asyncio.get_running_loop(), event_bus=EventBus())
    return session


def test_cog_raises_when_guild_ids_empty(monkeypatch) -> None:
    monkeypatch.setattr("discord_youtube_streamer.cogs.youtube.cog.GUILD_IDS", [])
    with pytest.raises(RuntimeError, match="GUILD_IDS"):
        YouTubeStreamerCog(bot=MagicMock())


def test_cog_constructs_when_guild_ids_present() -> None:
    cog = YouTubeStreamerCog(bot=MagicMock())
    assert cog.sessions == {}


@pytest.mark.asyncio
async def test_stale_track_end_callback_does_not_advance_queue() -> None:
    session = make_session_with_queue()
    first = make_audio("first")
    second = make_audio("second")
    third = make_audio("third")
    await session.queue.append(first)
    await session.queue.append(second)
    await session.queue.append(third)

    # User skips to "second" while "first" is still draining in the player
    assert session.queue.skip_to(1) == "second"
    assert session.queue.get_current_audio() is second

    # The old player's track-end callback for "first" fires late — it must
    # not advance the queue past the track the user just selected
    session.change_audio(finished=first)
    assert session.queue.get_current_audio() is second

    # The genuine track-end callback for "second" still advances
    session.change_audio(finished=second)
    assert session.queue.get_current_audio() is third


@pytest.mark.asyncio
async def test_change_audio_without_finished_always_advances() -> None:
    session = make_session_with_queue()
    first = make_audio("first")
    second = make_audio("second")
    await session.queue.append(first)
    await session.queue.append(second)

    # UI buttons and commands call change_audio with no finished track and
    # must keep advancing unconditionally
    session.change_audio()
    assert session.queue.get_current_audio() is second
