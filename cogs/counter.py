import discord
import json
import os
import re
import logging
import time
from datetime import datetime, timedelta, timezone
from discord import app_commands
from discord.ext import commands
from utils import owner_only

logger = logging.getLogger("cogs.counter")

DATA_FILE  = "counts.json"
WORDS_FILE = "words.json"

# words.json structure:
# {
#   "owo": { "cooldown": 10, "aliases": ["OwO", "0w0"] }
# }


# ── File helpers ──────────────────────────────────────────
def load_words() -> dict:
    if os.path.exists(WORDS_FILE):
        with open(WORDS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_words(words: dict):
    with open(WORDS_FILE, "w") as f:
        json.dump(words, f, indent=2)

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_user_word(data, user_id, word):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {}
    if word not in data[uid]:
        data[uid][word] = {"total": 0, "last_used": 0, "history": {}}
    return data[uid][word]

def all_triggers(words: dict) -> dict:
    """Returns a flat map of trigger → main_word for all words and their aliases."""
    mapping = {}
    for word, cfg in words.items():
        mapping[word.lower()] = word
        for alias in cfg.get("aliases", []):
            mapping[alias.lower()] = word
    return mapping


# ── Autocompletes ─────────────────────────────────────────
async def word_autocomplete(interaction: discord.Interaction, current: str):
    words = load_words()
    return [app_commands.Choice(name=w, value=w) for w in words if current.lower() in w.lower()]

async def alias_autocomplete(interaction: discord.Interaction, current: str):
    words = load_words()
    # Show existing aliases across all words
    aliases = []
    for cfg in words.values():
        aliases.extend(cfg.get("aliases", []))
    return [app_commands.Choice(name=a, value=a) for a in aliases if current.lower() in a.lower()][:25]


# ── Cog ───────────────────────────────────────────────────
class Counter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── on_message ────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        words = load_words()
        if not words:
            return

        triggers = all_triggers(words)
        content = message.content.lower().strip()

        # Only count if the message STARTS with the trigger
        matched_main_words = {}
        for trigger, main_word in triggers.items():
            if re.match(r"^" + re.escape(trigger.lower()) + r"(\s|$)", content):
                matched_main_words[main_word] = True

        if not matched_main_words:
            return

        data = load_data()
        now = time.time()
        today = get_today()
        counted = False
        for main_word in matched_main_words:
            cfg = words[main_word]
            cooldown = cfg["cooldown"]
            entry = get_user_word(data, message.author.id, main_word)
            remaining = cooldown - (now - entry["last_used"])
            if remaining > 0:
                continue  # silently skip, no ping
            entry["total"] += 1
            entry["last_used"] = now
            entry["history"][today] = entry["history"].get(today, 0) + 1
            counted = True

        if counted:
            save_data(data)

    # ── /addword ──────────────────────────────────────────
    @app_commands.check(owner_only)
    @app_commands.command(name="addword", description="Add a word to track with a cooldown")
    @app_commands.describe(word="Word or phrase to track", cooldown="Cooldown in seconds")
    async def addword(self, interaction: discord.Interaction, word: str, cooldown: app_commands.Range[int, 1, 86400]):
        words = load_words()
        word = word.lower().strip()
        action = "Updated" if word in words else "Added"
        if word not in words:
            words[word] = {"cooldown": cooldown, "aliases": []}
        else:
            words[word]["cooldown"] = cooldown
        save_words(words)
        await interaction.response.send_message(f"✅ {action} `{word}` with a **{cooldown}s** cooldown.", ephemeral=True)

    # ── /addalias ─────────────────────────────────────────
    @app_commands.check(owner_only)
    @app_commands.command(name="addalias", description="Add an alternate word that counts towards a tracked word")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="The main tracked word", alias="The alternate word/phrase to also count")
    async def addalias(self, interaction: discord.Interaction, word: str, alias: str):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not a tracked word.", ephemeral=True)
            return
        alias = alias.lower().strip()
        if alias in words[word].get("aliases", []):
            await interaction.response.send_message(f"⚠️ `{alias}` is already an alias for `{word}`.", ephemeral=True)
            return
        words[word].setdefault("aliases", []).append(alias)
        save_words(words)
        await interaction.response.send_message(f"✅ `{alias}` will now count towards `{word}`.", ephemeral=True)

    # ── /removealias ──────────────────────────────────────
    @app_commands.check(owner_only)
    @app_commands.command(name="removealias", description="Remove an alias from a tracked word")
    @app_commands.autocomplete(word=word_autocomplete, alias=alias_autocomplete)
    @app_commands.describe(word="The main tracked word", alias="The alias to remove")
    async def removealias(self, interaction: discord.Interaction, word: str, alias: str):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not a tracked word.", ephemeral=True)
            return
        aliases = words[word].get("aliases", [])
        if alias not in aliases:
            await interaction.response.send_message(f"❌ `{alias}` is not an alias for `{word}`.", ephemeral=True)
            return
        aliases.remove(alias)
        words[word]["aliases"] = aliases
        save_words(words)
        await interaction.response.send_message(f"✅ Removed alias `{alias}` from `{word}`.", ephemeral=True)

    # ── /removeword ───────────────────────────────────────
    @app_commands.check(owner_only)
    @app_commands.command(name="removeword", description="Stop tracking a word (keeps history)")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="Word to remove")
    async def removeword(self, interaction: discord.Interaction, word: str):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not being tracked.", ephemeral=True)
            return
        del words[word]
        save_words(words)
        await interaction.response.send_message(f"✅ Removed `{word}` from tracking.", ephemeral=True)

    # ── /deleteword ───────────────────────────────────────
    @app_commands.check(owner_only)
    @app_commands.command(name="deleteword", description="Remove a word and wipe all its history")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="Word to permanently delete along with all history")
    async def deleteword(self, interaction: discord.Interaction, word: str):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not being tracked.", ephemeral=True)
            return
        del words[word]
        save_words(words)
        data = load_data()
        wiped = 0
        for uid in data:
            if word in data[uid]:
                del data[uid][word]
                wiped += 1
        save_data(data)
        await interaction.response.send_message(f"🗑️ Deleted `{word}` and wiped history for **{wiped}** user(s).", ephemeral=True)

    # ── /listwords ────────────────────────────────────────
    @app_commands.command(name="listwords", description="Show all tracked words, aliases and cooldowns")
    async def listwords(self, interaction: discord.Interaction):
        words = load_words()
        if not words:
            await interaction.response.send_message("No words being tracked yet. Use `/addword` to add one!", ephemeral=True)
            return
        rows = []
        for w, cfg in sorted(words.items()):
            aliases = cfg.get("aliases", [])
            alias_str = f" *(also: {', '.join(f'`{a}`' for a in aliases)})*" if aliases else ""
            rows.append(f"`{w}` — **{cfg['cooldown']}s**{alias_str}")
        embed = discord.Embed(title="📋 Tracked Words", description="\n".join(rows), color=discord.Color.blurple())
        embed.set_footer(text=f"{len(words)} word(s) tracked")
        await interaction.response.send_message(embed=embed)

    # ── /count ────────────────────────────────────────────
    @app_commands.command(name="count", description="Check count stats for a word")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="The word to check", user="User to check (leave empty for yourself)")
    async def count(self, interaction: discord.Interaction, word: str, user: discord.Member = None):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not a tracked word.", ephemeral=True)
            return
        target = user or interaction.user
        data = load_data()
        entry = get_user_word(data, target.id, word)
        now_dt = datetime.now(timezone.utc)
        today = get_today()
        daily   = entry["history"].get(today, 0)
        weekly  = sum(v for k, v in entry["history"].items() if (now_dt - datetime.strptime(k, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days < 7)
        monthly = sum(v for k, v in entry["history"].items() if k.startswith(now_dt.strftime("%Y-%m")))
        aliases = words[word].get("aliases", [])
        embed = discord.Embed(title=f"📊 Stats for `{word}`", color=discord.Color.blurple())
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        embed.add_field(name="Today",    value=f"**{daily}**",          inline=True)
        embed.add_field(name="Weekly",   value=f"**{weekly}**",         inline=True)
        embed.add_field(name="Monthly",  value=f"**{monthly}**",        inline=True)
        embed.add_field(name="All Time", value=f"**{entry['total']}**", inline=True)
        if aliases:
            embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in aliases), inline=False)
        embed.set_footer(text=f"Cooldown: {words[word]['cooldown']}s per user")
        await interaction.response.send_message(embed=embed)

    # ── /history ──────────────────────────────────────────
    @app_commands.command(name="history", description="Show day-by-day history for a word")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="The word to check", user="User to check (leave empty for yourself)", days="Recent days to show (default 7, max 30)")
    async def history(self, interaction: discord.Interaction, word: str, user: discord.Member = None, days: app_commands.Range[int, 1, 30] = 7):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not a tracked word.", ephemeral=True)
            return
        target = user or interaction.user
        data = load_data()
        entry = get_user_word(data, target.id, word)
        now_dt = datetime.now(timezone.utc)
        rows = []
        for i in range(days - 1, -1, -1):
            day = (now_dt - timedelta(days=i)).strftime("%Y-%m-%d")
            cnt = entry["history"].get(day, 0)
            rows.append(f"`{day}` {'█' * min(cnt, 20) if cnt else '—'} **{cnt}**")
        embed = discord.Embed(title=f"📅 {days}-Day History for `{word}`", description="\n".join(rows), color=discord.Color.green())
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── /monthlyreport ────────────────────────────────────
    @app_commands.command(name="monthlyreport", description="Show monthly breakdown for a word")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="The word to check", user="User to check (leave empty for yourself)")
    async def monthlyreport(self, interaction: discord.Interaction, word: str, user: discord.Member = None):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not a tracked word.", ephemeral=True)
            return
        target = user or interaction.user
        data = load_data()
        entry = get_user_word(data, target.id, word)
        monthly = {}
        for day, cnt in entry["history"].items():
            monthly[day[:7]] = monthly.get(day[:7], 0) + cnt
        if not monthly:
            await interaction.response.send_message("No data yet!", ephemeral=True)
            return
        rows = [f"`{m}` — **{monthly[m]}**" for m in sorted(monthly.keys(), reverse=True)]
        embed = discord.Embed(title=f"📆 Monthly Report for `{word}`", description="\n".join(rows), color=discord.Color.orange())
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        embed.add_field(name="All Time", value=f"**{entry['total']}**", inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────
    @app_commands.command(name="leaderboard", description="Show top users for a tracked word")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="The word to rank")
    async def leaderboard(self, interaction: discord.Interaction, word: str):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not a tracked word.", ephemeral=True)
            return
        data = load_data()
        ranked = sorted([(uid, udata[word].get("total", 0)) for uid, udata in data.items() if word in udata and udata[word].get("total", 0) > 0], key=lambda x: x[1], reverse=True)[:10]
        if not ranked:
            await interaction.response.send_message("No data yet!", ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i] if i < 3 else f'`#{i+1}`'} <@{uid}> — **{total}**" for i, (uid, total) in enumerate(ranked)]
        embed = discord.Embed(title=f"🏆 Leaderboard for `{word}`", description="\n".join(lines), color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    # ── /resetcount ───────────────────────────────────────
    @app_commands.check(owner_only)
    @app_commands.command(name="resetcount", description="Reset count for a word")
    @app_commands.autocomplete(word=word_autocomplete)
    @app_commands.describe(word="The word to reset", user="User to reset (leave empty for yourself)")
    async def resetcount(self, interaction: discord.Interaction, word: str, user: discord.Member = None):
        words = load_words()
        if word not in words:
            await interaction.response.send_message(f"❌ `{word}` is not a tracked word.", ephemeral=True)
            return
        target = user or interaction.user
        data = load_data()
        uid = str(target.id)
        if uid in data and word in data[uid]:
            data[uid][word] = {"total": 0, "last_used": 0, "history": {}}
            save_data(data)
        await interaction.response.send_message(f"✅ Reset `{word}` count for {target.mention}.", ephemeral=True)


    # ════════════════════════════════════════════════════════
    # TEXT COMMANDS  (!o count, !o lb, !o history)
    # ════════════════════════════════════════════════════════

    # ── !o count ──────────────────────────────────────────
    # Shows all tracked words as paginated embeds, one word per page
    @commands.command(name="count")
    async def text_count(self, ctx, member: discord.Member = None):
        words = load_words()
        if not words:
            await ctx.send("No words are being tracked yet.")
            return

        target = member or ctx.author
        data = load_data()
        now_dt = datetime.now(timezone.utc)
        today = get_today()

        pages = []
        for word, cfg in sorted(words.items()):
            entry = get_user_word(data, target.id, word)
            daily   = entry["history"].get(today, 0)
            weekly  = sum(v for k, v in entry["history"].items() if (now_dt - datetime.strptime(k, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days < 7)
            monthly = sum(v for k, v in entry["history"].items() if k.startswith(now_dt.strftime("%Y-%m")))
            aliases = cfg.get("aliases", [])

            embed = discord.Embed(title=f"📊 `{word}`", color=discord.Color.blurple())
            embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
            embed.add_field(name="Today",    value=f"**{daily}**",          inline=True)
            embed.add_field(name="Weekly",   value=f"**{weekly}**",         inline=True)
            embed.add_field(name="Monthly",  value=f"**{monthly}**",        inline=True)
            embed.add_field(name="All Time", value=f"**{entry['total']}**", inline=True)
            if aliases:
                embed.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in aliases), inline=False)
            embed.set_footer(text=f"Cooldown: {cfg['cooldown']}s  •  Word {len(pages)+1}/{len(words)}")
            pages.append(embed)

        await self._paginate(ctx, pages)

    # ── !o lb ─────────────────────────────────────────────
    @commands.command(name="lb")
    async def text_leaderboard(self, ctx, *, word: str = None):
        words = load_words()
        if not words:
            await ctx.send("No words are being tracked yet.")
            return

        if word and word not in words:
            await ctx.send(f"❌ `{word}` is not a tracked word.")
            return

        data = load_data()
        pages = []
        word_list = [word] if word else sorted(words.keys())

        for w in word_list:
            ranked = sorted(
                [(uid, udata[w].get("total", 0)) for uid, udata in data.items() if w in udata and udata[w].get("total", 0) > 0],
                key=lambda x: x[1], reverse=True
            )[:10]
            medals = ["🥇", "🥈", "🥉"]
            lines = [f"{medals[i] if i < 3 else f'`#{i+1}`'} <@{uid}> — **{total}**" for i, (uid, total) in enumerate(ranked)] if ranked else ["No data yet!"]
            embed = discord.Embed(title=f"🏆 Leaderboard — `{w}`", description="\n".join(lines), color=discord.Color.gold())
            embed.set_footer(text=f"Word {word_list.index(w)+1}/{len(word_list)}")
            pages.append(embed)

        await self._paginate(ctx, pages)

    # ── !o history ────────────────────────────────────────
    @commands.command(name="history")
    async def text_history(self, ctx, word: str = None, days: int = 7):
        words = load_words()
        if not words:
            await ctx.send("No words are being tracked yet.")
            return

        if word and word not in words:
            await ctx.send(f"❌ `{word}` is not a tracked word.")
            return

        data = load_data()
        now_dt = datetime.now(timezone.utc)
        days = min(days, 30)
        pages = []
        word_list = [word] if word else sorted(words.keys())

        for w in word_list:
            entry = get_user_word(data, ctx.author.id, w)
            rows = []
            for i in range(days - 1, -1, -1):
                day = (now_dt - timedelta(days=i)).strftime("%Y-%m-%d")
                cnt = entry["history"].get(day, 0)
                rows.append(f"`{day}` {'█' * min(cnt, 20) if cnt else '—'} **{cnt}**")
            embed = discord.Embed(title=f"📅 {days}-Day History — `{w}`", description="\n".join(rows), color=discord.Color.green())
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.set_footer(text=f"Word {word_list.index(w)+1}/{len(word_list)}")
            pages.append(embed)

        await self._paginate(ctx, pages)

    # ── Pagination helper ─────────────────────────────────
    async def _paginate(self, ctx, pages: list):
        if not pages:
            await ctx.send("Nothing to show.")
            return
        if len(pages) == 1:
            await ctx.send(embed=pages[0])
            return

        current = 0

        class PaginationView(discord.ui.View):
            def __init__(self, author_id: int):
                super().__init__(timeout=60)
                self.author_id = author_id
                self.current = 0
                self.msg = None

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message("❌ These buttons aren't for you!", ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
            async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.current = (self.current - 1) % len(pages)
                await interaction.response.edit_message(embed=pages[self.current], view=self)

            @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
            async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.current = (self.current + 1) % len(pages)
                await interaction.response.edit_message(embed=pages[self.current], view=self)

            async def on_timeout(self):
                for child in self.children:
                    child.disabled = True
                try:
                    await self.msg.edit(view=self)
                except Exception:
                    pass

        view = PaginationView(ctx.author.id)
        msg = await ctx.send(embed=pages[0], view=view)
        view.msg = msg

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(str(error), ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Counter(bot))