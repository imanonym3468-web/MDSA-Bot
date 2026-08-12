import time
import asyncio
import datetime
from collections import deque
import discord
from discord import app_commands
from discord.ext import commands

# ---- Einstellungen ----
TIME_WINDOW_SECONDS = 60    # Fenster, in dem Löschungen für die Statistik gezählt werden
LOG_CHANNEL_ID = 0          # Optional: ID deines zentralen Log-Channels (falls vorhanden)


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._deletes: dict[int, deque[float]] = {}
        self._raid_active: dict[int, bool] = {}
        self._attack_start_time: dict[int, float] = {}

    # ==================================================================
    # 1. EVENT: REAKTION AUF KANAL-LÖSCHUNG
    # ==================================================================
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        now = time.time()

        # Startzeitpunkt des Angriffs protokollieren
        if guild.id not in self._attack_start_time:
            self._attack_start_time[guild.id] = now

        deletes = self._deletes.setdefault(guild.id, deque())
        deletes.append(now)
        while deletes and now - deletes[0] > TIME_WINDOW_SECONDS:
            deletes.popleft()

        # Schutz-Kette nur beim ersten erkannten Löschvorgang starten
        if not self._raid_active.get(guild.id, False):
            self._raid_active[guild.id] = True
            asyncio.create_task(self._execute_defense_sequence(guild, channel))

    # ==================================================================
    # 2. SCHUTZ-SEQUENZ (Kick -> Lockdown -> Analyse -> Embed in alle Channels)
    # ==================================================================
    async def _execute_defense_sequence(self, guild: discord.Guild, initial_channel: discord.abc.GuildChannel):
        attack_start = self._attack_start_time.get(guild.id, time.time())

        # ------------------------------------------------------------------
        # SCHRITT 1: Bots sofort kicken (Maximale Priorität)
        # ------------------------------------------------------------------
        kicked_bots, failed_bots = await self._kick_all_bots(guild)

        # ------------------------------------------------------------------
        # SCHRITT 2: Lockdown auf allen Text-Kanälen aktivieren
        # ------------------------------------------------------------------
        await self._lock_all_channels(guild)

        # Reaktionsdauer berechnen
        containment_duration = round(time.time() - attack_start, 2)

        # ------------------------------------------------------------------
        # SCHRITT 3: Audit-Logs mit Retry-Logik auslesen (Identifikation)
        # ------------------------------------------------------------------
        culprit = None        # Wer hat die Nuke veranlasst?
        executor_bot = None   # Welcher Bot/User hat gelöscht?

        # Kurze Kunstpause, damit Discord Zeit hat, das Audit-Log zu schreiben
        await asyncio.sleep(1.0)

        try:
            # Bis zu 3 Versuche mit leichter Verzögerung
            for _ in range(3):
                async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.channel_delete):
                    if entry.target and entry.target.id == initial_channel.id:
                        executor_bot = entry.user
                        culprit = entry.user
                        break
                if executor_bot:
                    break
                await asyncio.sleep(0.5)
        except discord.Forbidden:
            pass

        # Falls ein Bot gelöscht hat: Ermitteln, wer den Bot auf den Server geholt hat
        if executor_bot and executor_bot.bot:
            try:
                async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
                    if entry.target and entry.target.id == executor_bot.id:
                        culprit = entry.user
                        break
            except discord.Forbidden:
                pass

        # Nuke-Auslöser bannen (falls identifiziert und nicht der eigene Bot)
        if culprit and culprit.id != self.bot.user.id:
            try:
                await guild.ban(culprit, reason="Anti-Nuke: Auslöser des Angriffs identifiziert", delete_message_seconds=0)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # ------------------------------------------------------------------
        # SCHRITT 4: Bericht erstellen und in JEDEN Textkanal senden
        # ------------------------------------------------------------------
        deleted_count = len(self._deletes.get(guild.id, []))
        
        if deleted_count <= 2:
            severity = "🟢 Gering (Schnell abgefangen)"
        elif deleted_count <= 5:
            severity = "🟡 Mittel (Einige Kanäle verloren)"
        else:
            severity = "🔴 Hoch / Kritisch (Schwerer Schaden)"

        start_time_formatted = datetime.datetime.fromtimestamp(attack_start).strftime('%H:%M:%S Uhr (%d.%m.%Y)')
        kicked_list_str = ", ".join([f"`{b.name}`" for b in kicked_bots]) if kicked_bots else "Keine Bots gekickt"

        embed = discord.Embed(
            title="🚨 SERVER-LOCKDOWN AKTIVIERT",
            description="Aufgrund eines erkannten Nuke-Angriffs wurde der Server automatisch gesichert.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(
            name="💣 Nuke-Auslöser", 
            value=f"{culprit.mention if culprit else 'Unbekannt'} (`{culprit.id if culprit else 'N/A'}`)", 
            inline=True
        )
        embed.add_field(
            name="🤖 Ausführender Bot/User", 
            value=f"{executor_bot.mention if executor_bot else 'Unbekannt'} (`{executor_bot.id if executor_bot else 'N/A'}`)", 
            inline=True
        )
        embed.add_field(name="🕒 Angriffs-Startzeit", value=start_time_formatted, inline=False)
        embed.add_field(name="🗑️ Gelöschte Kanäle", value=f"**{deleted_count}** Channel(s)", inline=True)
        embed.add_field(name="⚠️ Schwere des Verlusts", value=severity, inline=True)
        embed.add_field(name="⏱️ Erkennungs- & Eindämmungszeit", value=f"**{containment_duration} Sekunden**", inline=False)
        embed.add_field(name="👞 Gekickte Bots", value=kicked_list_str, inline=False)

        # Bericht zeitgleich an alle Kanäle verteilen
        async def send_report(channel: discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        await asyncio.gather(*(send_report(ch) for ch in guild.text_channels), return_exceptions=True)

    # ==================================================================
    # HILFSFUNKTIONEN (BOT KICK & CHANNEL LOCK)
    # ==================================================================
    async def _kick_all_bots(self, guild: discord.Guild):
        targets = [m for m in guild.members if m.bot and m.id != self.bot.user.id]
        if not targets:
            return [], []

        async def kick_one(member: discord.Member):
            try:
                await guild.kick(member, reason="Anti-Nuke: Sofort-Kick fremder Bots")
                return member, True
            except (discord.Forbidden, discord.HTTPException):
                return member, False

        results = await asyncio.gather(*(kick_one(m) for m in targets))
        kicked = [m for m, ok in results if ok]
        failed = [m for m, ok in results if not ok]
        return kicked, failed

    async def _lock_all_channels(self, guild: discord.Guild):
        lockdown_cog = self.bot.get_cog("Lockdown")
        everyone = guild.default_role

        if lockdown_cog and hasattr(lockdown_cog, "_lock_channel"):
            await asyncio.gather(
                *(lockdown_cog._lock_channel(ch, everyone) for ch in guild.text_channels),
                return_exceptions=True
            )
        else:
            async def fallback_lock(ch: discord.TextChannel):
                try:
                    overwrites = ch.overwrites_for(everyone)
                    overwrites.send_messages = False
                    await ch.set_permissions(everyone, overwrite=overwrites)
                except (discord.Forbidden, discord.HTTPException):
                    pass

            await asyncio.gather(*(fallback_lock(ch) for ch in guild.text_channels), return_exceptions=True)

    def reset_raid_status(self, guild_id: int):
        """Wird aufgerufen, um den Raid-Status manuell zurückzusetzen (z. B. bei /unlock)."""
        self._raid_active[guild_id] = False
        self._deletes[guild_id] = deque()
        self._attack_start_time.pop(guild_id, None)

    # ==================================================================
    # MANUELLER TRIGGER: "!nuke" IM CHAT
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
                    await guild.ban(member, reason="Anti-Nuke: '!nuke'-Trigger im Chat", delete_message_seconds=0)
                    return member, True
                except (discord.Forbidden, discord.HTTPException):
                    return member, False

            results = await asyncio.gather(*(ban_one(m) for m in targets))
            banned = [m for m, ok in results if ok]
            failed = [m for m, ok in results if not ok]

            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            embed = discord.Embed(
                title="🚨 '!nuke' erkannt — Alle Bots gebannt",
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
    # COMMAND: /defense-status
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
                        "geladen" if lockdown_cog else "nicht geladen (Fallback aktiv)"))

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
