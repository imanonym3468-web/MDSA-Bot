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
        # DEBUG: zeigt IMMER an, dass on_message ausgelöst wurde, auch ohne Mentions
        print(f"[DEBUG] on_message ausgelöst | Autor={message.author} (bot={message.author.bot}) | Content='{message.content}' | Mentions={[u.id for u in message.mentions]}")

        if message.author.bot:
            return

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
