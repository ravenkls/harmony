from discord.ext import commands
import datetime
import discord
import inspect
from fuzzywuzzy import fuzz


class General:
    init_at = None
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command("help")
        self.bot.on_reaction_add = self.poll_reaction
        self.bot.on_reaction_remove = self.poll_reaction
        if self.init_at is None:
            self.init_at = datetime.datetime.utcnow()

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
                    help_embed.add_field(name="Permission Node", value="`" + perm_node + "`")
                await ctx.send(embed=help_embed)

    async def poll_reaction(self, reaction, user):
        if user != self.bot.user:
            if reaction.message.content.startswith("**Poll:**"):
                if reaction.emoji == "✅" or reaction.emoji == "❎":
                    yes = 0
                    no = 0
                    total = 0
                    for r in reaction.message.reactions:
                        if r.emoji == "✅":
                            yes = r.count - 1
                            total += r.count - 1
                        elif r.emoji == "❎":
                            no += r.count - 1
                            total += r.count - 1
                    if total == 0:
                        total = 1
                    lines = reaction.message.content.split("\n")
                    lines[2] = "**Results:** {}% / {}%".format(int((yes / total) * 100), int((no / total) * 100))
                    await reaction.message.edit(content="\n".join(lines))

    async def on_reaction_remove(self, reaction, user):
        if reaction.message.content.startswith("**Poll:**"):
            pass

    @commands.command()
    async def ping(self, ctx):
        """ Pong! """
        diff = ctx.message.created_at - datetime.datetime.utcnow()
        ms = int(diff.total_seconds() * 1000)
        await ctx.send(":ping_pong: `{}ms`".format(ms))

    @commands.command(description="Shows how long I've been online for")
    async def uptime(self, ctx):
        """ How long the bot has been online for (since commands plugin was initialized) """
        uptime = datetime.datetime.utcnow() - self.init_at
        s = uptime.total_seconds()
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        d, h, m, s = map(int, (d, h, m, s))
        uptime_embed = discord.Embed(description=":clock5:  **Ive been online for: ** {}d {}h {}m {}s".format(d, h, m, s), colour = self.bot.embed_colour())
        await ctx.send(embed=uptime_embed)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, plugin=None):
        if plugin is None:
            self.bot.reload_from("plugins")
        else:
            self.bot.unload(plugin)
            self.bot.load(plugin)
        await ctx.send("Reload complete!")

    @commands.command(name="eval", hidden=True)
    @commands.is_owner()
    async def _eval(self, ctx, *, code):
        try:
            await ctx.send("```python\n{}```".format(eval(code)))
        except Exception as e:
            await ctx.send("```python\n{}```".format(e))


def setup(bot):
    bot.add_cog(General(bot))
