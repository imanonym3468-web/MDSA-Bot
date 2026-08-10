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

GUILD_ID = discord.Object(id=1049550035735564319)


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")

    # Lädt alle Cogs (nur wenn noch nicht geladen)
    if "giveaway" not in bot.extensions:
        await bot.load_extension("giveaway")
    if "stats" not in bot.extensions:
        await bot.load_extension("stats")
    if "boss_ping" not in bot.extensions:
        await bot.load_extension("boss_ping")
    if "role" not in bot.extensions:
        await bot.load_extension("role")

    # Guild-spezifisches Sync: Commands erscheinen SOFORT auf deinem Server,
    # statt bis zu 1 Stunde auf das globale Sync zu warten
    bot.tree.copy_global_to(guild=GUILD_ID)
    synced = await bot.tree.sync(guild=GUILD_ID)
    print(f"{len(synced)} Slash Commands synced (Guild {GUILD_ID.id}): {[c.name for c in synced]}")

    # Danach: alte GLOBALE Commands löschen (verhindert Duplikate) -
    # erst NACHDEM die guild-spezifische Kopie erstellt wurde
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync()


bot.run(os.getenv("DISCORD_TOKEN"))
