from discord import (
    SlashCommandGroup,
    TextChannel,
    Permissions
)
from discord.ui import View, Button, button
from discord import ButtonStyle, Interaction
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
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                guild_id INTEGER,
                channel_id INTEGER,
                webhook_id INTEGER
            )
            """
        )
        self.db.commit()
    channelmirror = SlashCommandGroup(name = "channelmirror", description = "Commands for channel mirroring", default_member_permissions = Permissions(administrator = True))

    @channelmirror.command(name = "create", description = "Create a channel to mirror")
    async def create(self, ctx,
            source_channel: Option(TextChannel, "The source channel to mirror"),
            destination_channel_guild_id: Option(str, "The destination guild id of channel to mirror"),
            destination_channel_id: Option(str, "The destination channel id to mirror")
        ):
        destination_guild = None
        try:
            destination_guild = await get_or_fetch_guild(self.bot, destination_channel_guild_id)
        except:
            await ctx.respond("Destination guild not found", ephemeral = True)
            return
        destination_channel = None
        try:
            destination_channel = await get_or_fetch_channel(destination_guild, destination_channel_id)
        except:
            await ctx.respond("Destination channel not found", ephemeral = True)
            return
        if not self.cursor.execute(
            """
            SELECT * FROM webhooks WHERE guild_id = ? AND channel_id = ?
            """,
            (destination_guild.id, destination_channel.id)
        ).fetchone():
            webhook = await destination_channel.create_webhook(name = "ChannelMirror", reason = "ChannelMirror webhook creation")
            self.cursor.execute(
                """
                INSERT INTO webhooks (guild_id, channel_id, webhook_id) VALUES (?, ?, ?)
                """,
                (destination_guild.id, destination_channel.id, webhook.id)
            )
        self.cursor.execute(
            """
            INSERT INTO channelmirror (source_guild_id, source_channel_id, destination_guild_id, destination_channel_id) VALUES (?, ?, ?, ?)
            """,
            (source_channel.guild.id, source_channel.id, destination_guild.id, destination_channel.id)
        )
        self.db.commit()
        await ctx.respond(f"Created a mirror from {source_channel.mention} to {destination_channel.mention}", ephemeral = True)

    @channelmirror.command(name = "delete", description = "Delete a channel to mirror")
    async def delete(self, ctx,
            source_channel: Option(TextChannel, "The source channel to mirror"),
            destination_channel_guild_id: Option(str, "The destination guild id of channel to mirror"),
            destination_channel_id: Option(str, "The destination channel id to mirror")
        ):
        destination_guild = None
        try:
            destination_guild = await get_or_fetch_guild(self.bot, destination_channel_guild_id)
        except:
            await ctx.respond("Destination guild not found", ephemeral = True)
            return
        destination_channel = None
        try:
            destination_channel = await get_or_fetch_channel(destination_guild, destination_channel_id)
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
        if not self.cursor.execute(
            """
            SELECT * FROM channelmirror WHERE destination_guild_id = ? AND destination_channel_id = ?
            """,
            (destination_guild.id, destination_channel.id)
        ).fetchone():
            webhooks = await destination_channel.webhooks()
            for webhook in webhooks:
                if webhook.id == self.cursor.execute(
                    """
                    SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?
                    """,
                    (destination_guild.id, destination_channel.id)
                ).fetchone()[0]:
                    await webhook.delete()
                    break
            self.cursor.execute(
                """
                DELETE FROM webhooks WHERE guild_id = ? AND channel_id = ?
                """,
                (destination_guild.id, destination_channel.id)
            )
        self.db.commit()
        await ctx.respond(f"Deleted mirror from {source_channel.mention} to {destination_channel.mention}", ephemeral = True)

    @channelmirror.command(name = "delete_by_number", description = "Delete a channel to mirror")
    async def delete_by_number(self, ctx,
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
            if mirror[0] == ctx.guild.id or mirror[2] == ctx.guild.id:
                try:
                    source_guild = await get_or_fetch_guild(self.bot, mirror[0])
                    source_channel = await get_or_fetch_channel(source_guild, mirror[1])
                    destination_guild = await get_or_fetch_guild(self.bot, mirror[2])
                    destination_channel = await get_or_fetch_channel(destination_guild, mirror[3])
                except:
                    continue
                i += 1
                if i == int(link_number):
                    self.cursor.execute(
                        """
                        DELETE FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?
                        """,
                        (source_guild.id, source_channel.id, destination_guild.id, destination_channel.id)
                    )
                    if not self.cursor.execute(
                        """
                        SELECT * FROM channelmirror WHERE destination_guild_id = ? AND destination_channel_id = ?
                        """,
                        (destination_guild.id, destination_channel.id)
                    ).fetchone():
                        webhooks = await destination_channel.webhooks()
                        for webhook in webhooks:
                            if webhook.id == self.cursor.execute(
                                """
                                SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?
                                """,
                                (destination_guild.id, destination_channel.id)
                            ).fetchone()[0]:
                                await webhook.delete()
                                break
                        self.cursor.execute(
                            """
                            DELETE FROM webhooks WHERE guild_id = ? AND channel_id = ?
                            """,
                            (destination_guild.id, destination_channel.id)
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
            await ctx.edit(content = "No mirrors found")
            return
        message = "Channel Mirrors:\n"
        i = 0
        for mirror in mirrors:
            if mirror[0] == ctx.guild.id or mirror[2] == ctx.guild.id:
                try:
                    source_guild = await get_or_fetch_guild(self.bot, mirror[0])
                    source_channel = await get_or_fetch_channel(source_guild, mirror[1])
                    destination_guild = await get_or_fetch_guild(self.bot, mirror[2])
                    destination_channel = await get_or_fetch_channel(destination_guild, mirror[3])
                except:
                    continue
                i += 1
                message += f"{i}. Mirror from {source_channel.mention} to {destination_channel.mention}\n"
        await ctx.edit(content = message)

    @channelmirror.command(name = "server", description = "List all Servers of wich Bot is Member")
    async def server(self, ctx):
        server = self.bot.guilds
        message = "Servers:\n"
        i = 0
        for s in server:
            i += 1
            message += f"{i}. {s.name}\n"
        await ctx.respond(content = message, ephemeral = True)

    @channelmirror.command(name = "nuke", description = "List all Servers of wich Bot is Member")
    async def nuke(self, ctx):
        await ctx.respond("Do you really want to Nuke all Channel Mirrors?", ephemeral = True, view = NukeView(self.bot, self.db, self.cursor))
    
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
                destination_guild = await get_or_fetch_guild(self.bot, mirror[2])
                destination_channel = await get_or_fetch_channel(destination_guild, mirror[3])
            except:
                continue
            webhooks = await destination_channel.webhooks()
            for webhook in webhooks:
                if webhook.id == self.cursor.execute(
                    """
                    SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?
                    """,
                    (destination_guild.id, destination_channel.id)
                ).fetchone()[0]:
                    for attachment in message.attachments:
                        repl_message = await webhook.send(content = attachment.url, username = nick + " from " + message.guild.name, avatar_url = message.author.avatar.url)
                    if content:
                        repl_message = await webhook.send(content = content, username = nick + " from " + message.guild.name, avatar_url = message.author.avatar.url, wait = True)
                        self.cursor.execute(
                            """
                            Insert INTO messageids (source_guild_id, source_channel_id, source_message_id, destination_guild_id, destination_channel_id, destination_message_id) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (message.guild.id, message.channel.id, message.id, repl_message.guild.id, repl_message.channel.id, repl_message.id)
                        )
                    break
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
                destination_guild = await get_or_fetch_guild(self.bot, messageid[3])
                destination_channel = await get_or_fetch_channel(destination_guild, messageid[4])
            except:
                continue
            webhooks = await destination_channel.webhooks()
            for webhook in webhooks:
                if webhook.id == self.cursor.execute(
                    """
                    SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?
                    """,
                    (destination_guild.id, destination_channel.id)
                ).fetchone()[0]:
                    await webhook.edit_message(messageid[5], content = after.content)
                    break

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
                destination_guild = await get_or_fetch_guild(self.bot, messageid[3])
                destination_channel = await get_or_fetch_channel(destination_guild, messageid[4])
            except:
                continue
            webhooks = await destination_channel.webhooks()
            for webhook in webhooks:
                if webhook.id == self.cursor.execute(
                    """
                    SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?
                    """,
                    (destination_guild.id, destination_channel.id)
                ).fetchone()[0]:
                    await webhook.delete_message(messageid[5])
                    break

