import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import asyncio
from datetime import datetime, timedelta, timezone

class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int, bot):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.bot = bot

    @discord.ui.button(emoji="🎉", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.bot.giveaways.get(self.giveaway_id)
        if not g:
            return await interaction.response.send_message("Giveaway nicht gefunden.", ephemeral=True)

        if interaction.user.id in g["entries"]:
            g["entries"].remove(interaction.user.id)
            await interaction.response.send_message("Du hast dich ausgetragen.", ephemeral=True)
            return await self._update_count(interaction, g)

        g["entries"].add(interaction.user.id)
        await interaction.response.send_message("Du nimmst teil!", ephemeral=True)
        await self._update_count(interaction, g)

    async def _update_count(self, interaction, g):
        embed = interaction.message.embeds[0]
        lines = embed.fields[0].value.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("Entries:"):
                lines[i] = f"Entries: **{len(g['entries'])}**"
        embed.set_field_at(0, name="", value="\n".join(lines), inline=False)
        await interaction.message.edit(embed=embed)


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.giveaways = {}  # id -> dict(entries, winners, forced_winner, weights, ...)
        self.check_giveaways.start()

    @app_commands.command(name="gwcreate", description="Erstellt ein neues Giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway(self, interaction: discord.Interaction, prize: str, duration_minutes: int, winners: int = 1):
        end_time = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        embed = discord.Embed(
            title=prize,
            color=discord.Color.from_rgb(147, 112, 219)  # lila
        )
        embed.add_field(name="", value=(
            f"Ends: <t:{int(end_time.timestamp())}:R>\n"
            f"Hosted by: {interaction.user.mention}\n"
            f"Entries: **0**\n"
            f"Winners: **{winners}**"
        ), inline=False)
        embed.timestamp = end_time

        gid = interaction.id
        view = GiveawayView(gid, self.bot)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()

        self.bot.giveaways[gid] = {
            "message_id": msg.id,
            "channel_id": msg.channel.id,
            "entries": set(),
            "winners_count": winners,
            "end_time": end_time,
            "ended": False,
            # --- die "riggbaren" Felder ---
            "forced_winners": set(),      # IDs die garantiert gewinnen
            "excluded": set(),            # IDs die nie gewinnen können
            "weights": {},                # user_id -> gewichtungsfaktor
        }

    # Admin-Command zum "riggen"
    @app_commands.command(name="gwforce", description="Legt einen garantierten Gewinner für ein Giveaway fest")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_force(self, interaction: discord.Interaction, giveaway_msg_id: str, user: discord.User):
        g = self._find_by_message(int(giveaway_msg_id))
        if not g:
            return await interaction.response.send_message("Nicht gefunden.", ephemeral=True)
        g["forced_winners"].add(user.id)
        g["entries"].add(user.id)  # automatisch als Teilnehmer eintragen, auch ohne eigenen Klick
        await interaction.response.send_message(f"{user} wird garantiert gewinnen.", ephemeral=True)

    def _find_by_message(self, message_id):
        for g in self.bot.giveaways.values():
            if g["message_id"] == message_id:
                return g
        return None

    def draw_winners(self, g):
        """Zieht Gewinner – hier steckt die eigentliche Logik (fair ODER rigged)."""
        pool = list(g["entries"] - g["excluded"])
        winners = []

        # 1. Erzwungene Gewinner zuerst
        for uid in g["forced_winners"]:
            if uid in g["entries"] and uid not in winners:
                winners.append(uid)

        remaining_slots = g["winners_count"] - len(winners)
        remaining_pool = [u for u in pool if u not in winners]

        if remaining_slots > 0 and remaining_pool:
            if g["weights"]:
                # gewichtete Ziehung
                weighted_pool = []
                for uid in remaining_pool:
                    weighted_pool.extend([uid] * g["weights"].get(uid, 1))
                chosen = random.sample(weighted_pool, min(remaining_slots, len(set(weighted_pool))))
                winners.extend(list(dict.fromkeys(chosen))[:remaining_slots])
            else:
                winners.extend(random.sample(remaining_pool, min(remaining_slots, len(remaining_pool))))

        return winners

    @tasks.loop(seconds=15)
    async def check_giveaways(self):
        now = datetime.now(timezone.utc)
        for gid, g in list(self.bot.giveaways.items()):
            if not g["ended"] and now >= g["end_time"]:
                g["ended"] = True
                channel = self.bot.get_channel(g["channel_id"])
                winners = self.draw_winners(g)

                if not winners:
                    text = "Keine gültigen Teilnehmer."
                else:
                    text = ", ".join(f"<@{w}>" for w in winners)

                await channel.send(f"🎉 Giveaway beendet! Gewinner: {text}")

async def setup(bot):
    await bot.add_cog(Giveaways(bot))