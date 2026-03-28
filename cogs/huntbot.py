import discord
from discord import app_commands
from discord.ext import commands
import re
import logging
import asyncio
import json
import os
import time

logger = logging.getLogger("cogs.huntbot")
OWO_BOT_ID     = 408785106942164992
PREFS_FILE     = "huntbot_prefs.json"
REMINDERS_FILE = "huntbot_reminders.json"

# prefs structure:
# { "user_id": { "enabled": true, "mode": "dm" | "ping" | "both" } }


# ── File helpers ──────────────────────────────────────────
def load_prefs() -> dict:
    if os.path.exists(PREFS_FILE):
        with open(PREFS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_prefs(prefs: dict):
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)

def load_reminders() -> list:
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_reminders(reminders: list):
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)

def remove_reminder(user_id: int):
    reminders = [r for r in load_reminders() if r["user_id"] != user_id]
    save_reminders(reminders)


# ── Reminder mode choice view ─────────────────────────────
class ReminderModeView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ These buttons aren't for you!", ephemeral=True)
            return False
        return True

    async def _save(self, interaction: discord.Interaction, mode: str):
        prefs = load_prefs()
        prefs[str(self.user_id)] = {"enabled": True, "mode": mode}
        save_prefs(prefs)
        mode_label = {"dm": "📩 DM only", "ping": "📣 Ping in server only", "both": "📩📣 DM + Ping"}[mode]
        embed = discord.Embed(
            title="✅ Huntbot Reminders Enabled",
            description=f"Reminder mode set to **{mode_label}**.\nI'll notify you when your huntbot is back!",
            color=discord.Color.green()
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📩 DM", style=discord.ButtonStyle.primary)
    async def dm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save(interaction, "dm")

    @discord.ui.button(label="📣 Ping in server", style=discord.ButtonStyle.secondary)
    async def ping_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save(interaction, "ping")

    @discord.ui.button(label="📩📣 Both", style=discord.ButtonStyle.success)
    async def both_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save(interaction, "both")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ── Simple prompt view (mute button only) ────────────────
class PromptView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This button isn't for you!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔕 Don't ask me again", style=discord.ButtonStyle.danger)
    async def mute_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        prefs = load_prefs()
        uid = str(self.user_id)
        # Save as muted — enabled=False means "don't ask again"
        prefs[uid] = {"enabled": False, "mode": None, "muted": True}
        save_prefs(prefs)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="🔕 Got it, I won't ask again! You can still use `/huntbot on` anytime to enable reminders.",
            embed=None, view=self
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ── Cog ───────────────────────────────────────────────────
class Huntbot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._pending_reactions: dict[int, float] = {}  # message_id → fire_at
        self._active_reminders: set[int] = set()        # user_ids with an active task

    async def cog_load(self):
        reminders = load_reminders()
        if reminders:
            print(f"⏰ Rescheduling {len(reminders)} huntbot reminder(s)...")
        for r in reminders:
            uid = r["user_id"]
            if uid not in self._active_reminders:
                self._active_reminders.add(uid)
                self.bot.loop.create_task(self._send_reminder(
                    user_id=uid,
                    guild_id=r["guild_id"],
                    channel_id=r["channel_id"],
                    fire_at=r["fire_at"],
                    guild_name=r["guild_name"],
                    mode=r.get("mode", "dm"),
                ))

    async def _send_reminder(self, user_id: int, guild_id: int, channel_id: int, fire_at: float, guild_name: str, mode: str = "dm"):
        remaining = fire_at - time.time()
        if remaining > 0:
            await asyncio.sleep(remaining)

        remove_reminder(user_id)
        self._active_reminders.discard(user_id)
        logger.info(f"Firing huntbot reminder for user {user_id} in {guild_name}")

        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return

        dm_msg = f"🤖 **Huntbot is back!**\nYour huntbot in **{guild_name}** has returned!\nGo collect your animals and essence 🐾"
        channel_msg = f"⏰ <@{user_id}> Your huntbot is back!"
        dm_sent = False

        if mode in ("dm", "both"):
            try:
                await user.send(dm_msg)
                dm_sent = True
            except discord.Forbidden:
                pass

        if mode in ("ping", "both") or (mode == "dm" and not dm_sent):
            # ping mode, both mode, or DM fallback if DMs are closed
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(channel_msg)
                except discord.Forbidden:
                    pass

    # ── /huntbot ──────────────────────────────────────────
    @app_commands.command(name="huntbot", description="Toggle huntbot reminders on or off for yourself")
    @app_commands.describe(toggle="Turn reminders on or off")
    @app_commands.choices(toggle=[
        app_commands.Choice(name="on",  value="on"),
        app_commands.Choice(name="off", value="off"),
    ])
    async def huntbot_cmd(self, interaction: discord.Interaction, toggle: str):
        prefs = load_prefs()
        uid = str(interaction.user.id)

        if toggle == "on":
            embed = discord.Embed(
                title="⏰ How should I remind you?",
                description="Choose how you'd like to be notified when your huntbot is back:",
                color=discord.Color.blurple()
            )
            view = ReminderModeView(interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            prefs.pop(uid, None)
            save_prefs(prefs)
            await interaction.response.send_message("🔕 Huntbot reminders **disabled**.", ephemeral=True)

    # ── on_raw_reaction_add ──────────────────────────────
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != "⏰":
            return
        if payload.user_id == self.bot.user.id:
            return
        fire_at = self._pending_reactions.get(payload.message_id)
        if fire_at is None:
            return
        user = self.bot.get_user(payload.user_id)
        if user is None:
            return
        try:
            await user.send(
                f"⏰ That huntbot returns at <t:{int(fire_at)}:T> (<t:{int(fire_at)}:R>)"
            )
        except discord.Forbidden:
            pass

    # ── on_message ────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.id != OWO_BOT_ID:
            return

        content = message.content
        if "I WILL BE BACK IN" not in content.upper():
            embed_text = ""
            for embed in message.embeds:
                if embed.description:
                    embed_text += embed.description + "\n"
                for field in embed.fields:
                    embed_text += field.name + "\n" + field.value + "\n"
            if "I WILL BE BACK IN" not in embed_text.upper():
                return
            content = embed_text

        # Extract username
        triggered_name = None
        user_match = re.search(r"\*\*`([^`]+)`\*\*,", content)
        if user_match:
            triggered_name = user_match.group(1).strip().lower()
        if not triggered_name:
            for embed in message.embeds:
                if embed.footer and embed.footer.text:
                    footer_match = re.search(r"@(.+)", embed.footer.text)
                    if footer_match:
                        triggered_name = footer_match.group(1).strip().lower()
                        break

        # Extract time
        time_match = re.search(r"BACK IN\s+((?:\d+H\s*)?(?:\d+M)?)", content, re.IGNORECASE)
        if not time_match:
            return
        time_str = time_match.group(1).strip()
        hours   = int(h.group(1)) if (h := re.search(r"(\d+)H", time_str, re.IGNORECASE)) else 0
        minutes = int(m.group(1)) if (m := re.search(r"(\d+)M", time_str, re.IGNORECASE)) else 0
        total_seconds = hours * 3600 + minutes * 60
        if total_seconds <= 0:
            return

        guild = message.guild
        if not guild:
            return

        fire_at = time.time() + total_seconds

        # Find the member this huntbot belongs to
        owner_member = None
        if triggered_name:
            for m in guild.members:
                if m.display_name.lower() == triggered_name or m.name.lower() == triggered_name:
                    owner_member = m
                    break

        # React with alarm — store fire_at so on_reaction_add can look it up
        self._pending_reactions[message.id] = fire_at
        try:
            await message.add_reaction("⏰")
        except discord.Forbidden:
            pass

        if owner_member is None:
            return

        prefs = load_prefs()
        uid = str(owner_member.id)
        user_pref = prefs.get(uid)

        if user_pref and user_pref.get("enabled"):
            # User is subscribed — schedule reminder and confirm
            mode = user_pref.get("mode", "dm")
            reminders = [r for r in load_reminders() if r["user_id"] != owner_member.id]
            reminders.append({
                "user_id":    owner_member.id,
                "guild_id":   guild.id,
                "guild_name": guild.name,
                "channel_id": message.channel.id,
                "fire_at":    fire_at,
                "mode":       mode,
            })
            save_reminders(reminders)
            logger.info(f"Reminder set for {owner_member} (id={owner_member.id}), fires at {fire_at}")

            # Cancel previous task by clearing from active set — new task replaces it
            self._active_reminders.add(owner_member.id)
            self.bot.loop.create_task(self._send_reminder(
                user_id=owner_member.id,
                guild_id=guild.id,
                channel_id=message.channel.id,
                fire_at=fire_at,
                guild_name=guild.name,
                mode=mode,
            ))

        else:
            # User not subscribed and not muted — show simple prompt
            if user_pref and user_pref.get("muted"):
                return  # User said don't ask again

            try:
                await message.channel.send(
                    f"Hey {owner_member.mention}, would you like to be reminded when your huntbot is back? "
                    f"Run `/huntbot on` to set it up! "
                    f"\n*(Click the button below if you don't want these prompts)*",
                    view=PromptView(owner_member.id)
                )
            except discord.Forbidden:
                pass


async def setup(bot):
    await bot.add_cog(Huntbot(bot))