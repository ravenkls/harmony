from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType
import datetime
import discord
import inspect
from fuzzywuzzy import fuzz
import datetime


class General:
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command("help")
        if not hasattr(self.bot, "init_at"):
            self.bot.init_at = datetime.datetime.utcnow()

    @commands.command(aliases=["h"])
    async def help(self, ctx, cmd=None):
        """ Shows you a list of commands """
        if cmd is None:
            help_embed = discord.Embed(title="Commands are listed below", colour=self.bot.embed_colour())
            help_embed.__setattr__("description", "Type `{}help <command>` for more information".format(self.bot.command_prefix))
            help_embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar_url)
            help_embed.set_thumbnail(url=self.bot.user.avatar_url)
            for cog in self.bot.cogs:
                cmds = self.bot.get_cog_commands(cog)
                help_embed.add_field(name=cog, value="\n".join("`{0.name}`".format(c) for c in cmds if not c.hidden))
            await ctx.author.send(embed=help_embed)
            await ctx.message.add_reaction("\U0001F4EC")
        else:
            command = self.bot.get_command(cmd)
            if command is None:
                ctx.send("That command does not exist")
            else:
                help_embed = discord.Embed(title=command.name, colour=self.bot.embed_colour())
                desc = command.description
                help_embed.description = desc if desc != "" else command.callback.__doc__
                aliases = ", ".join("`{}`".format(c) for c in command.aliases)
                if len(aliases) > 0:
                    help_embed.add_field(name="Aliases", value=aliases)
                usage = self.bot.get_usage(command)
                help_embed.add_field(name="Usage", value="`" + usage + "`")
                if "Permissions" in self.bot.cogs:
                    module = command.module.split(".")[1]
                    perm_node = ".".join([module, command.name])
                    help_embed.add_field(name="Permission Node", value="`" + perm_node + "`", inline=False)
                await ctx.send(embed=help_embed)

    @commands.command()
    @commands.cooldown(rate=2, per=43200, type=BucketType.user)
    async def feedback(self, ctx, *, message):
        """Give me feedback on the bot. Feel free to give any suggestions!"""
        feedback_embed = discord.Embed(description=message)
        feedback_embed.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url)
        feedback_embed.set_thumbnail(url=ctx.guild.icon_url or "https://i.imgur.com/WvTRCXX.jpg")
        feedback_embed.set_footer(text=datetime.datetime.now())
        await self.bot.app_info.owner.send(embed=feedback_embed)
        await ctx.send("Thank you, your feedback has been noted.")

    @commands.command()
    async def ping(self, ctx):
        """Pong!"""
        diff = datetime.datetime.utcnow() - ctx.message.created_at
        ms = int(diff.total_seconds() * 1000)
        await ctx.send(":ping_pong: `{}ms`".format(ms))

    @commands.command(description="Shows how long I've been online for")
    async def uptime(self, ctx):
        """ How long the bot has been online for (since commands plugin was initialized) """
        uptime = datetime.datetime.utcnow() - self.bot.init_at
        s = uptime.total_seconds()
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        d, h, m, s = map(int, (d, h, m, s))
        uptime_embed = discord.Embed(description=f":clock5:  **Ive been online for:**  {d}d {h}h {m}m {s}s", colour=self.bot.embed_colour())
        await ctx.send(embed=uptime_embed)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, plugin=None):
        """Reloads all plugins or a specific plugin"""
        if plugin is None:
            num = self.bot.reload(*self.bot.INSTALLED_PLUGINS)
            await ctx.send(f"{num} plugins have been reloaded.")
        else:
            self.bot.unload(plugin)
            self.bot.load(plugin)
            await ctx.send(f"{plugin} has been reloaded!")

    @commands.command(name="eval", hidden=True)
    @commands.is_owner()
    async def _eval(self, ctx, *, code):
        try:
            if code.startswith("await "):
                response = await eval(code.replace("await ", ""))
            else:
                response = eval(code)
            if response is not None:
                await ctx.send("```python\n{}```".format(response))
        except Exception as e:
            await ctx.send("```python\n{}```".format(e))

    @commands.command(hidden=True)
    @commands.is_owner()
    async def edit(self, ctx, kw, arg):
        await self.bot.user.edit(**{kw: arg})
        await ctx.send("Done")


def setup(bot):
    bot.add_cog(General(bot))
