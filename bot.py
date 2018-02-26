import discord
from discord.ext import commands
import random
import os
import inspect
import aiohttp

DISCORDBOTS_API = os.environ.get("DISCORDBOTS_KEY")
EMBED_COLOUR = 0x19868A

class Bot(commands.Bot):

    INSTALLED_PLUGINS = [
        "plugins.general",
        "plugins.newmusic",
        # "plugins.moderation",
        # "plugins.permissions"
    ]

    def __init__(self, command_symbol: str, *args, **kwargs):
        self.log("Initialising")
        self.prefix = command_symbol
        self.embed_colour = EMBED_COLOUR
        super().__init__(command_prefix=self.get_prefixes, *args, **kwargs)

    def get_prefixes(self, bot, message):
        return [self.prefix, f"<@{self.user.id}> ", f"<@!{self.user.id}> "]

    def get_usage(self, command):
        args_spec = inspect.getfullargspec(command.callback)  # Get arguments of command
        args_info = []
        [args_info.append("".join(["<", arg, ">"])) for arg in args_spec.args[2:]]  # List arguments
        if args_spec.defaults is not None:
            for index, default in enumerate(args_spec.defaults):  # Modify <> to [] for optional arguments
                default_arg = list(args_info[-(index + 1)])
                default_arg[0] = "["
                default_arg[-1] = "]"
                args_info[-(index + 1)] = "".join(default_arg)
        if args_spec.varargs:  # Compensate for *args
            args_info.append("<" + args_spec.varargs + ">")
        if args_spec.kwonlyargs:
            args_info.extend(["<" + a + ">" for a in args_spec.kwonlyargs])
        args_info.insert(0, self.prefix + command.name)  # Add command name to the front
        return " ".join(args_info)  # Return args

        args = inspect.getfullargspec(command.callback)
        args_info = {}
        for arg in args[0][2:] + args[4]:
            if arg not in args[6]:
                args_info[arg] = None
            else:
                args_info[arg] = args[6][arg].__name__
        usage = " ".join("<{}: {}>".format(k, v) if v is not None else "<{}>".format(k) for k, v in args_info.items())
        return " ".join([command.name, usage])

    def log(self, value, name=None):
        if name is None:
            name = "BOT"
        else:
            name = name.upper()
        header = "[" + name + " " * (10 - len(name)) + "]"
        print(header, value)

    def load(self, *plugin):
        for p in plugin:
            self.load_extension(p)
            self.log("Successfully loaded {}".format(p), name="Plugins")

    def unload(self, *plugin):
        for p in plugin:
            self.unload_extension(p)
            self.log("Successfully unloaded {}".format(p), name="Plugins")

    def reload(self, *plugin):
        for p in plugin:
            self.unload(p)
            self.load(p)
        return len(plugin)

    async def set_playing(self):
        guilds = sum(1 for _ in self.guilds)
        await self.change_presence(game=discord.Game(name=f"on {guilds} guilds | {self.prefix}help"))
        with aiohttp.ClientSession() as session:
            url = f"https://discordbots.org/api/bots/{self.user.id}/stats"
            await session.post(url, data={"server_count": guilds},
                               headers={"Authorization": DISCORDBOTS_API})

    async def on_guild_join(self, guild):
        await self.set_playing()
        for channel in guild.text_channels:
            try:
                await channel.send(f"Thank you for adding {self.user.name}. Type `{self.prefix}help` for a full list of commands.\n"
                                   f"Please consider upvoting the bot at https://discordbots.org/bot/{self.user.id} if you "
                                   f"like {self.user.name} - it's greatly appreciated :slight_smile:")
                break
            except discord.Forbidden as e:
                pass

    async def on_guild_remove(self, guild):
        await self.set_playing()

    async def on_command_error(self, ctx, exception):
        if type(exception) == discord.ext.commands.errors.CommandNotFound:
            return
        error_embed = discord.Embed(colour=0xFF0000)
        if type(exception) == discord.ext.commands.errors.MissingRequiredArgument:
            arg = str(exception).split()[0]
            error_embed.title = "Syntax Error"
            error_embed.description = "Usage: `{}`".format(self.get_usage(ctx.command))
            error_embed.set_footer(text="{} is a required argument".format(arg))
        elif type(exception) == discord.ext.commands.errors.BadArgument:
            error_embed.title = "Syntax Error"
            error_embed.description = "Usage: `{}`".format(self.get_usage(ctx.command))
            error_embed.set_footer(text=str(exception))
        else:
            self.log(str(exception), "ERROR")
            error_embed.title = "Error"
            error_embed.description = "`" + str(exception) + "`"
        if error_embed.description is not None:
            return await ctx.send(embed=error_embed)

    async def on_ready(self):
        self.log("OK https://discordapp.com/oauth2/authorize?client_id={}&scope=bot".format(self.user.id))
        self.app_info = await self.application_info()
        await self.set_playing()


def main():
    bot = Bot(">")
    bot.load(*Bot.INSTALLED_PLUGINS)
    token = os.environ.get("HARMONY_TOKEN")
    if not token:
        token = open("token.txt").read().strip()
    bot.run(token)

if __name__ == "__main__":
    main()
