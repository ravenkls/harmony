from discord.ext import commands
from operator import itemgetter
from fuzzywuzzy import process
import discord
import aiohttp
import csv


class Moderation:
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def poll(self, ctx, *, question):
        try:
            await ctx.message.delete()
        except:
            pass
        message = await ctx.send("**Poll:** " + "@everyone " + question + "\n\n**Results:** 0% / 0%")
        await message.add_reaction("✅")
        await message.add_reaction("❎")

    @commands.command(aliases = ["vckick"])
    @commands.guild_only()
    async def voicekick(self, ctx, member: discord.Member):
        """ Kicks a member from voice chat """
        if member.voice is not None:
            kick_channel = await ctx.guild.create_voice_channel(name = self.bot.user.name)
            await member.move_to(kick_channel)
            await kick_channel.delete()
            await ctx.send("{0.name} has been kicked from voice".format(member))
        else:
            await ctx.send("{0.name} is not in a voice channel".format(member))

    @commands.command(aliases = ["emoji"])
    @commands.guild_only()
    async def twitchify(self, ctx, *, emote):
        """ Searches through twitch emotes and adds it to your server
__[See the full list of emotes here](https://twitchemotes.com/)__"""
        emotes = {}
        with open("emotes.csv") as file:
            csvfile = csv.reader(file)
            emotes = dict(csvfile)
        names = emotes.keys()
        results = process.extract(emote, names, limit = 3)
        best_match = max(results, key = itemgetter(1))
        if best_match[1] == 100:
            async with aiohttp.ClientSession() as session:
                async with session.get(emotes[best_match[0]]) as resp:
                    emoji = await ctx.guild.create_custom_emoji(name = best_match[0], image = await resp.read())
                    await ctx.send("{} I have added the `{}` emoji".format(str(emoji), best_match[0]))
        else:
            await ctx.send("**I couldn't find an emoji by the name `{}`.**\nDid you mean:\n".format(emote)
                           +"\n".join(["* " + i[0] for i in results]))


def setup(bot):
    bot.add_cog(Moderation(bot))