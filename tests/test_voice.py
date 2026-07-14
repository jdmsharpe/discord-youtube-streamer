from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_youtube_streamer.cogs.youtube.events import EventBus
from discord_youtube_streamer.cogs.youtube.voice import Voice


def make_voice(after_function=None) -> Voice:
    return Voice(bot=MagicMock(), event_bus=EventBus(), after_function=after_function)


def test_after_passes_finished_track_to_queue_callback() -> None:
    after_function = MagicMock()
    voice = make_voice(after_function=after_function)
    finished = MagicMock()
    voice.cur_audio = finished

    voice.after(None)

    assert voice.cur_audio is None
    voice.bot.loop.call_soon_threadsafe.assert_called_once_with(after_function, False, finished)


@pytest.mark.asyncio
async def test_refresh_failure_advance_is_identity_guarded() -> None:
    after_function = MagicMock()
    voice = make_voice(after_function=after_function)
    voice.client = MagicMock()
    voice.client.is_connected.return_value = True

    audio = MagicMock()
    audio.is_stale.return_value = True
    audio.refresh.return_value = False

    await voice.stream(audio)

    # The advance for the unrefreshable track carries its identity so a
    # concurrent retarget (or a live player's own callback) can't double-skip
    after_function.assert_called_once_with(finished=audio)
    voice.client.play.assert_not_called()


@pytest.mark.asyncio
async def test_cur_audio_is_assigned_only_after_source_swap(monkeypatch) -> None:
    # If the draining player's callback fires mid-retarget, it must capture
    # the OLD track (stale) — cur_audio may not name the new track until the
    # player actually owns its source
    monkeypatch.setattr(Voice, "_get_audio_source", staticmethod(lambda **_kwargs: MagicMock()))
    voice = make_voice(after_function=MagicMock())
    old_audio = MagicMock()
    new_audio = MagicMock()
    new_audio.is_stale.return_value = False
    voice.cur_audio = old_audio

    observed_at_swap = []

    class FakeClient:
        channel = "fake-channel"

        def is_connected(self):
            return True

        def is_playing(self):
            return True

        def is_paused(self):
            return False

        def __setattr__(self, name, value):
            if name == "source":
                observed_at_swap.append(voice.cur_audio)
            object.__setattr__(self, name, value)

    voice.client = FakeClient()

    await voice.stream(new_audio)

    assert observed_at_swap == [old_audio]
    assert voice.cur_audio is new_audio


@pytest.mark.asyncio
async def test_ensure_connected_aborts_cleanly_when_client_disconnected_mid_poll(
    monkeypatch,
) -> None:
    voice = make_voice()
    client = MagicMock()
    client.is_connected.return_value = False
    voice_channel = MagicMock()
    voice_channel.connect = AsyncMock(return_value=client)

    async def sleep_then_disconnect(_delay):
        # /reset during the readiness wait: disconnect_voice() clears the client
        voice.client = None

    monkeypatch.setattr("discord_youtube_streamer.cogs.youtube.voice.sleep", sleep_then_disconnect)

    # Must return instead of raising AttributeError on self.client.is_connected()
    await voice._ensure_connected(voice_channel=voice_channel)

    assert voice.client is None


@pytest.mark.asyncio
async def test_ensure_connected_waits_beyond_old_six_second_bound(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "discord_youtube_streamer.cogs.youtube.voice.sleep", AsyncMock(return_value=None)
    )
    voice = make_voice()
    client = MagicMock()
    # Handshake completes on the 101st poll — past the old 30-poll (6s) bound
    client.is_connected.side_effect = [False] * 101 + [True] * 5
    voice_channel = MagicMock()
    voice_channel.connect = AsyncMock(return_value=client)

    await voice._ensure_connected(voice_channel=voice_channel)

    assert voice.client is client
    assert "did not become ready" not in caplog.text
