import pytest

from discord_youtube_streamer.bot import build_bot


@pytest.mark.asyncio
async def test_build_bot_registers_youtube_cog(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_IDS", "123")

    bot = build_bot()

    assert bot.get_cog("YouTubeStreamerCog") is not None
