import time
import asyncio
from collections import deque
import discord
from discord.ext import commands

# ---- Einstellungen ----
DELETE_THRESHOLD = 2        # Anzahl gelöschter Channels...
TIME_WINDOW_SECONDS = 60    # ...innerhalb dieser Zeitspanne löst Lockdown aus
LOG_CHANNEL_ID = 0          # <-- HIER die ID deines Log/Alert-Channels eintragen


class RaidDetection(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # pro Server: Zeitstempel der letzten Channel-Löschungen
        self._deletes: dict[int, deque[float]] = {}
        # verhindert, dass der Lockdown mehrfach hintereinander ausgelöst wird
        self._raid_active: dict[int, bool] = {}

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        now = time.time()

        deletes = self._deletes.setdefault(guild.id, deque())
        deletes.append(now)

        # alte Einträge außerhalb des Zeitfensters entfernen
        while deletes and now - deletes[0] > TIME_WINDOW_SECONDS:
            deletes.popleft()

        if len(deletes) >= DELETE_THRESHOLD and not self._raid_active.get(guild.id, False):
            self._raid_active[guild.id] = True
            await self._trigger_raid_response(guild, len(deletes))

    async def _trigger_raid_response(self, guild: discord.Guild, delete_count: int):
        log_channel = guild.get_channel(LOG_CHANNEL_ID)

        embed = discord.Embed(
            title="🚨 Möglicher Raid erkannt!",
            description=(
                f"**{delete_count} Channels** wurden innerhalb von {TIME_WINDOW_SECONDS} Sekunden gelöscht.\n"
                f"Server wird sofort gesperrt."
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
            await log_channel.send("🔒 Server automatisch gesperrt. Nutze `/unlock`, sobald der Raid vorbei ist.")

    def reset_raid_status(self, guild_id: int):
        """Wird z.B. von /unlock aufgerufen, um den Raid-Status zurückzusetzen."""
        self._raid_active[guild_id] = False
        self._deletes[guild_id] = deque()


async def setup(bot: commands.Bot):
    await bot.add_cog(RaidDetection(bot))
