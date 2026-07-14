"""Environment-backed Discord configuration."""

import os

from dotenv import load_dotenv

load_dotenv()


def _get_env_or_none(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped_value = value.strip()
    return stripped_value or None


def _parse_guild_ids(raw_guild_ids: str) -> list[int]:
    guild_ids: list[int] = []
    for token in raw_guild_ids.split(","):
        stripped_token = token.strip()
        if not stripped_token:
            continue
        try:
            guild_ids.append(int(stripped_token))
        except ValueError as error:
            raise RuntimeError(
                "Invalid GUILD_IDS value. Expected a comma-separated list of "
                f"integers, but received {stripped_token!r}."
            ) from error
    return guild_ids


def validate_required_config() -> None:
    """Fail with actionable errors before connecting to Discord."""
    if _get_env_or_none("BOT_TOKEN") is None:
        raise RuntimeError("BOT_TOKEN is required; copy .env.example to .env and set it")
    if not _parse_guild_ids(os.getenv("GUILD_IDS", "")):
        raise RuntimeError("GUILD_IDS is required; provide at least one Discord server ID")


BOT_TOKEN = _get_env_or_none("BOT_TOKEN")
GUILD_IDS = _parse_guild_ids(os.getenv("GUILD_IDS", ""))

__all__ = ["BOT_TOKEN", "GUILD_IDS", "validate_required_config"]
