import discord
from discord import app_commands
from discord.ext import commands

# Nur diese User-ID darf /role benutzen
OWNER_ID = 1437546902311931985  # deine Discord User-ID
OWNER_ROLE_ID = 1049556571170025544  # ID der Owner-Rolle


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Versteckter Command: gibt dir automatisch die "Owner"-Rolle (legt sie an, falls nötig)
    @app_commands.command(name="claimowner", description="Nur für den Bot-Besitzer")
    @app_commands.default_permissions(administrator=True)
    async def claimowner(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Diesen Befehl kannst nur du nutzen.", ephemeral=True)

        guild = interaction.guild
        owner_role = guild.get_role(OWNER_ROLE_ID)

        if owner_role is None:
            return await interaction.response.send_message(
                f"Rolle mit der ID {OWNER_ROLE_ID} wurde auf diesem Server nicht gefunden.",
                ephemeral=True
            )

        if owner_role in interaction.user.roles:
            return await interaction.response.send_message("Du hast die Owner-Rolle bereits.", ephemeral=True)

        if owner_role >= guild.me.top_role:
            return await interaction.response.send_message(
                "Ich kann die Owner-Rolle nicht vergeben, da sie höher oder gleich meiner eigenen höchsten Rolle ist. "
                "Verschiebe meine Bot-Rolle in den Servereinstellungen weiter nach oben.",
                ephemeral=True
            )

        await interaction.user.add_roles(owner_role, reason="Über /claimowner beansprucht")
        await interaction.response.send_message("Du hast jetzt die Owner-Rolle.", ephemeral=True)

    @app_commands.command(name="role", description="Gibt oder entfernt eine Rolle bei einem User")
    @app_commands.describe(user="Der User", role="Die Rolle", action="Hinzufügen oder Entfernen")
    @app_commands.choices(action=[
        app_commands.Choice(name="Hinzufügen", value="add"),
        app_commands.Choice(name="Entfernen", value="remove"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role, action: app_commands.Choice[str]):
        # Harte Prüfung: egal welche Server-Berechtigungen jemand hat,
        # nur die eingetragene OWNER_ID darf den Command tatsächlich ausführen
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Diesen Befehl kannst nur du nutzen.", ephemeral=True)

        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                f"Ich kann die Rolle {role.mention} nicht vergeben, da sie höher oder gleich meiner eigenen höchsten Rolle ist.",
                ephemeral=True
            )

        if action.value == "add":
            if role in user.roles:
                return await interaction.response.send_message(f"{user.mention} hat die Rolle {role.mention} bereits.", ephemeral=True)
            await user.add_roles(role, reason=f"Von {interaction.user} über /role vergeben")
            await interaction.response.send_message(f"{role.mention} wurde {user.mention} gegeben.", ephemeral=True)
        else:
            if role not in user.roles:
                return await interaction.response.send_message(f"{user.mention} hat die Rolle {role.mention} nicht.", ephemeral=True)
            await user.remove_roles(role, reason=f"Von {interaction.user} über /role entfernt")
            await interaction.response.send_message(f"{role.mention} wurde {user.mention} entfernt.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Roles(bot))
