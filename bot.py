import asyncio
import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()  # also print to console
    ]
)
logger = logging.getLogger("bot")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!o ", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    logger.info(f"Logged in as {bot.user} ({bot.user.id})")
    logger.info("Slash commands synced.")

async def main():
    async with bot:
        for ext in ("cogs.channels", "cogs.counter", "cogs.huntbot", "cogs.help"):
            try:
                await bot.load_extension(ext)
                logger.info(f"Loaded {ext}")
            except Exception as e:
                logger.error(f"Failed to load {ext}: {e}")
        token = os.getenv("BOT_TOKEN")
        if not token:
            raise ValueError("BOT_TOKEN not found in .env file")
        await bot.start(token)

asyncio.run(main())