import discord
from discord.ext import commands

# Trage hier deine eigene Discord User-ID ein (siehe Anleitung: Entwicklermodus aktivieren,
# Rechtsklick auf dein Profil -> "ID kopieren")
BOSS_ID = 1437546902311931985  # deine Discord User-ID


class BossPing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # DEBUG: zeigt in den Railway-Logs, welche Mentions in jeder Nachricht ankommen
        if message.mentions:
            print(f"[DEBUG] Nachricht von {message.author}: mentions={[u.id for u in message.mentions]} | Ziel-ID={BOSS_ID}")

        if any(user.id == BOSS_ID for user in message.mentions):
            print("[DEBUG] Match gefunden! Sende Antwort...")
            try:
                await message.reply("# ❌DONT PING MY BOSS🔨")
            except discord.Forbidden:
                print("[DEBUG] FEHLER: Keine Berechtigung zum Antworten in diesem Kanal!")
            except discord.HTTPException as e:
                print(f"[DEBUG] FEHLER beim Senden: {e}")


async def setup(bot):
    await bot.add_cog(BossPing(bot))
