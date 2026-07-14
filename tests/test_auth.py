import pytest

from discord_youtube_streamer.config import auth


def test_parse_guild_ids() -> None:
    assert auth._parse_guild_ids("123, 456,,") == [123, 456]


def test_parse_guild_ids_rejects_invalid_tokens() -> None:
    with pytest.raises(RuntimeError, match="Invalid GUILD_IDS"):
        auth._parse_guild_ids("123,not-an-id")


def test_validate_required_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_IDS", "123")

    auth.validate_required_config()


def test_validate_required_config_reports_missing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("GUILD_IDS", raising=False)

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        auth.validate_required_config()
