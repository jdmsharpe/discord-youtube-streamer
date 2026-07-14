from discord.ext import commands

from discord_youtube_streamer import AudioStreamer, YouTubeStreamerCog


def test_public_cog_exports() -> None:
    assert AudioStreamer is YouTubeStreamerCog
    assert issubclass(YouTubeStreamerCog, commands.Cog)
