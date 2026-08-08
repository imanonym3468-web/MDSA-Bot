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

        if any(user.id == BOSS_ID for user in message.mentions):
            await message.reply("# ❌DONT PING MY BOSS🔨")


async def setup(bot):
    await bot.add_cog(BossPing(bot))