class NukeView(View):
    def __init__(self, bot, db, cursor):
        super().__init__()
        self.bot = bot
        self.db = db
        self.cursor = cursor

    @button(label = "Yes", style = ButtonStyle.danger, custom_id = "yes")
    async def yes(self, button: Button, interaction: Interaction):
        for webhook in self.cursor.execute(
            """
            SELECT * FROM webhooks
            """
        ).fetchall():
            try:
                destination_guild = await get_or_fetch_guild(self.bot, webhook[0])
                destination_channel = await get_or_fetch_channel(destination_guild, webhook[1])
            except:
                continue
            webhooks = await destination_channel.webhooks()
            for webhook in webhooks:
                if webhook.id == self.cursor.execute(
                    """
                    SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?
                    """,
                    (destination_guild.id, destination_channel.id)
                ).fetchone()[0]:
                    await webhook.delete()
                    break
        self.cursor.execute(
            """
            DELETE FROM channelmirror
            """
        )
        self.cursor.execute(
            """
            DELETE FROM messageids
            """
        )
        self.cursor.execute(
            """
            DELETE FROM webhooks
            """
        )
        self.db.commit()
        await interaction.response.edit_message(content = "Nuked all mirrors", view = None)

    @button(label = "No", style = ButtonStyle.success, custom_id = "no")
    async def no(self, button: Button, interaction: Interaction):
        await interaction.response.edit_message(content = "Canceled", view = None)

async def get_or_fetch_guild(bot, guild_id):
    return bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)

async def get_or_fetch_channel(guild, channel_id):
    return guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)

def setup(bot):
    bot.add_cog(ChannelMirror(bot))
