import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # user_id -> Anzahl Nachrichten
        self.message_counts = defaultdict(int)
        # user_id -> Anzahl erfolgreicher Invites (Leute, die über seinen Link beigetreten sind)
        self.invite_counts = defaultdict(int)
        # guild_id -> {invite_code: uses}  (Cache, um Differenzen zu erkennen)
        self.invite_cache = {}

    # ---------- Setup: beim Start alle aktuellen Invites cachen + rückwirkend zählen ----------
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                invites = await guild.invites()
                self.invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}

                # Rückwirkend zählen: jeder Invite trägt seine gesamte bisherige "uses"-Zahl
                # dem Ersteller gut, auch aus der Zeit vor dem Bot-Start.
                for inv in invites:
                    if inv.inviter and inv.uses:
                        self.invite_counts[inv.inviter.id] += inv.uses

            except discord.Forbidden:
                print(f"Keine Berechtigung, Invites in '{guild.name}' zu lesen (Manage Guild fehlt).")

    # ---------- Nachrichten zählen ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        self.message_counts[message.author.id] += 1

    # ---------- Neuen Invite cachen, sobald er erstellt wird ----------
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        self.invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses

    # ---------- Beim Beitritt herausfinden, welcher Invite benutzt wurde ----------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        try:
            new_invites = await guild.invites()
        except discord.Forbidden:
            return

        old_invites = self.invite_cache.get(guild.id, {})

        used_invite = None
        for inv in new_invites:
            old_uses = old_invites.get(inv.code, 0)
            if inv.uses is not None and inv.uses > old_uses:
                used_invite = inv
                break

        # Cache aktualisieren
        self.invite_cache[guild.id] = {inv.code: inv.uses for inv in new_invites}

        if used_invite and used_invite.inviter:
            self.invite_counts[used_invite.inviter.id] += 1

    # ---------- /stats Command ----------
    @app_commands.command(name="stats", description="Zeigt Nachrichten- und Invite-Statistik eines Users")
    async def stats(self, interaction: discord.Interaction, user: discord.User = None):
        target = user or interaction.user

        messages = self.message_counts.get(target.id, 0)
        invites = self.invite_counts.get(target.id, 0)

        embed = discord.Embed(
            title=target.display_name,
            color=discord.Color.from_rgb(147, 112, 219)
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Nachrichten", value=str(messages), inline=True)
        embed.add_field(name="Invites", value=str(invites), inline=True)

        await interaction.response.send_message(embed=embed)

    # ---------- /stats_backfill: zählt alte Nachrichten aus der Kanalhistorie nach ----------
    @app_commands.command(name="stats_backfill", description="Zählt alte Nachrichten in allen Kanälen nach (einmalig, kann dauern)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stats_backfill(self, interaction: discord.Interaction):
        await interaction.response.send_message("Starte Backfill – das kann je nach Servergröße einige Minuten dauern...", ephemeral=True)

        guild = interaction.guild
        total_counted = 0
        skipped_channels = []

        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if not perms.read_message_history:
                skipped_channels.append(channel.name)
                continue

            try:
                async for message in channel.history(limit=None):
                    if not message.author.bot:
                        self.message_counts[message.author.id] += 1
                        total_counted += 1
            except discord.Forbidden:
                skipped_channels.append(channel.name)

        summary = f"Backfill abgeschlossen. {total_counted} Nachrichten nachgezählt."
        if skipped_channels:
            summary += f"\nÜbersprungen (keine Berechtigung): {', '.join(skipped_channels)}"

        await interaction.followup.send(summary, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Stats(bot))