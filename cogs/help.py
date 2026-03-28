import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger("cogs.help")


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all available commands")
    async def help_cmd(self, interaction: discord.Interaction):

        author_id = interaction.user.id

        class HelpView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.current = 0
                self.pages = []
                self.msg = None

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != author_id:
                    await interaction.response.send_message("❌ Not for you!", ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
            async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.current = (self.current - 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.pages[self.current], view=self)

            @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
            async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.current = (self.current + 1) % len(self.pages)
                await interaction.response.edit_message(embed=self.pages[self.current], view=self)

            async def on_timeout(self):
                for child in self.children:
                    child.disabled = True
                try:
                    await self.msg.edit(view=self)
                except Exception:
                    pass

        # ── Page 1: Channel Commands ───────────────────────
        p1 = discord.Embed(title="📖 Help — Channel Commands (5/5)", color=discord.Color.blurple())
        p1.add_field(name="🔒 All commands on this page are owner only", value="\u200b", inline=False)
        p1.add_field(
            name="/createchannels prefix [count] [category]",
            value=(
                "Create channels with a custom name or sequence.\n"
                "• No count → creates single channel with raw name\n"
                "• With count → creates `prefix-1`, `prefix-2`... auto-continuing from where existing channels left off\n"
                "• Category is autocompleted and auto-created if it doesn't exist"
            ),
            inline=False
        )
        p1.add_field(
            name="/deletechannels category",
            value="Delete all channels inside a category. Category name is autocompleted.",
            inline=False
        )
        p1.set_footer(text="Page 4/5 • Use ◀ ▶ to navigate")

        # ── Page 2: Counter — Everyone ────────────────────
        p2 = discord.Embed(title="📖 Help — Counter Stats (1/5)", color=discord.Color.blurple())
        p2.add_field(name="/listwords", value="Show all tracked words, their cooldowns and aliases.", inline=False)
        p2.add_field(name="/count word [@user]", value="Today / weekly / monthly / all-time stats for a word.", inline=False)
        p2.add_field(name="/history word [@user] [days]", value="Day-by-day bar chart. Default 7 days, max 30.", inline=False)
        p2.add_field(name="/monthlyreport word [@user]", value="Month-by-month breakdown with all-time total.", inline=False)
        p2.add_field(name="/leaderboard word", value="Top 10 users for a tracked word.", inline=False)
        p2.add_field(name="/pausetracking pause|resume", value="Pause or resume word tracking for yourself. While paused your messages are silently ignored.", inline=False)
        p2.add_field(name="─── Text Commands (prefix: `!o`) ───", value="\u200b", inline=False)
        p2.add_field(name="!o count [@user]", value="Paginated stats for all tracked words, one word per page.", inline=False)
        p2.add_field(name="!o lb [word]", value="Leaderboard — all words paginated, or a specific one.", inline=False)
        p2.add_field(name="!o history [word] [days]", value="Day-by-day history — all words or a specific one.", inline=False)
        p2.set_footer(text="Page 1/5 • Use ◀ ▶ to navigate")

        # ── Page 3: Counter — Owner Only ──────────────────
        p3 = discord.Embed(title="📖 Help — Counter Management (3/5)", color=discord.Color.blurple())
        p3.add_field(name="🔒 All commands on this page are owner only", value="\u200b", inline=False)
        p3.add_field(name="/addword word cooldown", value="Start tracking a word with a per-user cooldown in seconds.", inline=False)
        p3.add_field(name="/addalias word alias", value="Add an alternate word/phrase that counts towards a tracked word. Supports multi-word aliases.", inline=False)
        p3.add_field(name="/removealias word alias", value="Remove an alias from a tracked word.", inline=False)
        p3.add_field(name="/removeword word", value="Stop tracking a word. History is kept.", inline=False)
        p3.add_field(name="/deleteword word", value="Stop tracking and permanently wipe all history for a word.", inline=False)
        p3.add_field(name="/resetcount word [@user]", value="Reset a user's count for a word. Leave user empty to reset yourself.", inline=False)
        p3.add_field(name="/servertracking pause|resume", value="Pause or resume word tracking for the entire server.", inline=False)
        p3.add_field(name="/blacklistchannel #channel add|remove", value="Add or remove a channel from the blacklist. Messages in blacklisted channels are never counted.", inline=False)
        p3.add_field(name="/listblacklist", value="Show server tracking status and all blacklisted channels.", inline=False)
        p3.set_footer(text="Page 3/5 • Use ◀ ▶ to navigate")

        # ── Page 4: Huntbot — Everyone ────────────────────
        p4 = discord.Embed(title="📖 Help — Huntbot Reminder (2/5)", color=discord.Color.blurple())
        p4.add_field(
            name="/huntbot on",
            value=(
                "Enable huntbot reminders for yourself.\n"
                "Prompts you to choose your reminder mode:\n"
                "• 📩 DM only\n"
                "• 📣 Ping in server only\n"
                "• 📩📣 Both"
            ),
            inline=False
        )
        p4.add_field(name="/huntbot off", value="Disable huntbot reminders for yourself.", inline=False)
        p4.add_field(
            name="⏰ Auto-detection",
            value=(
                "When OwO Bot sends a huntbot message, the bot automatically:\n"
                "• Reacts with ⏰ on the message — click the reaction to see the exact return time as a Discord timestamp\n"
                "• If you're subscribed → silently schedules your reminder\n"
                "• If you're not subscribed → prompts you to enable with `/huntbot on`\n"
                "• Click **🔕 Don't ask me again** to silence future prompts"
            ),
            inline=False
        )
        p4.set_footer(text="Page 2/5 • Use ◀ ▶ to navigate")

        # ── Page 5: Huntbot — Owner Only ──────────────────
        p5 = discord.Embed(title="📖 Help — Huntbot Management (4/5)", color=discord.Color.blurple())
        p5.add_field(name="🔒 All commands on this page are owner only", value="\u200b", inline=False)
        p5.add_field(
            name="/huntbotstatus",
            value=(
                "See everyone's reminder status in the server.\n"
                "Shows three groups:\n"
                "• ✅ Opted in — name + their reminder mode\n"
                "• ❌ Opted out — disabled reminders\n"
                "• 🔕 Muted — clicked 'Don't ask me again'"
            ),
            inline=False
        )
        p5.set_footer(text="Page 4/5 • Use ◀ ▶ to navigate")

        view = HelpView()
        view.pages = [p2, p4, p3, p5, p1]
        await interaction.response.send_message(embed=p1, view=view)
        view.msg = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(Help(bot))