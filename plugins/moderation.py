from discord.ext import commands
import asyncio
import discord


class Moderation:
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def poll(self, ctx, question, *options: str):
        """Create a poll
Example: `poll \"How old are you?\" \"0-20\" \"21-40\" \"41-60\" \"61+\"`"""
        if len(options) > 9:
            return await ctx.send("I can't do a poll with more than 9 options")
        message = await ctx.send("**Poll:** @everyone " + question + "\n" +
                                 "\n".join(f"**{n+1}** {option}" for n, option in enumerate(options)))
        emojis = ["\U00000031\U000020E3", "\U00000032\U000020E3",
                  "\U00000033\U000020E3", "\U00000034\U000020E3",
                  "\U00000035\U000020E3", "\U00000036\U000020E3",
                  "\U00000037\U000020E3", "\U00000038\U000020E3",
                  "\U00000039\U000020E3"]
        for num in range(len(options)):
            await message.add_reaction(emojis[num])

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

    @commands.command()
    @commands.guild_only()
    async def mute(self, ctx, member: discord.Member, seconds: int=0, *, reason=None):
        """Prevents someone from speaking in all text and voice channels for a duration"""
        try:
            text_overwrite = discord.PermissionOverwrite(send_messages=False)
            voice_overwrite = discord.PermissionOverwrite(speak=False)
            for channel in ctx.guild.channels:
                if type(channel) == discord.TextChannel:
                    await channel.set_permissions(member, overwrite=text_overwrite, reason=reason)
                elif type(channel) == discord.VoiceChannel:
                    await channel.set_permissions(member, overwrite=voice_overwrite, reason=reason)
        except Exception as e:
            print(e)
            await ctx.send("no perms")
        if seconds > 0:
            pass


def setup(bot):
    bot.add_cog(Moderation(bot))
