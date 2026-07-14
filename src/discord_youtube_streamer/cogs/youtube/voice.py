import logging
from asyncio import sleep, to_thread
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime

from discord import Bot, FFmpegPCMAudio, PCMVolumeTransformer, VoiceChannel, utils
from discord.errors import ClientException
from discord.opus import OpusNotLoaded

from ...config.settings import FFMPEG_OPTS
from .events import EventBus
from .models import Audio


class Voice:
    __slots__ = "after_function", "bot", "client", "cur_audio", "paused_time_left"

    def __init__(self, bot: Bot, event_bus: EventBus, after_function: Callable | None = None):
        self.bot = bot
        self.after_function = after_function
        self.client = None
        self.cur_audio = None
        self.paused_time_left = None
        event_bus.subscribe(event_type="new_audio", function=self.stream)
        event_bus.subscribe(event_type="no_audio", function=self.disconnect_voice)

    async def join_voice(self, voice_channel: VoiceChannel) -> None:
        try:
            # Capture the returned client: bot.voice_clients[0] would grab an
            # arbitrary guild's session once more than one guild is connected.
            self.client = await voice_channel.connect()
            logging.debug("Connected to new voice channel: %s", voice_channel)
        except ClientException:
            # Already connected in this guild — reuse that client and move it
            existing = utils.get(self.bot.voice_clients, guild=voice_channel.guild)
            if existing:
                self.client = existing
                await self.client.move_to(voice_channel)
                logging.debug("Moved to new voice channel: %s", voice_channel)
            else:
                logging.warning(
                    "Already connected but no voice client available for guild: %s",
                    voice_channel.guild,
                )

    async def _ensure_connected(self, voice_channel: VoiceChannel) -> None:
        """Join voice and wait until the connection is fully established."""
        await self.join_voice(voice_channel=voice_channel)
        if self.client and not self.client.is_connected():
            logging.debug("Waiting for voice connection to be ready...")
            for _ in range(30):
                await sleep(0.2)
                if self.client.is_connected():
                    break
            if not self.client.is_connected():
                logging.error("Voice connection did not become ready in time")

    async def check_voice(self, voice_channel: VoiceChannel):
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
                    self.after_function()
                return

        audio_source = self._get_audio_source(audio=audio)
        self.cur_audio = audio

        if self.is_playing() or self.is_paused():
            # A paused player still owns the stream — swap the source and
            # resume rather than calling play(), which would spawn a second
            # player thread on top of the paused one
            self.client.source = audio_source
            if self.is_paused():
                self.paused_time_left = None
                self.client.resume()
        else:
            try:
                self.client.play(source=audio_source, after=self.after)
            except (TypeError, AttributeError, ClientException, OpusNotLoaded) as error_msg:
                logging.error("Error playing audio: %s", error_msg)

    def after(self, e: Exception) -> None:
        """Track-end callback — runs on the FFmpeg player thread, so queue
        mutation and task creation must be marshalled back to the event loop."""
        self.cur_audio = None
        if e:
            logging.error("Play error: %s", e)
        if self.after_function:
            self.bot.loop.call_soon_threadsafe(self.after_function)

    def pause_playback(self) -> bool:
        if not self.is_playing() or not self.cur_audio:
            return False
        # Freeze the remaining time so the UI countdown can hold steady and
        # end_time can be re-anchored on resume
        self.paused_time_left = self.cur_audio.end_time - datetime.now()
        self.client.pause()
        return True

    def resume_playback(self) -> bool:
        if not self.is_paused():
            return False
        if self.cur_audio and self.paused_time_left is not None:
            self.cur_audio.end_time = datetime.now() + self.paused_time_left
        self.paused_time_left = None
        self.client.resume()
        return True

    def go_to(self, time: int) -> None:
        if self.is_playing() and self.cur_audio:
            audio_source = self._get_audio_source(
                audio=self.cur_audio, extra_before_options=[f"-ss {time}"]
            )
            self.client.source = audio_source

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
        try:
            await self.client.disconnect(force=True)
        except (AttributeError, TypeError) as missing_client:
            logging.warning("No voice client connected to stop: %s", missing_client)
        self.client = None
        self.paused_time_left = None

    def stop_voice(self) -> None:
        try:
            self.client.stop()
        except (AttributeError, TypeError) as missing_client:
            logging.warning("No voice client connected to stop: %s", missing_client)

    def current_channel(self) -> VoiceChannel | None:
        return self.client.channel if self.is_connected() else None

    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()

    def is_playing(self) -> bool:
        return self.client is not None and self.client.is_playing()

    def is_paused(self) -> bool:
        return self.client is not None and self.client.is_paused()
