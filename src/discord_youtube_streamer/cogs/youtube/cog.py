import logging
from asyncio import all_tasks, get_running_loop

from discord import (
    ApplicationContext,
    Bot,
    ClientException,
    Colour,
    Embed,
    Member,
    TextChannel,
    User,
    VoiceChannel,
)
from discord.commands import option, slash_command
from discord.errors import HTTPException
from discord.ext import commands

from ...config.auth import GUILD_IDS
from ...config.settings import DELETE_TIMER
from .client import get_audio, get_playlist
from .events import EventBus
from .models import Audio, AudioQueue
from .views import StreamerUserInterface
from .voice import Voice

green = Colour.green()
red = Colour.red()


class GuildSession:
    """Everything one guild needs to stream audio. Each guild gets its own
    event bus, queue, voice wrapper, and control-panel UI so playback in one
    guild can never drive another guild's session."""

    __slots__ = "event_bus", "guild_id", "queue", "user_interface", "voice"

    def __init__(self, bot: Bot, guild_id: int):
        self.guild_id = guild_id
        self.event_bus = EventBus()
        self.queue = AudioQueue(event_loop=get_running_loop(), event_bus=self.event_bus)
        self.voice = Voice(bot=bot, event_bus=self.event_bus, after_function=self.change_audio)
        self.user_interface = StreamerUserInterface(
            change_audio_function=self.change_audio,
            queue=self.queue,
            event_bus=self.event_bus,
            voice=self.voice,
        )

    def change_audio(self, previous: bool = False) -> None:
        if previous:
            logging.info("Getting previous audio")
            self.queue.get_previous_audio()
        else:
            logging.info("Getting next audio")
            self.queue.get_next_audio()

    @property
    def playlist_task_name(self) -> str:
        return f"playlist-{self.guild_id}"


