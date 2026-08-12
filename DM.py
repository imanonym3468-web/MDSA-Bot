import discord
from discord.ext import commands

class DMReply(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        if isinstance(message.channel, discord.DMChannel):
            if message.content.strip().lower() == "how are you":
                await message.channel.send(
                    "I don't know who I am, I'm just a shadow of my past. "
                    "I hate everyone and me the most. "
                    "Misa destroys everyone who tries to hurt me, "
                    "that's why she is the only one that I wanna be with."
                )

async def setup(bot: commands.Bot):
    await bot.add_cog(DMReply(bot))
