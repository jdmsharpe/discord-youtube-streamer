import asyncio
from unittest.mock import MagicMock

import pytest

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


@pytest.mark.asyncio
async def test_queue_remove_and_skip_by_display_position() -> None:
    queue = AudioQueue(
        event_loop=asyncio.get_running_loop(),
        event_bus=EventBus(),
    )
    first = make_audio("first")
    second = make_audio("second")
    third = make_audio("third")

    await queue.append(first)
    await queue.append(second)
    await queue.append(third)

    assert queue.remove_at(1) == "second"
    assert queue.skip_to(1) == "third"
    assert queue.get_current_audio() is third
    assert list(queue.previous_queue) == [first]
