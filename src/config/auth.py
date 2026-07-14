"""Load and validate Discord credentials from the environment."""

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required; copy .env.example to .env and set it")

try:
    GUILD_IDS = [
        int(guild_id.strip())
        for guild_id in os.getenv("GUILD_IDS", "").split(",")
        if guild_id.strip()
    ]
except ValueError as error:
    raise RuntimeError("GUILD_IDS must be a comma-separated list of Discord server IDs") from error

if not GUILD_IDS:
    raise RuntimeError("GUILD_IDS is required; provide at least one Discord server ID")
