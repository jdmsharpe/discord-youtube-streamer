import logging
from asyncio import sleep, to_thread
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta

from discord import Bot, FFmpegPCMAudio, PCMVolumeTransformer, utils
from discord.channel import VocalGuildChannel
from discord.errors import ClientException
from discord.opus import OpusNotLoaded

# discord.VoiceClient is a deprecated alias since py-cord 2.7 (removed in 3.0);
# discord.voice is the supported path. This is also the concrete class that
# channel.connect() instantiates when cls is left at its MISSING default —
# discord.VoiceProtocol, the annotated return type, is the abstract base and
# defines none of play/pause/resume/source.
from discord.voice import VoiceClient

from ...config.settings import FFMPEG_OPTS
from .events import EventBus
from .models import Audio


class Voice:
    __slots__ = "after_function", "bot", "client", "cur_audio", "paused_time_left"

    def __init__(self, bot: Bot, event_bus: EventBus, after_function: Callable | None = None):
        self.bot = bot
        self.after_function = after_function
        self.client: VoiceClient | None = None
        self.cur_audio: Audio | None = None
        self.paused_time_left: timedelta | None = None
        event_bus.subscribe(event_type="new_audio", function=self.stream)
        event_bus.subscribe(event_type="no_audio", function=self.disconnect_voice)

    async def join_voice(self, voice_channel: VocalGuildChannel) -> None:
        try:
            # Capture the returned client: bot.voice_clients[0] would grab an
            # arbitrary guild's session once more than one guild is connected.
            # cls is passed explicitly only to pin the return type — VoiceClient
            # is exactly what connect() substitutes for its MISSING default.
            self.client = await voice_channel.connect(cls=VoiceClient)
            logging.debug("Connected to new voice channel: %s", voice_channel)
        except ClientException:
            # Already connected in this guild — reuse that client and move it.
            # bot.voice_clients is list[VoiceProtocol]; anything that is not a
            # full VoiceClient cannot drive playback, so treat it as unusable.
            existing = utils.get(self.bot.voice_clients, guild=voice_channel.guild)
            if isinstance(existing, VoiceClient):
                self.client = existing
                await existing.move_to(voice_channel)
                logging.debug("Moved to new voice channel: %s", voice_channel)
            else:
                logging.warning(
                    "Already connected but no voice client available for guild: %s",
                    voice_channel.guild,
                )

    async def _ensure_connected(self, voice_channel: VocalGuildChannel) -> None:
        """Join voice and wait until the connection is fully established."""
        await self.join_voice(voice_channel=voice_channel)
        if self.client and not self.client.is_connected():
            logging.debug("Waiting for voice connection to be ready...")
            # Bound matches py-cord's 60s connect timeout: giving up sooner
            # strands current_audio with no player on a slow voice handshake
            for _ in range(300):
                await sleep(0.2)
                if self.client is None:
                    # /reset or queue drain disconnected voice while we slept;
                    # playback is moot and self.client.is_connected() would raise
                    logging.debug("Voice client went away while waiting for connection")
                    return
                if self.client.is_connected():
                    break
            # None-safe helper: no await separates loop exit from this check
            # today, but don't let a future yield point turn a mid-wait
            # disconnect into an AttributeError here
            if not self.is_connected():
                logging.error("Voice connection did not become ready in time")

    async def check_voice(self, voice_channel: VocalGuildChannel):
        if self.client and self.client.is_connected():
            logging.debug("Remaining in current channel: %s", self.client.channel)
        else:
            await self._ensure_connected(voice_channel=voice_channel)

    async def stream(self, audio: Audio) -> None:
        await self.check_voice(voice_channel=audio.voice_channel)
        if not self.is_connected():
            logging.error("Cannot stream audio: voice client not connected")
            return

        # Network probes run off-loop: a stalled HEAD request or yt-dlp
        # re-extraction here would freeze gateway/voice heartbeats.
        if await to_thread(audio.is_stale):
            logging.info("Stream URL stale, refreshing: %s", audio.title)
            if not await to_thread(audio.refresh):
                logging.error("Unable to refresh %s, skipping to next audio", audio.title)
                if self.after_function:
                    # Identity-guarded: only advances if this dead track is
                    # still the queue's current — a running player's own
                    # track-end callback must not advance a second time.
                    self.after_function(finished=audio)
                return

        audio_source = self._get_audio_source(audio=audio)

        # Bind once rather than re-reading self.client per branch: the staleness
        # probe and refresh above are awaits, so /reset or a queue drain can
        # clear self.client between the is_connected() check and here, and every
        # branch below must act on the same client instance.
        client = self.client
        if client is None:
            logging.error("Cannot stream audio: voice client went away before playback")
            return

        if client.is_playing() or client.is_paused():
            # A paused player still owns the stream — swap the source and
            # resume rather than calling play(), which would spawn a second
            # player thread on top of the paused one
            client.source = audio_source
            if client.is_paused():
                self.paused_time_left = None
                client.resume()
        else:
            try:
                client.play(source=audio_source, after=self.after)
            except (TypeError, AttributeError, ClientException, OpusNotLoaded) as error_msg:
                logging.error("Error playing audio: %s", error_msg)
                return
        # Assigned only after the player owns the new source: if the old
        # player drains mid-retarget, its callback must capture the OLD track
        # (correctly stale) — assigning earlier made the pending track look
        # finished and advanced the queue past it
        self.cur_audio = audio

    def after(self, e: Exception | None) -> None:
        """Track-end callback — runs on the FFmpeg player thread, so queue
        mutation and task creation must be marshalled back to the event loop.

        py-cord passes None on a clean drain and the exception on a player
        error, so e is genuinely optional — the old ``Exception`` annotation
        contradicted both the ``if e:`` guard below and the test suite."""
        # Pass the finished track along so the queue can ignore this callback
        # if it was retargeted (skip_to/remove/refresh-failure) while the
        # player was still draining — advancing then would double-skip.
        finished = self.cur_audio
        self.cur_audio = None
        if e:
            logging.error("Play error: %s", e)
        if self.after_function:
            self.bot.loop.call_soon_threadsafe(self.after_function, False, finished)

    def pause_playback(self) -> bool:
        client = self.client
        if client is None or not client.is_playing() or not self.cur_audio:
            return False
        # Freeze the remaining time so the UI countdown can hold steady and
        # end_time can be re-anchored on resume
        self.paused_time_left = self.cur_audio.end_time - datetime.now()
        client.pause()
        return True

    def resume_playback(self) -> bool:
        client = self.client
        if client is None or not client.is_paused():
            return False
        if self.cur_audio and self.paused_time_left is not None:
            self.cur_audio.end_time = datetime.now() + self.paused_time_left
        self.paused_time_left = None
        client.resume()
        return True

    def go_to(self, time: int) -> None:
        client = self.client
        if client is not None and client.is_playing() and self.cur_audio:
            audio_source = self._get_audio_source(
                audio=self.cur_audio, extra_before_options=[f"-ss {time}"]
            )
            client.source = audio_source

    @staticmethod
    def _get_audio_source(
        audio: Audio, extra_before_options: list | None = None, extra_options: list | None = None
    ) -> PCMVolumeTransformer:
        opts = deepcopy(FFMPEG_OPTS)
        if extra_before_options:
            opts["before_options"] += extra_before_options
        if extra_options:
            opts["options"] += extra_options

        before_options = " ".join(opts["before_options"])
        options = " ".join(opts["options"])

        return PCMVolumeTransformer(
            FFmpegPCMAudio(source=audio.audio_url, before_options=before_options, options=options),
            volume=0.25,
        )

    async def disconnect_voice(self) -> None:
        client = self.client
        if client is None:
            # Fires on every queue drain that ends with voice already gone
            logging.warning("No voice client connected to disconnect")
        else:
            try:
                await client.disconnect(force=True)
            except (AttributeError, TypeError) as disconnect_error:
                logging.warning("Unable to disconnect voice client: %s", disconnect_error)
        self.client = None
        self.paused_time_left = None

    def stop_voice(self) -> None:
        client = self.client
        if client is None:
            logging.warning("No voice client connected to stop")
            return
        try:
            client.stop()
        except (AttributeError, TypeError) as stop_error:
            logging.warning("Unable to stop voice client: %s", stop_error)

    def current_channel(self) -> VocalGuildChannel | None:
        client = self.client
        if client is None or not client.is_connected():
            return None
        # VoiceClient.channel is declared as the broad abc.Connectable, but
        # py-cord only ever binds a voice/stage channel there (its own code
        # annotates it VocalGuildChannel). Narrow rather than cast.
        channel = client.channel
        return channel if isinstance(channel, VocalGuildChannel) else None

    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()

    def is_playing(self) -> bool:
        return self.client is not None and self.client.is_playing()

    def is_paused(self) -> bool:
        return self.client is not None and self.client.is_paused()
