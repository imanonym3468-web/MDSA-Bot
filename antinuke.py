import time
import asyncio
from collections import deque
import discord
from discord import app_commands
from discord.ext import commands

# ---- Einstellungen ----
TIME_WINDOW_SECONDS = 60    # Fenster, in dem Löschungen für die Statistik gezählt werden
LOG_CHANNEL_ID = 0          # <-- HIER die ID deines Log/Alert-Channels eintragen


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._deletes: dict[int, deque[float]] = {}
        self._raid_active: dict[int, bool] = {}

    # ==================================================================
    # SOFORTMASSNAHME: reagiert auf den ALLERERSTEN gelöschten Channel
    # ==================================================================
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        now = time.time()

        deletes = self._deletes.setdefault(guild.id, deque())
        deletes.append(now)
        while deletes and now - deletes[0] > TIME_WINDOW_SECONDS:
            deletes.popleft()

        # Kritischer Pfad: NUR beim ersten Mal auslösen, dann sofort
        # Kick + Lockdown parallel als Tasks starten — nichts davor abwarten.
        if not self._raid_active.get(guild.id, False):
            self._raid_active[guild.id] = True
            asyncio.create_task(self._kick_all_bots(guild))
            asyncio.create_task(self._lock_all_channels(guild))

        # Alles Weitere (wer war's, Logging) ist NICHT zeitkritisch und
        # läuft separat im Hintergrund, blockiert den kritischen Pfad nicht.
        asyncio.create_task(self._log_incident(guild, channel, len(deletes)))

    # ==================================================================
    # Kick aller fremden Bots — höchste Priorität, maximal parallel
    # ==================================================================
    async def _kick_all_bots(self, guild: discord.Guild):
        targets = [
            m for m in guild.members
            if m.bot and m.id != self.bot.user.id
        ]
        if not targets:
            return

        async def kick_one(member: discord.Member):
            try:
                await guild.kick(member, reason="Anti-Nuke: Channel-Löschung erkannt — Sofort-Kick")
                return member, True
            except (discord.Forbidden, discord.HTTPException):
                return member, False

        results = await asyncio.gather(*(kick_one(m) for m in targets))
        kicked = [m for m, ok in results if ok]
        failed = [m for m, ok in results if not ok]

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            msg = f"⚡ Sofort-Kick: {len(kicked)}/{len(targets)} fremde Bots entfernt."
            if failed:
                msg += f"\n❌ Fehlgeschlagen (Rollen-Hierarchie/Rechte prüfen): {', '.join(str(m) for m in failed)}"
            try:
                await log_channel.send(msg)
            except discord.HTTPException:
                pass

    # ==================================================================
    # Server-Lockdown — parallel zum Kick, nicht danach
    # ==================================================================
    async def _lock_all_channels(self, guild: discord.Guild):
        lockdown_cog = self.bot.get_cog("Lockdown")
        if lockdown_cog is None:
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                try:
                    await log_channel.send("⚠️ Lockdown-Cog nicht gefunden — Lockdown übersprungen.")
                except discord.HTTPException:
                    pass
            return

        everyone = guild.default_role
        await asyncio.gather(
            *(lockdown_cog._lock_channel(ch, everyone) for ch in guild.text_channels),
            return_exceptions=True,
        )

    # ==================================================================
    # Logging + Verursacher-Identifikation — NICHT zeitkritisch
    # ==================================================================
    async def _log_incident(self, guild: discord.Guild, channel: discord.abc.GuildChannel, delete_count: int):
        culprit = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
                if entry.target and entry.target.id == channel.id:
                    culprit = entry.user
                    break
        except discord.Forbidden:
            pass

        ban_success = False
        if culprit:
            try:
                await guild.ban(culprit, reason="Anti-Nuke: Channel-Löschung", delete_message_seconds=0)
                ban_success = True
            except (discord.Forbidden, discord.HTTPException):
                pass

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            return

        embed = discord.Embed(
            title="🚨 Raid erkannt",
            description=(
                f"**{delete_count} Channels** gelöscht (Fenster: {TIME_WINDOW_SECONDS}s).\n"
                f"Verursacher: {culprit.mention if culprit else 'unbekannt'} (`{culprit}`)\n"
                f"Bann Verursacher: {'✅' if ban_success else '❌'}\n"
                f"Sofort-Kick aller Bots + Lockdown wurden bereits ausgelöst."
            ),
            color=discord.Color.red()
        )
        try:
            await log_channel.send(embed=embed)
        except discord.HTTPException:
            pass

    def reset_raid_status(self, guild_id: int):
        """Von /unlock aufrufen, um den Raid-Status zurückzusetzen."""
        self._raid_active[guild_id] = False
        self._deletes[guild_id] = deque()

    # ==================================================================
    # Manueller Trigger: "!nuke" im Chat -> alle fremden Bots BANNEN
    # ==================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user or message.guild is None:
            return

        if message.content.strip().lower() == "!nuke":
            guild = message.guild
            targets = [m for m in guild.members if m.bot and m.id != self.bot.user.id]

            async def ban_one(member: discord.Member):
                try:
                    await guild.ban(member, reason="Anti-Nuke: '!nuke'-Trigger", delete_message_seconds=0)
                    return member, True
                except (discord.Forbidden, discord.HTTPException):
                    return member, False

            results = await asyncio.gather(*(ban_one(m) for m in targets))
            banned = [m for m, ok in results if ok]
            failed = [m for m, ok in results if not ok]

            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            embed = discord.Embed(
                title="🚨 '!nuke' erkannt — alle Bots gebannt",
                description=(
                    f"Ausgelöst von: {message.author.mention} in {message.channel.mention}\n"
                    f"Gebannt: {len(banned)}/{len(targets)}"
                    + (f"\n❌ Fehlgeschlagen: {', '.join(str(m) for m in failed)}" if failed else "")
                ),
                color=discord.Color.red()
            )
            if log_channel:
                try:
                    await log_channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    # ==================================================================
    # /defense-status
    # ==================================================================
    @app_commands.command(name="defense-status", description="Zeigt, ob der Anti-Nuke-Schutz einsatzbereit ist")
    async def defense_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        bot_member = guild.me

        checks: list[tuple[str, bool, str]] = []

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        checks.append(("Log-Channel konfiguriert", log_channel is not None,
                        f"#{log_channel.name}" if log_channel else "LOG_CHANNEL_ID nicht gesetzt"))

        checks.append(("Kick-Berechtigung", bot_member.guild_permissions.kick_members,
                        "vorhanden" if bot_member.guild_permissions.kick_members else "fehlt — Sofort-Kick wird fehlschlagen"))

        checks.append(("Bann-Berechtigung", bot_member.guild_permissions.ban_members,
                        "vorhanden" if bot_member.guild_permissions.ban_members else "fehlt — Bann des Verursachers wird fehlschlagen"))

        checks.append(("Audit-Log-Zugriff", bot_member.guild_permissions.view_audit_log,
                        "vorhanden" if bot_member.guild_permissions.view_audit_log else "fehlt — Verursacher kann nicht identifiziert werden"))

        checks.append(("Channel-Verwaltung (Lockdown)", bot_member.guild_permissions.manage_channels,
                        "vorhanden" if bot_member.guild_permissions.manage_channels else "fehlt — Lockdown wird fehlschlagen"))

        lockdown_cog = self.bot.get_cog("Lockdown")
        checks.append(("Lockdown-Cog geladen", lockdown_cog is not None,
                        "geladen" if lockdown_cog else "nicht geladen"))

        high_role = bot_member.top_role.position >= (len(guild.roles) - 3)
        checks.append(("Bot-Rolle hoch genug", high_role,
                        f"Position {bot_member.top_role.position}/{len(guild.roles) - 1}"
                        + ("" if high_role else " — evtl. zu niedrig")))

        all_ready = all(ok for _, ok, _ in checks)
        raid_status = self._raid_active.get(guild.id, False)

        embed = discord.Embed(
            title="🛡️ Anti-Nuke Defense Status",
            description=f"**Gesamtstatus: {'✅ Einsatzbereit' if all_ready else '⚠️ Nicht vollständig einsatzbereit'}**",
            color=discord.Color.green() if all_ready else discord.Color.orange()
        )
        for name, ok, detail in checks:
            embed.add_field(name=f"{'✅' if ok else '❌'} {name}", value=detail, inline=False)
        embed.add_field(
            name="🚦 Aktueller Raid-Status",
            value="🔴 AKTIV" if raid_status else "🟢 Normal",
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
