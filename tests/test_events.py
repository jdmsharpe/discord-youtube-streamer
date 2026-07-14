import asyncio

import pytest

from discord_youtube_streamer.cogs.youtube.events import EventBus


@pytest.mark.asyncio
async def test_event_buses_are_isolated() -> None:
    first_bus = EventBus()
    second_bus = EventBus()
    received: list[str] = []

    async def subscriber(value: str) -> None:
        received.append(value)

    first_bus.subscribe("track", subscriber)
    first_bus.post("track", asyncio.get_running_loop(), "first")
    second_bus.post("track", asyncio.get_running_loop(), "second")
    await asyncio.sleep(0)

    assert received == ["first"]