class YouTubeStreamerCog(commands.Cog):
    __slots__ = "bot", "sessions"

    def __init__(self, bot: Bot):
        self.bot = bot
        self.sessions: dict[int, GuildSession] = {}

    def _get_session(self, guild_id: int) -> GuildSession:
        if guild_id not in self.sessions:
            self.sessions[guild_id] = GuildSession(bot=self.bot, guild_id=guild_id)
        return self.sessions[guild_id]

    @slash_command(
        name="play",
        description="Queue YouTube audio files via a search query or URL",
        guild_ids=GUILD_IDS,
    )
    @option("query", description="Search or URL", required=True)
    async def play_command(self, ctx: ApplicationContext, query: str) -> None:
        logging.info("Play command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        audio_title = await self.queue_audio(
            session=session,
            author=ctx.author,
            voice_channel=ctx.author.voice.channel,
            text_channel=ctx.channel,
            query=query,
        )
        if audio_title:
            await ctx.respond(
                embed=Embed(title="Queued", description=f"**{audio_title}**", color=green),
                delete_after=DELETE_TIMER,
            )
        else:
            await ctx.respond(
                embed=Embed(title="Error", description=f"Unable to queue **{query}**", color=red),
                delete_after=DELETE_TIMER,
            )

    @slash_command(
        name="play_next",
        description="Queue up next YouTube audio files via a search query or URL",
        guild_ids=GUILD_IDS,
    )
    @option("query", description="Search or URL", required=True)
    async def play_next_command(self, ctx: ApplicationContext, query: str) -> None:
        logging.info("Play next command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        audio_title = await self.queue_audio(
            session=session,
            author=ctx.author,
            voice_channel=ctx.author.voice.channel,
            text_channel=ctx.channel,
            query=query,
            add_to_start=True,
        )
        if audio_title:
            await ctx.respond(
                embed=Embed(title="Queued Next", description=f"**{audio_title}**", color=green),
                delete_after=DELETE_TIMER,
            )
        else:
            await ctx.respond(
                embed=Embed(
                    title="Error", description=f"Unable to queue next **{query}**", color=red
                ),
                delete_after=DELETE_TIMER,
            )

    @slash_command(
        name="playlist",
        description="Queue a series of audio files from a YouTube Playlist URL",
        guild_ids=GUILD_IDS,
    )
    @option("url", description="A playlist URL", required=True)
    async def playlist_command(self, ctx: ApplicationContext, url: str) -> None:
        logging.info("Playlist command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        # Flat extraction is a network round-trip — keep it off the event loop
        playlist = await get_running_loop().run_in_executor(None, get_playlist, url)

        if not playlist:
            await ctx.respond(
                embed=Embed(
                    title="Error", description=f"Unable to queue playlist **{url}**", color=red
                ),
                delete_after=DELETE_TIMER,
            )
            return

        await ctx.respond(
            embed=Embed(title="Queuing Playlist", description=playlist["title"], color=green),
            delete_after=DELETE_TIMER,
        )

        get_running_loop().create_task(
            coro=self.queue_playlist(
                session=session,
                author=ctx.author,
                voice_channel=ctx.author.voice.channel,
                text_channel=ctx.channel,
                urls=playlist["urls"],
            ),
            name=session.playlist_task_name,
        )

    @slash_command(
        name="pause", description="Pause the currently playing audio", guild_ids=GUILD_IDS
    )
    async def pause_command(self, ctx: ApplicationContext) -> None:
        logging.info("Pause command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        if session.voice.pause_playback():
            await session.user_interface.refresh_ui()
            await ctx.respond(
                embed=Embed(
                    title="Paused", description=f"**{session.voice.cur_audio}**", color=green
                ),
                delete_after=DELETE_TIMER,
            )
        else:
            await ctx.respond(
                embed=Embed(
                    title="Error", description="There is currently no audio playing", color=red
                ),
                delete_after=DELETE_TIMER,
            )

    @slash_command(name="resume", description="Resume the paused audio", guild_ids=GUILD_IDS)
    async def resume_command(self, ctx: ApplicationContext) -> None:
        logging.info("Resume command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        if session.voice.resume_playback():
            await session.user_interface.refresh_ui()
            await ctx.respond(
                embed=Embed(
                    title="Resumed", description=f"**{session.voice.cur_audio}**", color=green
                ),
                delete_after=DELETE_TIMER,
            )
        else:
            await ctx.respond(
                embed=Embed(
                    title="Error", description="There is currently no paused audio", color=red
                ),
                delete_after=DELETE_TIMER,
            )

    @slash_command(
        name="remove_at",
        description="Remove the song at an up next queue position",
        guild_ids=GUILD_IDS,
    )
    @option(
        "position",
        input_type=int,
        min_value=1,
        description="Queue position as shown in the Next list",
    )
    async def remove_at_command(self, ctx: ApplicationContext, position: int) -> None:
        logging.info("Remove at command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        audio_title = session.queue.remove_at(position=position)
        if audio_title:
            await ctx.respond(
                embed=Embed(
                    title="Removed from Queue",
                    description=f"Removed **{audio_title}** (position {position})",
                    color=green,
                ),
                delete_after=DELETE_TIMER,
            )
        else:
            await ctx.respond(
                embed=Embed(
                    title="Error",
                    description=f"No song at queue position **{position}**",
                    color=red,
                ),
                delete_after=DELETE_TIMER,
            )

    @slash_command(
        name="skip_to",
        description="Skip ahead to the song at an up next queue position",
        guild_ids=GUILD_IDS,
    )
    @option(
        "position",
        input_type=int,
        min_value=1,
        description="Queue position as shown in the Next list",
    )
    async def skip_to_command(self, ctx: ApplicationContext, position: int) -> None:
        logging.info("Skip to command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        audio_title = session.queue.skip_to(position=position)
        if audio_title:
            await ctx.respond(
                embed=Embed(title="Skipping To", description=f"**{audio_title}**", color=green),
                delete_after=DELETE_TIMER,
            )
        else:
            await ctx.respond(
                embed=Embed(
                    title="Error",
                    description=f"No song at queue position **{position}**",
                    color=red,
                ),
                delete_after=DELETE_TIMER,
            )

    @slash_command(
        name="restart_queue",
        description="Start playing from the beginning of the previous queue",
        guild_ids=GUILD_IDS,
    )
    async def restart_queue(self, ctx: ApplicationContext) -> None:
        logging.info("Restart queue command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        await session.queue.restart_queue()
        await ctx.respond(
            embed=Embed(title="Restarted Queue", color=green), delete_after=DELETE_TIMER
        )

    @slash_command(
        name="go_to",
        description="Go to a specific time in the audio. If no time is set, the audio is reset to the start",
        guild_ids=GUILD_IDS,
    )
    @option(
        "hour", input_type=int, min_value=0, max_value=100, default=0, description="Hour [optional]"
    )
    @option(
        "minute",
        input_type=int,
        min_value=0,
        max_value=59,
        default=0,
        description="Minute [optional, max: 59]",
    )
    @option(
        "second",
        input_type=int,
        min_value=0,
        max_value=59,
        default=0,
        description="Second [optional, max: 59]",
    )
    async def go_to(self, ctx: ApplicationContext, hour: int, minute: int, second: int) -> None:
        logging.info("Go to command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        if session.voice.is_playing():
            time, description = self._get_time_and_description(
                hour=hour, minute=minute, second=second
            )
            if time >= session.queue.get_current_audio().length:
                await ctx.respond(
                    embed=Embed(
                        title="Out of Bounds",
                        description="Time requested is over song length",
                        color=red,
                    ),
                    delete_after=DELETE_TIMER,
                )
            else:
                session.voice.go_to(time=time)
                session.queue.get_current_audio().set_end_time(offset=time)
                await ctx.respond(
                    embed=Embed(title="Going To", description=description[:-2], color=green),
                    delete_after=DELETE_TIMER,
                )
        else:
            await ctx.respond(
                embed=Embed(
                    title="Error", description="There is currently no audio playing", color=red
                ),
                delete_after=DELETE_TIMER,
            )

    @slash_command(name="clear_queue", description="Clear the up next queue", guild_ids=GUILD_IDS)
    async def clear_up_next_command(self, ctx: ApplicationContext) -> None:
        logging.info("Clear command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        self.cancel_playlist(task_name=session.playlist_task_name)
        session.queue.clear_next_queue()
        await ctx.respond(
            embed=Embed(title="Cleared Up Next Queue", color=green), delete_after=DELETE_TIMER
        )

    @slash_command(
        name="clear_previous_queue", description="Clear the previous queue", guild_ids=GUILD_IDS
    )
    async def clear_previous_command(self, ctx: ApplicationContext) -> None:
        logging.info("Clear command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        session.queue.clear_previous_queue()
        await ctx.respond(
            embed=Embed(title="Cleared Previous Queue", color=green), delete_after=DELETE_TIMER
        )

    @slash_command(
        name="remove",
        description="Skips and removes the currently playing song from the queue",
        guild_ids=GUILD_IDS,
    )
    async def remove_command(self, ctx: ApplicationContext) -> None:
        logging.info("Remove from queue command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        audio_title = session.queue.remove_current_audio()
        if audio_title:
            await ctx.respond(
                embed=Embed(
                    title="Remove from Queue", description=f"Removed **{audio_title}**", color=green
                ),
                delete_after=DELETE_TIMER,
            )
        else:
            await ctx.respond(
                embed=Embed(
                    title="Unable to Remove from Queue",
                    description="Unable to find current audio to remove",
                    color=red,
                ),
                delete_after=DELETE_TIMER,
            )

    @slash_command(
        name="reset",
        description="Reset the voice client, queue, and user interface",
        guild_ids=GUILD_IDS,
    )
    async def reset_command(self, ctx: ApplicationContext) -> None:
        logging.info("Reset command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        self.cancel_playlist(task_name=session.playlist_task_name)
        session.queue.reset_queue()

        await session.voice.disconnect_voice()

        ctx_message_id = await self.get_id_from_ctx(ctx=ctx)
        await session.user_interface.delete_ui(
            bot=self.bot, guild=ctx.guild, ignore_msg_ids={ctx_message_id}
        )

        await ctx.respond(
            embed=Embed(
                title="Reset Bot",
                description=f"**{self.bot.user.display_name}** has been reset",
                color=green,
            ),
            delete_after=DELETE_TIMER,
        )

    @slash_command(
        name="reconnect_bot",
        description="Reconnect the bot to your voice channel and text channel",
        guild_ids=GUILD_IDS,
    )
    async def reconnect_bot(self, ctx: ApplicationContext) -> None:
        logging.info("Reconnect command invoked")
        session = self._get_session(guild_id=ctx.guild_id)
        try:
            await session.voice.join_voice(voice_channel=ctx.author.voice.channel)
            await session.user_interface.new_ui(data=ctx.channel)
            await ctx.respond(
                embed=Embed(
                    title="Reconnected",
                    description=f"""**{self.bot.user.display_name}** connected to voice channel **{ctx.author.voice.channel}**
                                                          and text channel **{ctx.channel}**""",
                    color=green,
                ),
                delete_after=DELETE_TIMER,
            )
            logging.info("Bot reconnected")
        except AttributeError as attribute_error:
            logging.error("Unable to connect bot to voice: %s", attribute_error)
            await ctx.respond(
                embed=Embed(
                    title="Unable to Connect",
                    description=f"Error connecting **{self.bot.user.display_name}** to voice",
                    color=red,
                ),
                delete_after=DELETE_TIMER,
            )

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()
        # Sessions are created lazily per guild on first command; nothing to
        # clean up here — UI references do not survive a restart
        logging.info(
            "YouTubeStreamerCog ready in guilds: %s",
            [guild.id for guild in self.bot.guilds if guild.id in GUILD_IDS],
        )

    @play_command.before_invoke
    @play_next_command.before_invoke
    @playlist_command.before_invoke
    @pause_command.before_invoke
    @resume_command.before_invoke
    @remove_at_command.before_invoke
    @skip_to_command.before_invoke
    @restart_queue.before_invoke
    @go_to.before_invoke
    @clear_up_next_command.before_invoke
    @clear_previous_command.before_invoke
    @remove_command.before_invoke
    @reset_command.before_invoke
    @reconnect_bot.before_invoke
    async def defer_and_check_voice(self, ctx: ApplicationContext) -> None:
        await ctx.defer()
        if ctx.author and ctx.author.voice is None:
            await ctx.respond(
                embed=Embed(
                    title="Error", description="You are not connected to a voice channel", color=red
                ),
                delete_after=DELETE_TIMER,
            )
            raise commands.CommandError("User not connected to a voice channel")

        # While the bot is connected, only users in its voice channel may
        # control playback (stops drive-by skips/resets from other channels)
        session = self.sessions.get(ctx.guild_id)
        bot_channel = session.voice.current_channel() if session else None
        if bot_channel is not None and ctx.author.voice.channel != bot_channel:
            await ctx.respond(
                embed=Embed(
                    title="Error",
                    description=f"You must be in **{bot_channel}** to control playback",
                    color=red,
                ),
                delete_after=DELETE_TIMER,
            )
            raise commands.CommandError("User not in the bot voice channel")

    async def queue_audio(
        self,
        session: GuildSession,
        query: str,
        author: User | Member,
        voice_channel: VoiceChannel,
        text_channel: TextChannel,
        add_to_start: bool = False,
    ) -> str | None:
        logging.info("Queuing %s", query)
        entry = await get_running_loop().run_in_executor(None, get_audio, query)

        title = None
        if entry:
            audio = Audio(
                author=author,
                voice_channel=voice_channel,
                text_channel=text_channel,
                audio_url=entry["audio_url"],
                webpage_url=entry["webpage_url"],
                title=entry["title"],
                length=entry["length"],
                thumbnail=entry["thumbnail"],
            )

            if add_to_start:
                await session.queue.append_left(audio=audio)
            else:
                await session.queue.append(audio=audio)

            # Ensure voice connection is established
            try:
                if not session.voice.is_connected():
                    logging.info(
                        "Voice not connected, attempting to join voice channel for queued audio"
                    )
                    await session.voice.join_voice(voice_channel=voice_channel)
            except Exception as e:
                logging.warning("Failed to establish voice connection when queuing audio: %s", e)

            await session.user_interface.refresh_ui()
            logging.info("Queued %s %s", audio.title, audio.audio_url)

            title = entry["title"]
        else:
            logging.error("Unable to queue audio %s", query)
        return title

    async def queue_playlist(
        self,
        session: GuildSession,
        author: User | Member,
        voice_channel: VoiceChannel,
        text_channel: TextChannel,
        urls: list[str],
    ) -> None:
        for url in urls:
            await self.queue_audio(
                session=session,
                author=author,
                voice_channel=voice_channel,
                text_channel=text_channel,
                query=url,
            )

    @staticmethod
    def cancel_playlist(task_name: str) -> None:
        tasks = [task for task in all_tasks() if task.get_name() == task_name]
        for task in tasks:
            task.cancel()

    @staticmethod
    async def get_id_from_ctx(ctx: ApplicationContext):
        try:
            ctx_message = await ctx.interaction.original_response()
            ctx_message_id = ctx_message.id
        except (HTTPException, ClientException) as msg_not_found:
            logging.error("Unable to find message: %s", msg_not_found)
            ctx_message_id = None
        return ctx_message_id

    @staticmethod
    def _get_time_and_description(
        hour: int | None, minute: int | None, second: int | None
    ) -> tuple[int, str]:
        time = 0
        description = "Going to "
        if hour:
            time += hour * 60 * 60
            description += f"**{hour} hour**, " if hour == 1 else f"**{hour} hours**, "
        if minute:
            time += minute * 60
            description += f"**{minute} minute**, " if minute == 1 else f"**{minute} minutes**, "
        if second:
            time += second
            description += f"**{second} second**, " if second == 1 else f"**{second} seconds**, "
        if time == 0:
            description = "Going to start  "
        return time, description


AudioStreamer = YouTubeStreamerCog

__all__ = ["AudioStreamer", "YouTubeStreamerCog"]
