from discord.ext import commands
from functools import partial
import discord
import random
import json
import os


class Permissions:
    def __init__(self, bot):
        self.bot = bot
        if not os.path.exists("permissions/data"):
            os.makedirs("permissions/data")
        if not os.path.exists("permissions/default_perms.txt"):
            open("permissions/default_perms.txt", "w").close()
            self.bot.log(
                "Please define default permissions in permissions/default_perms.txt", name="Plugins")
        self.file_fmt = "permissions/data/{0.id}.json"
        self.bot.on_message = self.perms_on_message

    def create_guild_file(self, guild):
        guild_file = self.file_fmt.format(guild)
        json_dump = {}
        with open("permissions/default_perms.txt", "r") as file:
            perms = [L.strip() for L in file.readlines()]
        json_dump[str(guild.default_role.id)] = perms
        with open(guild_file, "w") as file:
            file.write(json.dumps(json_dump, indent=4))

    async def perms_on_message(self, message):
        if type(message.channel) != discord.TextChannel:
            ctx = await self.bot.get_context(message)
            return await self.bot.invoke(ctx)
        elif message.content.startswith(self.bot.command_prefix):
            ctx = await self.bot.get_context(message)
            if ctx.command is None:
                return
            if ctx.author.guild_permissions.administrator or ctx.author is ctx.guild.owner:
                return await self.bot.invoke(ctx)
            perms = self.get_guild_perms(ctx.guild)
            module = ctx.command.module.split(".")[1]
            permission_needed = ".".join([module, ctx.command.name])

            for role in ctx.author.roles:
                if str(role.id) in perms:
                    role_perms = perms[str(role.id)]
                    for permission in role_perms:
                        perm_split = permission.split(".")
                        perm_needed_split = permission_needed.split(".")
                        for i, node in enumerate(perm_split):
                            if perm_needed_split[i] == node or node == "*":
                                access = True
                                continue
                            else:
                                access = False
                                break
                        if access:
                            return await self.bot.invoke(ctx)
            return await ctx.send("You are missing the `{}` permission to execute this command".format(permission_needed))

    def get_guild_perms(self, guild):
        if not os.path.exists(self.file_fmt.format(guild)):
            self.create_guild_file(guild)
        with open(self.file_fmt.format(guild)) as file:
            perms = json.loads(file.read())
        return perms

    def get_guild_file(self, guild, mode="r"):
        if not os.path.exists(self.file_fmt.format(guild)):
            self.create_guild_file(guild)
        return open(self.file_fmt.format(guild), mode)

    @commands.group(aliases=["perms"])
    async def permissions(self, ctx):
        """Used for managing server permissions
Note: these permissions only affect what commands users can use with the bot

Examples:
`permissions add Owner *` - gives the Owner role all commands
`permissions add @everyone general.*` - gives everyone all General commands
`permissions del Moderators music.stop` - removes the Moderators stop permission
`permissions list Admins` - lists all the permissions belonging to the Owner role
`permissions clear @everyone` - clears everyones permissions so they cant type any commands

Type `permissions nodes` for a list of all the available permission nodes
        """
        if ctx.invoked_subcommand is None:
            help = self.bot.get_command("help")
            # Execute the ?help perms command
            await ctx.invoke(help, ctx.command.name)

    @permissions.command(aliases=["allow", "give"])
    @commands.guild_only()
    async def add(self, ctx, role: discord.Role, permission):
        perms = self.get_guild_perms(ctx.guild)
        if str(role.id) in perms:
            perms[str(role.id)].append(permission)
        else:
            perms.update({int(role.id): [permission]})

        with self.get_guild_file(ctx.guild, "w") as file:
            file.write(json.dumps(perms, indent=4))

        await ctx.send("The permission `{}` has been added to `{}`".format(permission, role.name))

    @permissions.command(name="del", aliases=["rm", "deny", "remove", "delete"])
    @commands.guild_only()
    async def _del(self, ctx, role: discord.Role, permission):
        perms = self.get_guild_perms(ctx.guild)
        if str(role.id) in perms:
            try:
                perms[str(role.id)].remove(permission)
            except:
                return await ctx.send("The `{}` role doesn't have that permission")
        else:
            return await ctx.send("The `{}` role doesn't have that permission")

        with self.get_guild_file(ctx.guild, "w") as file:
            file.write(json.dumps(perms, indent=4))

        await ctx.send("The permission `{}` has been removed from `{}`".format(permission, role.name))

    @permissions.command()
    @commands.guild_only()
    async def list(self, ctx, role: discord.Role):
        perms_embed = discord.Embed(title="{}'s permissions".format(
            role.name), colour=random.randint(0, 0xFFFFFF))
        perms = self.get_guild_perms(ctx.guild)
        if str(role.id) in perms:
            perms_embed.description = "\n".join(
                map(lambda x: "`" + x + "`", perms[str(role.id)]))
        else:
            perms_embed.description = "No permissions"
        await ctx.send(embed=perms_embed)

    @permissions.command()
    @commands.guild_only()
    async def nodes(self, ctx):
        perms_embed = discord.Embed(
            title="All Permission Nodes", colour=random.randint(0, 0xFFFFFF))
        perms_embed.set_thumbnail(url=self.bot.user.avatar_url)
        for cog in self.bot.cogs:
            cmds = self.bot.get_cog_commands(cog)
            nodes = []
            for cmd in cmds:
                if not cmd.hidden:
                    module = cmd.module.split(".")[1]
                    permission_node = ".".join([module, cmd.name])
                    nodes.append(permission_node)
            perms_embed.add_field(name=cog, value="\n".join(
                "`{}`".format(n) for n in nodes))
        await ctx.send(embed=perms_embed)


def setup(bot):
    bot.add_cog(Permissions(bot))
