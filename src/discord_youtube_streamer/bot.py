"""Standalone application entry point."""

from discord import Bot, Intents

from .cogs.youtube import YouTubeStreamerCog
from .config import auth
from .logging_setup import configure_logging


def build_bot() -> Bot:
    """Build a configured bot without connecting to Discord."""
    auth.validate_required_config()

    intents = Intents.default()
    return_bot = Bot(intents=intents)
    return_bot.add_cog(YouTubeStreamerCog(bot=return_bot))
    return return_bot


def main() -> None:
    """Run the standalone YouTube streamer bot."""
    configure_logging()
    bot = build_bot()
    if auth.BOT_TOKEN is None:  # Narrow the type after validation.
        raise RuntimeError("BOT_TOKEN is required")
    bot.run(auth.BOT_TOKEN)


__all__ = ["build_bot", "main"]
