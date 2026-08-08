import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.invites = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")

    # Lädt die giveaways.py als Cog (nur wenn noch nicht geladen)
    if "giveaways" not in bot.extensions:
        await bot.load_extension("giveaways")
    if "stats" not in bot.extensions:
        await bot.load_extension("stats")

    # Synct die Slash Commands mit Discord, damit sie im "/" Menü erscheinen
    synced = await bot.tree.sync()
    print(f"{len(synced)} Slash Commands synced: {[c.name for c in synced]}")


bot.run(os.getenv("DISCORD_TOKEN"))
