"""Public package interface for Discord YouTube Streamer."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cogs.youtube.cog import AudioStreamer, YouTubeStreamerCog

__all__ = ["AudioStreamer", "YouTubeStreamerCog"]


def __getattr__(name: str):
    if name in __all__:
        from .cogs.youtube import AudioStreamer, YouTubeStreamerCog

        return {
            "AudioStreamer": AudioStreamer,
            "YouTubeStreamerCog": YouTubeStreamerCog,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
