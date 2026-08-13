import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_youtube_streamer.cogs.youtube.base_view import UserInterface
from discord_youtube_streamer.cogs.youtube.events import EventBus
from discord_youtube_streamer.cogs.youtube.models import Audio, AudioQueue
from discord_youtube_streamer.cogs.youtube.views import StreamerUserInterface


def make_audio(title: str, text_channel) -> Audio:
    audio = Audio(
        author=MagicMock(),
        voice_channel=MagicMock(),
        text_channel=text_channel,
        audio_url=f"https://example.invalid/{title}",
        webpage_url=f"https://youtube.com/watch?v={title}",
        title=title,
        length=120,
        thumbnail="https://example.invalid/thumbnail.jpg",
    )
    audio.set_end_time()
    return audio


def make_ui(event_bus: EventBus) -> StreamerUserInterface:
    voice = MagicMock()
    voice.is_paused.return_value = False
    ui = StreamerUserInterface(
        change_audio_function=MagicMock(),
        queue=AudioQueue(event_loop=asyncio.get_running_loop(), event_bus=event_bus),
        event_bus=event_bus,
        voice=voice,
    )
    # new_ui starts the 2.5s refresher; keep it out of the other tests
    ui.stop_auto_refresh()
    return ui


@pytest.mark.asyncio
async def test_new_audio_event_posts_the_panel_in_the_queuing_channel() -> None:
    """The "new_audio" payload is an Audio, but new_ui takes a channel.

    That mismatch used to be absorbed by overriding new_ui with a widened
    ``Audio | TextChannel`` parameter — which also renamed the parameter and
    broke the base class's ``text_channel=`` keyword. The handler is now a
    separate on_new_audio; this pins the bus wiring that split relies on.
    """
    event_bus = EventBus()
    ui = make_ui(event_bus)
    channel = MagicMock()
    channel.send = AsyncMock(return_value=MagicMock())

    try:
        # Queuing is what raises "new_audio", and it also sets current_audio so
        # the rendered panel reflects the track rather than "Not Playing"
        await ui.queue.append(make_audio("first", channel))
        # the bus schedules the handler as a task; give the loop turns to run it
        for _ in range(5):
            await asyncio.sleep(0)

        channel.send.assert_awaited_once()
        assert channel.send.await_args.kwargs["embed"].title == "first"
    finally:
        ui.stop_auto_refresh()


def test_new_ui_still_accepts_the_base_class_keyword() -> None:
    # A subclass that renames this parameter breaks every super()-style caller
    assert StreamerUserInterface.new_ui is UserInterface.new_ui
