import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from discord import ButtonStyle, Embed, Interaction, TextChannel
from discord.ui import Button, View

from .base_view import UserInterface
from .events import EventBus
from .models import Audio, AudioQueue
from .voice import Voice


class StreamerUserInterface(UserInterface):
    __slots__ = "change_audio_function", "queue", "voice"

    def __init__(
        self, change_audio_function: Callable, queue: AudioQueue, event_bus: EventBus, voice: Voice
    ):
        super().__init__()
        self.change_audio_function = change_audio_function
        self.queue = queue
        self.voice = voice
        event_bus.subscribe(event_type="new_audio", function=self.new_ui)
        event_bus.subscribe(event_type="no_audio", function=self.refresh_ui)
        event_bus.subscribe(event_type="no_audio", function=self.stop_auto_refresh)
        event_bus.subscribe(event_type="queue_update", function=self.refresh_ui)

    async def new_ui(self, data: Audio | TextChannel) -> None:
        if isinstance(data, Audio):
            await super().new_ui(text_channel=data.text_channel)
        else:
            await super().new_ui(text_channel=data)

    async def get_embed(self) -> Embed:
        if self.queue.get_current_audio() is None:
            embed = Embed(title="Not Playing")
        else:
            current_audio = self.queue.get_current_audio()
            embed = Embed(title=current_audio.title)

            try:
                if self.voice.is_paused() and self.voice.paused_time_left is not None:
                    time_left = f"⏸ {self._format_duration(self.voice.paused_time_left)} (paused)"
                else:
                    time_left = self.calculate_time_left(end_time=current_audio.end_time)
                embed.add_field(name="Time Left", value=time_left, inline=False)
            except AttributeError as attribute_error:
                logging.error(attribute_error)

            embed.set_image(url=current_audio.thumbnail)
            if current_audio.author is not None:
                embed.set_footer(
                    text=f"Requested by {current_audio.author.display_name}",
                    icon_url=current_audio.author.display_avatar,
                )

        next_audio_string = await self._get_audio_queue_strings(amount=5)
        if next_audio_string:
            embed.add_field(name="Next", value=next_audio_string, inline=False)

        previous_audio_string = await self._get_audio_queue_strings(amount=3, get_prev=True)
        if previous_audio_string:
            embed.add_field(name="Previous", value=previous_audio_string, inline=False)

        return embed

    async def _get_audio_queue_strings(self, amount: int = 5, get_prev: bool = False) -> str | None:
        if get_prev:
            audios = await self.queue.get_previous_queue_as_str(amount=amount)
        else:
            audios = await self.queue.get_queue_as_str(amount=amount)

        if audios:
            if get_prev:
                amount_past_max = self.queue.get_previous_queue_length() - amount
            else:
                amount_past_max = self.queue.get_queue_length() - amount

            if amount_past_max > 0:
                audios += f"**+ {amount_past_max} more**"

        return audios

    async def get_view(self) -> View:
        if self.queue.get_previous_queue_length() > 0:
            previous_audio_button = Button(style=ButtonStyle.secondary, emoji="⏮")
        else:
            previous_audio_button = Button(disabled=True, style=ButtonStyle.secondary, emoji="⏮")
        previous_audio_button.callback = self.previous_audio_callback

        if self.queue.get_current_audio() is not None:
            pause_button = Button(
                style=ButtonStyle.secondary, emoji="▶" if self.voice.is_paused() else "⏸"
            )
        else:
            pause_button = Button(disabled=True, style=ButtonStyle.secondary, emoji="⏸")
        pause_button.callback = self.pause_audio_callback

        if self.queue.get_queue_length() > 0 or self.queue.get_current_audio():
            next_audio_button = Button(style=ButtonStyle.secondary, emoji="⏭")
        else:
            next_audio_button = Button(disabled=True, style=ButtonStyle.secondary, emoji="⏭")
        next_audio_button.callback = self.next_audio_callback

        view = View(previous_audio_button, pause_button, next_audio_button, timeout=None)

        if self.queue.get_current_audio() is not None:
            go_to_youtube = Button(
                style=ButtonStyle.url,
                label="See on YouTube",
                url=self.queue.get_current_audio().webpage_url,
            )
            view.add_item(go_to_youtube)

        return view

    async def previous_audio_callback(self, interaction: Interaction):
        logging.info("Previous audio button selected: %s", interaction.user)
        if not await self._check_user_can_control(interaction=interaction):
            return
        await interaction.response.defer()
        self.change_audio_function(previous=True)

    async def next_audio_callback(self, interaction: Interaction):
        logging.info("Next audio button selected: %s", interaction.user)
        if not await self._check_user_can_control(interaction=interaction):
            return
        await interaction.response.defer()
        self.change_audio_function()

    async def pause_audio_callback(self, interaction: Interaction):
        logging.info("Pause/resume button selected: %s", interaction.user)
        if not await self._check_user_can_control(interaction=interaction):
            return
        await interaction.response.defer()
        if self.voice.is_paused():
            self.voice.resume_playback()
        else:
            self.voice.pause_playback()
        await self.refresh_ui()

    async def _check_user_can_control(self, interaction: Interaction) -> bool:
        """Playback controls are restricted to users sharing the bot's voice
        channel — otherwise anyone in the guild (or the AFK channel) can skip."""
        voice_state = getattr(interaction.user, "voice", None)
        bot_channel = self.voice.current_channel()
        allowed = (
            voice_state is not None
            and voice_state.channel is not None
            and (bot_channel is None or voice_state.channel == bot_channel)
        )
        if not allowed:
            await interaction.response.send_message(
                "You must be in the voice channel with the bot to control playback", ephemeral=True
            )
        return allowed

    @staticmethod
    def calculate_time_left(end_time: datetime) -> str:
        return StreamerUserInterface._format_duration(time_left=end_time - datetime.now())

    @staticmethod
    def _format_duration(time_left: timedelta) -> str:
        tot_sec = time_left.total_seconds()
        if tot_sec > 0:
            hours = int(tot_sec // 3600)
            minutes = int((tot_sec % 3600) // 60)
            secs = int((tot_sec % 3600) % 60)

            return f"{hours:02}:{minutes:02}:{secs:02}"
        return "00:00:00"
