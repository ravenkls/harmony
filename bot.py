import discord
from discord.ext import commands
import random
import os
import inspect


class Bot(commands.Bot):
    def __init__(self, command_prefix, *args, **kwargs):
        self.log("Initialising")
        super().__init__(command_prefix, *args, **kwargs)
        self.embed_colour = lambda: random.randint(0, 0xFFFFFF)

    def get_usage(self, command):
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

    def load(self, plugin):
        self.load_extension(plugin)
        self.log("Successfully loaded {}".format(plugin), name="Plugins")

    def unload(self, plugin):
        self.unload_extension(plugin)
        self.log("Successfully unloaded {}".format(plugin), name="Plugins")

    def load_from(self, directory):
        for file in os.listdir(directory):
            import_path = ".".join(directory.split("/") + [file[:-3]])
            if file.endswith(".py"):
                self.load(import_path)

    def reload_from(self, directory):
        for file in os.listdir(directory):
            import_path = ".".join(directory.split("/") + [file[:-3]])
            if file.endswith(".py"):
                self.unload(import_path)
                self.load(import_path)

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


def main():
    bot = Bot("?")
    bot.load_from("plugins")
    #bot.unload("plugins.music")
    token = os.environ.get("HARMONY_TOKEN")
    if not token:
        token = open("token.txt").read().strip()
    bot.run(token)

if __name__ == "__main__":
    main()
