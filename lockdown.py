import asyncio
import discord
from discord import app_commands
from discord.ext import commands

LOCKDOWN_MESSAGE = "🔒 **THE SERVER IS CURRENTLY IN A LOCKDOWN, BE PATIENT.**"

class Lockdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # speichert pro Channel: (ursprüngliche Permission-Overwrite, ursprünglicher Name)
        self._saved_state: dict[int, tuple[discord.PermissionOverwrite, str]] = {}

    @app_commands.command(name="lockdown", description="Sperrt den Server oder einen Channel")
    @app_commands.describe(channel="Optional: nur diesen Channel sperren (Standard: ganzer Server)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lockdown(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        guild = interaction.guild
        everyone = guild.default_role
        targets = [channel] if channel else guild.text_channels

        await interaction.response.defer(ephemeral=True)

        for ch in targets:
            overwrite = ch.overwrites_for(everyone)
            self._saved_state[ch.id] = (overwrite, ch.name)  # Original sichern (Rechte + Name)

            # @everyone das Schreiben (und Reagieren/Threads erstellen) verbieten
            overwrite.send_messages = False
            overwrite.create_public_threads = False
            overwrite.create_private_threads = False
            overwrite.add_reactions = False
            await ch.set_permissions(everyone, overwrite=overwrite)
            # Hinweis: Mitglieder mit "Administrator"-Berechtigung umgehen Channel-Overwrites
            # automatisch und können trotz der Sperre weiterhin schreiben.

            try:
                await ch.edit(name="lockdown")
            except discord.HTTPException:
                pass

            try:
                await ch.send(LOCKDOWN_MESSAGE)
            except discord.HTTPException:
                pass

            await asyncio.sleep(1)  # schont das Rate-Limit bei vielen Channels

        await interaction.followup.send(
            f"🔒 Lockdown aktiv für {'`' + channel.name + '`' if channel else 'den gesamten Server'}.",
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

        for ch in targets:
            saved = self._saved_state.pop(ch.id, None)

            if saved is not None:
                overwrite, original_name = saved
                await ch.set_permissions(everyone, overwrite=overwrite)
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
                await ch.set_permissions(everyone, overwrite=overwrite)

            await asyncio.sleep(1)

        await interaction.followup.send(
            f"🔓 Lockdown aufgehoben für {'`' + channel.name + '`' if channel else 'den gesamten Server'}.",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Lockdown(bot))
