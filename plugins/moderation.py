from discord.ext import commands
import asyncio
import discord


class Moderation:
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def poll(self, ctx, *, question):
        """Create a poll"""
        if not question.endswith("?"):
            question += "?"
        message = await ctx.send("**Poll:** " + "@everyone " + question)
        await message.add_reaction("✅")
        await message.add_reaction("❎")

    @commands.command(aliases=["vckick"])
    @commands.guild_only()
    async def voicekick(self, ctx, member: discord.Member):
        """Kick a member from voice chat"""
        if member.voice is not None:
            kick_channel = await ctx.guild.create_voice_channel(name=self.bot.user.name)
            await member.move_to(kick_channel)
            await kick_channel.delete()
            await ctx.send("{0.name} has been kicked from voice".format(member))
        else:
            await ctx.send("{0.name} is not in a voice channel".format(member))

    @commands.command(aliases=["clear", "clean", "cls"])
    @commands.guild_only()
    async def purge(self, ctx, limit=100, member: discord.Member=None):
        """Remove messages from a channel"""
        if member is not None:
            await ctx.channel.purge(limit=limit, check=lambda m: m.author is member)
        else:
            await ctx.channel.purge(limit=limit)
        completed = await ctx.send(":white_check_mark:")
        await asyncio.sleep(2)
        await completed.delete()


def setup(bot):
    bot.add_cog(Moderation(bot))
