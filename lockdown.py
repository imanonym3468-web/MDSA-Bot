import asyncio
import discord
from discord import app_commands
from discord.ext import commands

LOCKDOWN_MESSAGE = "🔒 **THE SERVER IS CURRENTLY IN A LOCKDOWN, BE PATIENT.**"


class Lockdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._saved_state: dict[int, tuple[discord.PermissionOverwrite, str]] = {}

    async def _lock_channel(self, ch: discord.TextChannel, everyone: discord.Role):
        overwrite = ch.overwrites_for(everyone)
        self._saved_state[ch.id] = (overwrite, ch.name)
        overwrite.send_messages = False
        overwrite.create_public_threads = False
        overwrite.create_private_threads = False
        overwrite.add_reactions = False
        try:
            await ch.set_permissions(everyone, overwrite=overwrite)
        except discord.HTTPException:
            pass
        try:
            await ch.edit(name="lockdown")
        except discord.HTTPException:
            pass
        try:
            await ch.send(LOCKDOWN_MESSAGE)
        except discord.HTTPException:
            pass

    async def _unlock_channel(self, ch: discord.TextChannel, everyone: discord.Role):
        saved = self._saved_state.pop(ch.id, None)
        if saved is not None:
            overwrite, original_name = saved
            try:
                await ch.set_permissions(everyone, overwrite=overwrite)
            except discord.HTTPException:
                pass
            try:
                if ch.name != original_name:
                    await ch.edit(name=original_name)
            except discord.HTTPException:
                pass
        else:
            overwrite = ch.overwrites_for(everyone)
            overwrite.send_messages = None
            overwrite.create_public_threads = None
            overwrite.create_private_threads = None
            overwrite.add_reactions = None
            try:
                await ch.set_permissions(everyone, overwrite=overwrite)
            except discord.HTTPException:
                pass

    @app_commands.command(name="lockdown", description="Sperrt den Server oder einen Channel")
    @app_commands.describe(channel="Optional: nur diesen Channel sperren (Standard: ganzer Server)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lockdown(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        guild = interaction.guild
        everyone = guild.default_role
        targets = [channel] if channel else guild.text_channels
        await interaction.response.defer(ephemeral=True)

        await asyncio.gather(*(self._lock_channel(ch, everyone) for ch in targets))

        # Kontaminiert-Rolle nur bei Server-weitem Lockdown vergeben (nicht bei Einzel-Channel)
        role_note = ""
        if channel is None:
            anti_nuke_cog = self.bot.get_cog("AntiNuke")
            if anti_nuke_cog and hasattr(anti_nuke_cog, "_apply_contaminated_roles"):
                await anti_nuke_cog._apply_contaminated_roles(guild)
                role_note = " Alle Member haben die Rolle `Kontaminiert` erhalten."

        await interaction.followup.send(
            f"🔒 Lockdown aktiv für {'`' + channel.name + '`' if channel else 'den gesamten Server'}."
            f"{role_note}",
            ephemeral=True
        )

    @app_commands.command(name="unlock", description="Hebt den Lockdown wieder auf")
    @app_commands.describe(channel="Optional: nur diesen Channel entsperren")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        guild = interaction.guild
        everyone = guild.default_role
        targets = [channel] if channel else guild.text_channels
        await interaction.response.defer(ephemeral=True)

        await asyncio.gather(*(self._unlock_channel(ch, everyone) for ch in targets))

        # Rollen nur bei Server-weitem Unlock wiederherstellen (nicht bei Einzel-Channel)
        role_note = ""
        if channel is None:
            anti_nuke_cog = self.bot.get_cog("AntiNuke")
            if anti_nuke_cog and hasattr(anti_nuke_cog, "_restore_roles"):
                await anti_nuke_cog._restore_roles(guild)
                if hasattr(anti_nuke_cog, "reset_raid_status"):
                    anti_nuke_cog.reset_raid_status(guild.id)
                role_note = " Alle Rollen wurden wiederhergestellt."

        await interaction.followup.send(
            f"🔓 Lockdown aufgehoben für {'`' + channel.name + '`' if channel else 'den gesamten Server'}."
            f"{role_note}",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Lockdown(bot))
