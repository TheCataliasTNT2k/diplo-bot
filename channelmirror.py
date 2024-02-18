from discord import (
    SlashCommandGroup,
    TextChannel,
    Permissions
)
from discord.commands import Option
from discord.ext.commands import Cog
import sqlite3

class ChannelMirror(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = sqlite3.connect("database/channelmirror/channelmirror.db")
        self.cursor = self.db.cursor()
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS channelmirror (
                source_guild_id INTEGER,
                source_channel_id INTEGER,
                destination_guild_id INTEGER,
                destination_channel_id INTEGER
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messageids (
                source_guild_id INTEGER,
                source_channel_id INTEGER,
                source_message_id INTEGER,
                destination_guild_id INTEGER,
                destination_channel_id INTEGER,
                destination_message_id INTEGER
            )
            """
        )
        self.db.commit()
    channelmirror = SlashCommandGroup(name = "channelmirror", description = "Commands for channel mirroring", default_member_permissions = Permissions(manage_guild = True))

    @channelmirror.command(name = "create", description = "Create a channel to mirror")
    async def create(self, ctx,
            source_channel: Option(TextChannel, "The source channel to mirror"),
            destination_channel_guild_id: Option(str, "The destination guild id of channel to mirror"),
            destination_channel_id: Option(str, "The destination channel id to mirror")
        ):
        destination_guild = None
        try:
            destination_guild = await self.bot.fetch_guild(destination_channel_guild_id)
        except:
            await ctx.respond("Destination guild not found", ephemeral = True)
            return
        destination_channel = None
        try:
            destination_channel = await destination_guild.fetch_channel(destination_channel_id)
        except:
            await ctx.respond("Destination channel not found", ephemeral = True)
            return
        self.cursor.execute(
            """
            INSERT INTO channelmirror (source_guild_id, source_channel_id, destination_guild_id, destination_channel_id) VALUES (?, ?, ?, ?)
            """,
            (source_channel.guild.id, source_channel.id, destination_guild.id, destination_channel.id)
        )
        self.db.commit()
        await destination_channel.create_webhook(name = "ChannelMirror", reason = "ChannelMirror webhook creation")
        await ctx.respond(f"Created a mirror from {source_channel.mention} to {destination_channel.mention}", ephemeral = True)

    @channelmirror.command(name = "delete", description = "Delete a channel to mirror")
    async def delete(self, ctx,
            source_channel: Option(TextChannel, "The source channel to mirror"),
            destination_channel_guild_id: Option(str, "The destination guild id of channel to mirror"),
            destination_channel_id: Option(str, "The destination channel id to mirror")
        ):
        destination_guild = None
        try:
            destination_guild = await self.bot.fetch_guild(destination_channel_guild_id)
        except:
            await ctx.respond("Destination guild not found", ephemeral = True)
            return
        destination_channel = None
        try:
            destination_channel = await destination_guild.fetch_channel(destination_channel_id)
        except:
            await ctx.respond("Destination channel not found", ephemeral = True)
            return
        if not self.cursor.execute(
            """
            SELECT * FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?
            """,
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        ).fetchone():
            await ctx.respond("Mirror not found", ephemeral = True)
            return
        self.cursor.execute(
            """
            DELETE FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?
            """,
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        )
        self.db.commit()
        webhooks = await destination_channel.webhooks()
        for webhook in webhooks:
            if webhook.name == "ChannelMirror":
                await webhook.delete()
                break
        await ctx.respond(f"Deleted mirror from {source_channel.mention} to {destination_channel.mention}", ephemeral = True)

    @channelmirror.command(name = "delete_by_number", description = "Delete a channel to mirror")
    async def list(self, ctx,
            link_number: Option(str, "The Link number to delete")
        ):
        await ctx.respond("Deleting...", ephemeral = True)
        self.cursor.execute(
            """
            SELECT * FROM channelmirror
            """
        )
        mirrors = self.cursor.fetchall()
        if not mirrors:
            await ctx.respond("No mirrors found", ephemeral = True)
            return
        i = 0
        for mirror in mirrors:
            try:
                source_guild = await self.bot.fetch_guild(mirror[0])
            except:
                continue
            try:
                source_channel = await source_guild.fetch_channel(mirror[1])
            except:
                continue
            try:
                destination_guild = await self.bot.fetch_guild(mirror[2])
            except:
                continue
            try:
                destination_channel = await destination_guild.fetch_channel(mirror[3])
            except:
                continue
            if source_guild == ctx.guild or destination_guild == ctx.guild:
                i += 1
                if i == int(link_number):
                    self.cursor.execute(
                        """
                        DELETE FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?
                        """,
                        (source_guild.id, source_channel.id, destination_guild.id, destination_channel.id)
                    )
                    self.db.commit()
                    await ctx.edit(content = f"Deleted mirror from {source_channel.mention} to {destination_channel.mention}")
                    return
    
    @channelmirror.command(name = "list", description = "List all mirrors")
    async def list(self, ctx):
        await ctx.respond("Loading...", ephemeral = True)
        self.cursor.execute(
            """
            SELECT * FROM channelmirror
            """
        )
        mirrors = self.cursor.fetchall()
        if not mirrors:
            await ctx.respond("No mirrors found", ephemeral = True)
            return
        message = "Channel Mirrors:\n"
        i = 0
        for mirror in mirrors:
            try:
                source_guild = await self.bot.fetch_guild(mirror[0])
            except:
                continue
            try:
                source_channel = await source_guild.fetch_channel(mirror[1])
            except:
                continue
            try:
                destination_guild = await self.bot.fetch_guild(mirror[2])
            except:
                continue
            try:
                destination_channel = await destination_guild.fetch_channel(mirror[3])
            except:
                continue
            if source_guild == ctx.guild or destination_guild == ctx.guild:
                i += 1
                message += f"{i}. Mirror from {source_channel.mention} to {destination_channel.mention}\n"
        await ctx.edit(content = message)

    @channelmirror.command(name = "server", description = "List all Servers of wich Bot is Member")
    async def list(self, ctx):
        server = self.bot.guilds
        message = "Servers:\n"
        i = 0
        for s in server:
            i += 1
            message += f"{i}. {s.name}\n"
        await ctx.respond(content = message, ephemeral = True)
    
    @Cog.listener("on_message")
    async def on_message(self, message):
        if message.author.bot:
            return
        self.cursor.execute(
            """
            SELECT * FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ?
            """,
            (message.guild.id, message.channel.id)
        )
        mirrors = self.cursor.fetchall()
        content = message.content.replace("@everyone", "everyone").replace("@here", "here")
        nick = message.author.nick or message.author.display_name
        for mirror in mirrors:
            try:
                destination_guild = await self.bot.fetch_guild(mirror[2])
            except:
                continue
            try:
                destination_channel = await destination_guild.fetch_channel(mirror[3])
            except:
                continue
            webhooks = await destination_channel.webhooks()
            webhk = None
            for webhook in webhooks:
                if webhook.name == "ChannelMirror":
                    webhk = webhook
                    break
            for attachment in message.attachments:
                repl_message = await webhk.send(content = attachment.url, username = nick + " from " + message.guild.name, avatar_url = message.author.avatar.url, wait = True)
                #self.cursor.execute(
                #    """
                #    Insert INTO messageids (source_guild_id, source_channel_id, source_message_id, destination_guild_id, destination_channel_id, destination_message_id) VALUES (?, ?, ?, ?, ?, ?)
                #    """,
                #    (message.guild.id, message.channel.id, message.id, repl_message.guild.id, repl_message.channel.id, repl_message.id)
                #)
            if content:
                repl_message = await webhk.send(content = content, username = nick + " from " + message.guild.name, avatar_url = message.author.avatar.url, wait = True)
                self.cursor.execute(
                    """
                    Insert INTO messageids (source_guild_id, source_channel_id, source_message_id, destination_guild_id, destination_channel_id, destination_message_id) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (message.guild.id, message.channel.id, message.id, repl_message.guild.id, repl_message.channel.id, repl_message.id)
                )
        self.db.commit()

    @Cog.listener("on_message_edit")
    async def on_message_edit(self, before, after):
        if before.author.bot:
            return
        self.cursor.execute(
            """
            SELECT * FROM messageids WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ?
            """,
            (before.guild.id, before.channel.id, before.id)
        )
        messageids = self.cursor.fetchall()
        for messageid in messageids:
            try:
                destination_guild = await self.bot.fetch_guild(messageid[3])
            except:
                continue
            try:
                destination_channel = await destination_guild.fetch_channel(messageid[4])
            except:
                continue
            webhooks = await destination_channel.webhooks()
            webhk = None
            for webhook in webhooks:
                if webhook.name == "ChannelMirror":
                    webhk = webhook
                    break
            await webhk.edit_message(messageid[5], content = after.content)

    @Cog.listener("on_message_delete")
    async def on_message_delete(self, message):
        if message.author.bot:
            return
        self.cursor.execute(
            """
            SELECT * FROM messageids WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ?
            """,
            (message.guild.id, message.channel.id, message.id)
        )
        messageids = self.cursor.fetchall()
        for messageid in messageids:
            try:
                destination_guild = await self.bot.fetch_guild(messageid[3])
            except:
                continue
            try:
                destination_channel = await destination_guild.fetch_channel(messageid[4])
            except:
                continue
            webhooks = await destination_channel.webhooks()
            webhk = None
            for webhook in webhooks:
                if webhook.name == "ChannelMirror":
                    webhk = webhook
                    break
            await webhk.delete_message(messageid[5])

def setup(bot):
    bot.add_cog(ChannelMirror(bot))
