import os

# The slash-command decorators bind GUILD_IDS at package import time, and
# YouTubeStreamerCog fails fast when it is empty — give the test session a
# configured environment before any test module imports the package.
# A caller-provided value stays authoritative (auth.py's load_dotenv() never
# overrides existing variables), but an exported-empty GUILD_IDS= must not
# defeat the default; individual tests monkeypatch as needed.
if not os.environ.get("GUILD_IDS"):
    os.environ["GUILD_IDS"] = "123"
