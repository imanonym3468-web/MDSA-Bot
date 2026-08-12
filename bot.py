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
    if "giveaway" not in bot.extensions:
        await bot.load_extension("giveaway")
    if "stats" not in bot.extensions:
        await bot.load_extension("stats")
    if "boss_ping" not in bot.extensions:
        await bot.load_extension("boss_ping")
    if "role" not in bot.extensions:
        await bot.load_extension("role")
    if "lockdown" not in bot.extensions:
        await bot.load_extension("lockdown")

    bot.tree.copy_global_to(guild=GUILD_ID)
    synced = await bot.tree.sync(guild=GUILD_ID)
    print(f"{len(synced)} Slash Commands synced (Guild {GUILD_ID.id}): {[c.name for c in synced]}")

    bot.tree.clear_commands(guild=None)
    global_synced = await bot.tree.sync()
    print(f"{len(global_synced)} globale Slash Commands synced: {[c.name for c in global_synced]}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    print(f"Neuem Server beigetreten: {guild.name} ({guild.id})")
    try:
        synced = await bot.tree.sync(guild=guild)
        print(f"{len(synced)} Commands sofort für {guild.name} synced.")
    except discord.HTTPException as e:
        print(f"Sync fehlgeschlagen für {guild.name}: {e}")

@bot.command()
@commands.is_owner()
async def sync(ctx):
    bot.tree.copy_global_to(guild=GUILD_ID)
    synced = await bot.tree.sync(guild=GUILD_ID)
    await ctx.send(f"🔄 {len(synced)} Commands für diesen Server synced.")

bot.run(os.getenv("DISCORD_TOKEN"))
