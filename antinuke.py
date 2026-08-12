import time
import asyncio
from collections import deque
import discord
from discord import app_commands
from discord.ext import commands

# ---- Einstellungen ----
DELETE_THRESHOLD = 2        # Anzahl gelöschter Channels...
TIME_WINDOW_SECONDS = 60    # ...innerhalb dieser Zeitspanne löst Lockdown + Ban aus
LOG_CHANNEL_ID = 0          # <-- HIER die ID deines Log/Alert-Channels eintragen


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._deletes: dict[int, deque[float]] = {}
        self._raid_active: dict[int, bool] = {}

    # ---------- Erkennung: mehrere Channel-Löschungen ----------
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        now = time.time()

        culprit = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
                if entry.target and entry.target.id == channel.id:
                    culprit = entry.user
                    break
        except discord.Forbidden:
            pass

        deletes = self._deletes.setdefault(guild.id, deque())
        deletes.append((now, culprit))

        while deletes and now - deletes[0][0] > TIME_WINDOW_SECONDS:
            deletes.popleft()

        if len(deletes) >= DELETE_THRESHOLD and not self._raid_active.get(guild.id, False):
            self._raid_active[guild.id] = True
            latest_culprit = deletes[-1][1]
            await self._trigger_raid_response(guild, len(deletes), latest_culprit)

    async def _trigger_raid_response(self, guild: discord.Guild, delete_count: int, culprit: discord.abc.User | None):
        log_channel = guild.get_channel(LOG_CHANNEL_ID)

        ban_success = False
        ban_error = None
        if culprit:
            try:
                await guild.ban(culprit, reason="Anti-Nuke: Mehrfaches Löschen von Channels erkannt", delete_message_seconds=0)
                ban_success = True
            except discord.Forbidden as e:
                ban_error = f"Forbidden (Rollen-Hierarchie oder fehlende Berechtigung): {e}"
            except discord.HTTPException as e:
                ban_error = f"HTTPException: {e}"

        embed = discord.Embed(
            title="🚨 Raid erkannt — Server gesperrt!",
            description=(
                f"**{delete_count} Channels** wurden innerhalb von {TIME_WINDOW_SECONDS} Sekunden gelöscht.\n"
                f"Verursacher: {culprit.mention if culprit else 'unbekannt'} (`{culprit}`)\n"
                f"Bann: {'✅ erfolgreich' if ban_success else '❌ fehlgeschlagen'}"
                + (f"\nFehler: `{ban_error}`" if ban_error else "")
            ),
            color=discord.Color.red()
        )
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except discord.HTTPException:
                pass

        lockdown_cog = self.bot.get_cog("Lockdown")
        if lockdown_cog is None:
            if log_channel:
                await log_channel.send("⚠️ Lockdown-Cog nicht gefunden — automatischer Lockdown fehlgeschlagen.")
            return

        everyone = guild.default_role
        targets = guild.text_channels
        await asyncio.gather(*(lockdown_cog._lock_channel(ch, everyone) for ch in targets))

        if log_channel:
            await log_channel.send("🔒 Server automatisch gesperrt. Nutze `/unlock`, sobald alles geklärt ist.")

    def reset_raid_status(self, guild_id: int):
        """Wird z.B. von /unlock aufgerufen, um den Raid-Status zurückzusetzen."""
        self._raid_active[guild_id] = False
        self._deletes[guild_id] = deque()

    # ---------- Erkennung: "!nuke" im Chat -> alle fremden Bots bannen ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.guild is None:
            return

        if message.content.strip().lower() == "!nuke":
            guild = message.guild
            log_channel = guild.get_channel(LOG_CHANNEL_ID)

            bots_to_ban = [
                member for member in guild.members
                if member.bot and member.id != self.bot.user.id
            ]

            banned = []
            failed = []
            for bot_member in bots_to_ban:
                try:
                    await guild.ban(bot_member, reason="Anti-Nuke: '!nuke'-Trigger erkannt", delete_message_seconds=0)
                    banned.append(bot_member)
                except discord.Forbidden:
                    failed.append(bot_member)
                except discord.HTTPException:
                    failed.append(bot_member)

            embed = discord.Embed(
                title="🚨 '!nuke' erkannt — alle Bots gebannt",
                description=(
                    f"Ausgelöst von: {message.author.mention} (`{message.author}`) in {message.channel.mention}\n"
                    f"Gebannt: {len(banned)}\n"
                    f"Fehlgeschlagen: {len(failed)}"
                    + (f"\n⚠️ Konnte nicht gebannt werden: {', '.join(str(b) for b in failed)}" if failed else "")
                ),
                color=discord.Color.red()
            )
            if log_channel:
                try:
                    await log_channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    # ---------- Status-Check ----------
    @app_commands.command(name="defense-status", description="Zeigt, ob der Anti-Nuke-Schutz einsatzbereit ist")
    async def defense_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        bot_member = guild.me

        checks: list[tuple[str, bool, str]] = []

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        checks.append((
            "Log-Channel konfiguriert",
            log_channel is not None,
            f"#{log_channel.name}" if log_channel else "LOG_CHANNEL_ID nicht gesetzt oder ungültig"
        ))

        can_view_audit = bot_member.guild_permissions.view_audit_log
        checks.append((
            "Audit-Log-Zugriff",
            can_view_audit,
            "vorhanden" if can_view_audit else "fehlt — Bot kann Verursacher nicht identifizieren"
        ))

        can_ban = bot_member.guild_permissions.ban_members
        checks.append((
            "Bann-Berechtigung",
            can_ban,
            "vorhanden" if can_ban else "fehlt — Bot kann niemanden bannen"
        ))

        can_manage_channels = bot_member.guild_permissions.manage_channels
        checks.append((
            "Channel-Verwaltung (für Lockdown)",
            can_manage_channels,
            "vorhanden" if can_manage_channels else "fehlt — automatischer Lockdown wird fehlschlagen"
        ))

        lockdown_cog = self.bot.get_cog("Lockdown")
        checks.append((
            "Lockdown-Cog geladen",
            lockdown_cog is not None,
            "geladen" if lockdown_cog else "nicht geladen — auf 'lockdown' Extension prüfen"
        ))

        high_role = bot_member.top_role.position >= (len(guild.roles) - 3)
        checks.append((
            "Bot-Rolle hoch genug",
            high_role,
            f"Position {bot_member.top_role.position}/{len(guild.roles) - 1}"
            + ("" if high_role else " — evtl. zu niedrig, Bann könnte bei hochrangigen Accounts scheitern")
        ))

        all_ready = all(ok for _, ok, _ in checks)
        raid_status = self._raid_active.get(guild.id, False)

        embed = discord.Embed(
            title="🛡️ Anti-Nuke Defense Status",
            description=f"**Gesamtstatus: {'✅ Einsatzbereit' if all_ready else '⚠️ Nicht vollständig einsatzbereit'}**",
            color=discord.Color.green() if all_ready else discord.Color.orange()
        )

        for name, ok, detail in checks:
            emoji = "✅" if ok else "❌"
            embed.add_field(name=f"{emoji} {name}", value=detail, inline=False)

        embed.add_field(
            name="🚦 Aktueller Raid-Status",
            value="🔴 AKTIV (Lockdown ausgelöst)" if raid_status else "🟢 Normal",
            inline=False
        )
        embed.set_footer(text=f"Schwelle: {DELETE_THRESHOLD} gelöschte Channels in {TIME_WINDOW_SECONDS}s")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
