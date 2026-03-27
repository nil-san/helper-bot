import os
import logging
from discord import app_commands, Interaction

logger = logging.getLogger("utils")


def owner_only(interaction: Interaction) -> bool:
    raw = os.getenv("OWNER_IDS", "").strip()
    if not raw:
        raise app_commands.CheckFailure("❌ OWNER_IDS is not set in .env file.")
    # Accept both "123,456" and "123, 456" (strip whitespace around each id)
    owner_ids = {uid.strip() for uid in raw.split(",") if uid.strip()}
    if str(interaction.user.id) not in owner_ids:
        raise app_commands.CheckFailure("❌ Only the bot owner can use this command.")
    return True