import discord
from discord import app_commands
from discord.ext import commands
import re
from utils import owner_only


async def category_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=cat.name, value=cat.name)
        for cat in interaction.guild.categories
        if current.lower() in cat.name.lower()
    ]


def find_next_index(guild: discord.Guild, prefix: str) -> int:
    existing = set()
    for channel in guild.channels:
        match = re.fullmatch(re.escape(prefix) + r"-(\d+)", channel.name, re.IGNORECASE)
        if match:
            existing.add(int(match.group(1)))
    return max(existing) + 1 if existing else 1


def build_copyable(user_id: int, ids: list[int]) -> str:
    ids_lines = ",\n".join(f"                    {cid}" for cid in ids)
    return (
        "```\n"
        f'                "userid": {user_id},\n'
        f'                "channels": [\n'
        f'{ids_lines}\n'
        f'                ]\n'
        "```"
    )


class Channels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.check(owner_only)
    @app_commands.command(name="createchannels", description="Create channels with a custom name or numbered sequence")
    @app_commands.autocomplete(category=category_autocomplete)
    @app_commands.describe(
        prefix="Channel name or prefix (e.g. 'owo' → creates owo, or owo-13 if owo-1..12 exist)",
        count="How many channels to create (leave empty to create just one with the raw name)",
        category="Pick an existing category or type a new name to create one"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def createchannels(
        self,
        interaction: discord.Interaction,
        prefix: str,
        count: app_commands.Range[int, 1, 50] = None,
        category: str = None
    ):
        await interaction.response.defer()
        guild = interaction.guild

        target_category = None
        if category:
            target_category = discord.utils.get(guild.categories, name=category)
            if target_category is None:
                try:
                    target_category = await guild.create_category(category)
                    await interaction.followup.send(f"📁 Category **{category}** didn't exist — created it!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send(f"❌ No permission to create category **{category}**.", ephemeral=True)

        # No count = single channel with raw name
        if count is None:
            try:
                channel = await guild.create_text_channel(prefix, category=target_category)
                embed = discord.Embed(title="✅ Channel Created", color=discord.Color.green())
                embed.add_field(name="📋 Channel ID", value=str(channel.id), inline=False)
                embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                await interaction.followup.send(embed=embed)
                await interaction.followup.send(build_copyable(interaction.user.id, [channel.id]))
            except discord.Forbidden:
                await interaction.followup.send("❌ Missing permission to create channels.", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)
            return

        # Smart index
        start = find_next_index(guild, prefix)
        if start > 1:
            await interaction.followup.send(
                f"ℹ️ Found existing `{prefix}-*` channels — continuing from `{prefix}-{start}`.",
                ephemeral=True
            )

        progress_msg = await interaction.followup.send(f"⏳ Creating **{count}** channels starting from `{prefix}-{start}`...")
        created, failed = [], []

        for i in range(start, start + count):
            name = f"{prefix}-{i}"
            try:
                channel = await guild.create_text_channel(name, category=target_category)
                created.append((channel.name, channel.id))
            except discord.Forbidden:
                failed.append(name)
            except discord.HTTPException as e:
                failed.append(f"{name} ({e})")

        # Page 1: summary embed with IDs
        embed = discord.Embed(
            title="✅ Channel Creation Complete",
            color=discord.Color.green() if not failed else discord.Color.orange()
        )
        embed.add_field(name="📊 Summary", value=f"Created: **{len(created)}/{count}**", inline=False)

        if created:
            channel_lines = [str(cid) for _, cid in created]
            chunks, chunk = [], ""
            for line in channel_lines:
                if len(chunk) + len(line) + 1 > 1020:
                    chunks.append(chunk)
                    chunk = line
                else:
                    chunk += ("\n" if chunk else "") + line
            if chunk:
                chunks.append(chunk)
            for idx, chunk in enumerate(chunks):
                embed.add_field(name="📋 Channel IDs" if idx == 0 else "📋 Channel IDs (cont.)", value=chunk, inline=False)

        if failed:
            embed.add_field(name="❌ Failed", value="\n".join(failed), inline=False)

        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await progress_msg.edit(content=None, embed=embed)

        # Page 2: copyable formatted block
        if created:
            ids = [cid for _, cid in created]
            await interaction.followup.send(build_copyable(interaction.user.id, ids))

    @app_commands.check(owner_only)
    @app_commands.command(name="deletechannels", description="Delete all channels inside a category")
    @app_commands.autocomplete(category=category_autocomplete)
    @app_commands.describe(category="The category whose channels you want to delete")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def deletechannels(self, interaction: discord.Interaction, category: str):
        await interaction.response.defer()
        guild = interaction.guild
        target_category = discord.utils.get(guild.categories, name=category)

        if target_category is None:
            await interaction.followup.send(f"❌ Category **{category}** not found.", ephemeral=True)
            return

        channels = target_category.channels
        if not channels:
            await interaction.followup.send(f"⚠️ Category **{category}** has no channels.", ephemeral=True)
            return

        progress_msg = await interaction.followup.send(f"⏳ Deleting **{len(channels)}** channels in `{category}`...")
        deleted, failed = [], []

        for channel in channels:
            try:
                await channel.delete()
                deleted.append(channel.name)
            except discord.Forbidden:
                failed.append(channel.name)
            except discord.HTTPException as e:
                failed.append(f"{channel.name} ({e})")

        embed = discord.Embed(
            title="🗑️ Channel Deletion Complete",
            color=discord.Color.red() if failed else discord.Color.green()
        )
        embed.add_field(name="📊 Summary", value=f"Deleted: **{len(deleted)}/{len(channels)}** in `{category}`", inline=False)
        if deleted:
            embed.add_field(name="✅ Deleted", value="\n".join(f"`#{n}`" for n in deleted), inline=False)
        if failed:
            embed.add_field(name="❌ Failed", value="\n".join(failed), inline=False)
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await progress_msg.edit(content=None, embed=embed)

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(str(error), ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need the **Manage Channels** permission.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Channels(bot))