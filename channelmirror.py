from discord import (
    SlashCommandGroup,
    TextChannel,
    Permissions,
    Forbidden,
    NotFound,
    ChannelType
)
from discord.ui import View, Button, button
from discord import ButtonStyle, Interaction
from discord.commands import Option
from discord.ext.commands import Cog
import mariadb
import sys
from login import loginData

class ChannelMirror(Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            self.db = mariadb.connect(user=loginData.user, password=loginData.password, host=loginData.host, port=loginData.port, database="channelmirror")
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            while True:
                print("Do you want to try again? (y/n)")
                answer = input()
                if answer == "n":
                    sys.exit()
                elif answer == "y":
                    try:
                        self.db = mariadb.connect(user=loginData.user, password=loginData.password, host=loginData.host, port=loginData.port, database="channelmirror")
                        break
                    except mariadb.Error as e:
                        print(f"Error connecting to MariaDB Platform: {e}")
                else:
                    print("Invalid input")
        self.db.autocommit = False
        self.cursor = self.db.cursor()
        self.cursor.execute("CREATE TABLE IF NOT EXISTS channelmirror (channelmirror_id INT NOT NULL AUTO_INCREMENT, source_guild_id BIGINT, source_channel_id BIGINT, destination_guild_id BIGINT, destination_channel_id BIGINT, Primary Key (channelmirror_id))")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS messageids (source_guild_id BIGINT, source_channel_id BIGINT, source_message_id BIGINT, destination_guild_id BIGINT, destination_channel_id BIGINT, destination_message_id BIGINT)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS webhooks (guild_id BIGINT, channel_id BIGINT, webhook_id BIGINT)")
        self.db.commit()
        self.channelmirror_cache = {}
        self.cursor.execute("SELECT * FROM channelmirror")
        for mirror in self.cursor:
            if mirror[1] not in self.channelmirror_cache.keys():
                self.channelmirror_cache[mirror[1]] = []
            self.channelmirror_cache[mirror[1]].append(mirror[2])
        self.webhook_cache = {}
    channelmirror = SlashCommandGroup(name = "channelmirror", description = "Commands for channel mirroring", default_member_permissions = Permissions(administrator = True))

    @channelmirror.command(name = "create", description = "Create a channel to mirror")
    async def create(self, ctx,
            source_channel: Option(TextChannel, "The source channel to mirror"),
            destination_channel_guild_id: Option(str, "The destination guild id of channel to mirror"),
            destination_channel_id: Option(str, "The destination channel id to mirror")
        ):
        destination_guild = await get_or_fetch_guild(self.bot, ctx, destination_channel_guild_id)
        if not destination_guild:
            return
        destination_channel = await get_or_fetch_channel(ctx, destination_guild, destination_channel_id)
        if not destination_channel:
            return
        if destination_channel.permissions_for(ctx.author).administrator == False:
            await ctx.respond("You don't have permission to create a mirror in destination guild", ephemeral = True)
            return
        if destination_channel.type != ChannelType.text:
            await ctx.respond("Destination channel is not a text channel", ephemeral = True)
            return
        self.cursor.execute(
            "SELECT * FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        )
        if self.cursor.fetchone():
            await ctx.respond("Mirror already exists", ephemeral = True)
            return
        if destination_channel.permissions_for(await destination_guild.fetch_member(1203722669376409611)).send_messages == False:
            await ctx.respond("I don't have permission to send messages in destination channel", ephemeral = True)
            return
        await self.create_webhook(destination_guild, destination_channel)
        self.cursor.execute(
            "INSERT INTO channelmirror (source_guild_id, source_channel_id, destination_guild_id, destination_channel_id) VALUES (?, ?, ?, ?)",
            (source_channel.guild.id, source_channel.id, destination_guild.id, destination_channel.id)
        )
        self.db.commit()
        if source_channel.guild.id not in self.channelmirror_cache.keys():
            self.channelmirror_cache[source_channel.guild.id] = []
        if source_channel.id not in self.channelmirror_cache[source_channel.guild.id]:
            self.channelmirror_cache[source_channel.guild.id].append(source_channel.id)
        await ctx.respond(f"Created a mirror from {source_channel.mention} to {destination_channel.mention}", ephemeral = True)

    @channelmirror.command(name = "delete", description = "Delete a channel to mirror")
    async def delete(self, ctx,
            source_channel: Option(TextChannel, "The source channel to mirror"),
            destination_channel_guild_id: Option(str, "The destination guild id of channel to mirror"),
            destination_channel_id: Option(str, "The destination channel id to mirror")
        ):
        destination_guild = await get_or_fetch_guild(self.bot, ctx, destination_channel_guild_id)
        if not destination_guild:
            await ctx.respond("Destination guild not found", ephemeral = True)
            return
        destination_channel = await get_or_fetch_channel(ctx, destination_guild, destination_channel_id)
        if not destination_channel:
            await ctx.respond("Destination channel not found", ephemeral = True)
            return
        if destination_channel.type != ChannelType.text:
            await ctx.respond("Destination channel is not a text channel", ephemeral = True)
            return
        self.cursor.execute(
            "SELECT * FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        )
        if not self.cursor.fetchone():
            await ctx.respond("Mirror not found", ephemeral = True)
            return
        self.cursor.execute(
            "DELETE FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        )
        self.cursor.execute(
            "DELETE FROM messageids WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_guild.id, destination_channel.id)
        )
        await self.delete_webhook(destination_guild, destination_channel)
        self.db.commit()
        self.cursor.execute(
            "SELECT * FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ?",
            (source_channel.guild.id, source_channel.id)
        )
        if not self.cursor.fetchone():
            if source_channel.guild.id in self.channelmirror_cache.keys():
                if source_channel.id in self.channelmirror_cache[source_channel.guild.id]:
                    self.channelmirror_cache[source_channel.guild.id].remove(source_channel.id)
        await ctx.respond(f"Deleted mirror from {source_channel.mention} to {destination_channel.mention}", ephemeral = True)

    @channelmirror.command(name = "delete_by_number", description = "Delete a channel to mirror")
    async def delete_by_number(self, ctx,
            link_number: Option(int, "The Link number to delete")
        ):
        link_number -= 1
        mirrors = await self.get_channelmirrors(ctx.guild.id)
        if not mirrors:
            await ctx.respond("No mirrors found", ephemeral = True)
            return
        if link_number < 0 or link_number >= len(mirrors):
            await ctx.respond(content = "Invalid link number", ephemeral = True)
        mirror = mirrors[link_number]
        self.cursor.execute(
            "DELETE FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (mirror[1].id, mirror[2].id, mirror[3].id, mirror[4].id)
        )
        self.cursor.execute(
            "DELETE FROM messageids WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (mirror[1].id, mirror[2].id, mirror[3].id, mirror[4].id)
        )
        self.delete_webhook(mirror[3], mirror[4])
        self.db.commit()
        self.cursor.execute(
            "SELECT * FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ?",
            (mirror[1].id, mirror[2].id)
        )
        if not self.cursor.fetchone():
            if mirror[1].id in self.channelmirror_cache.keys():
                if mirror[2].id in self.channelmirror_cache[mirror[1].id]:
                    self.channelmirror_cache[mirror[1].id].remove(mirror[2].id)
        await ctx.respond(content = f"Deleted mirror from {mirror[2].mention} to {mirror[4].mention}", ephemeral = True)

    @channelmirror.command(name = "list", description = "List all mirrors")
    async def list(self, ctx):
        await ctx.respond("Loading...", ephemeral = True)
        mirrors = await self.get_channelmirrors(ctx.guild.id)
        if not mirrors:
            await ctx.edit(content = "No mirrors found")
            return
        message = "Channel Mirrors:\n"
        for i, mirror in enumerate(mirrors):
                source_channel_mention = "Unknown"
                destination_channel_mention = "Unknown"
                if mirror[1] and mirror[2]:
                    source_channel_mention = mirror[2].mention
                if mirror[3] and mirror[4]:
                    destination_channel_mention = mirror[4].mention
                message += f"{i + 1}. Mirror from {source_channel_mention} to {destination_channel_mention}\n"
        await ctx.edit(content = message)

    @channelmirror.command(name = "server", description = "List all Servers of wich Bot is Member")
    async def server(self, ctx):
        server = self.bot.guilds
        message = "Servers:\n"
        for i, s in enumerate(server):
            message += f"{i + 1}. {s.name}\n"
        await ctx.respond(content = message, ephemeral = True)

    @channelmirror.command(name = "nuke", description = "List all Servers of wich Bot is Member")
    async def nuke(self, ctx):
        await ctx.respond("Do you really want to Nuke all Channel Mirrors?", ephemeral = True, view = NukeView(self.bot, self.db, self.cursor))

    @Cog.listener("on_message")
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.guild.id not in self.channelmirror_cache.keys():
            return
        if message.channel.id not in self.channelmirror_cache[message.guild.id]:
            return
        self.cursor.execute(
            "SELECT * FROM channelmirror WHERE source_guild_id = ? AND source_channel_id = ?",
            (message.guild.id, message.channel.id)
        )
        mirrors = self.cursor.fetchall()
        content = message.content.replace("@everyone", "everyone").replace("@here", "here")
        nick = message.author.nick or message.author.display_name
        for mirror in mirrors:
            destination_guild = await get_or_fetch_guild(self.bot, None, mirror[3])
            if not destination_guild:
                continue
            destination_channel = await get_or_fetch_channel(None, destination_guild, mirror[4])
            if not destination_channel:
                continue
            webhook = await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
            if not webhook:
                continue
            files = []
            for attachment in message.attachments:
                files.append(await attachment.to_file())
            repl_message = await webhook.send(content = content, embeds = message.embeds, files = files, username = nick + " from " + message.guild.name, avatar_url = message.author.avatar.url, wait = True)
            self.cursor.execute(
                "Insert INTO messageids (source_guild_id, source_channel_id, source_message_id, destination_guild_id, destination_channel_id, destination_message_id) VALUES (?, ?, ?, ?, ?, ?)",
                (message.guild.id, message.channel.id, message.id, repl_message.guild.id, repl_message.channel.id, repl_message.id)
            )
        self.db.commit()

    @Cog.listener("on_raw_message_edit")
    async def on_message_edit(self, message):
        if message.cached_message:
            if message.cached_message.author.bot:
                return
        source_guild = await get_or_fetch_guild(self.bot, None, message.guild_id)
        if not source_guild:
            return
        source_channel = await get_or_fetch_channel(None, source_guild, message.channel_id)
        if not source_channel:
            return
        message = await source_channel.fetch_message(message.message_id)
        if message.author.bot:
            return
        self.cursor.execute(
            "SELECT * FROM messageids WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ?",
            (message.guild.id, message.channel.id, message.id)
        )
        messageids = self.cursor.fetchall()
        content = message.content.replace("@everyone", "everyone").replace("@here", "here")
        for messageid in messageids:
            destination_guild = await get_or_fetch_guild(self.bot, None, messageid[3])
            if not destination_guild:
                continue
            destination_channel = await get_or_fetch_channel(None, destination_guild, messageid[4])
            if not destination_channel:
                continue
            webhook = await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
            if not webhook:
                continue
            files = []
            for attachment in message.attachments:
                files.append(await attachment.to_file())
            await webhook.edit_message(messageid[5], content = content, embeds = message.embeds, files = files)

    @Cog.listener("on_raw_message_delete")
    async def on_message_delete(self, message):
        self.cursor.execute(
            "SELECT * FROM messageids WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ?",
            (message.guild_id, message.channel_id, message.message_id)
        )
        messageids = self.cursor.fetchall()
        for messageid in messageids:
            destination_guild = await get_or_fetch_guild(self.bot, None, messageid[3])
            if not destination_guild:
                continue
            destination_channel = await get_or_fetch_channel(None, destination_guild, messageid[4])
            if not destination_channel:
                continue
            webhook = await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
            if not webhook:
                continue
            await webhook.delete_message(messageid[5])

    async def create_webhook(self, destination_guild, destination_channel):
        self.cursor.execute(
            "SELECT * FROM webhooks WHERE guild_id = ? AND channel_id = ?",
            (destination_guild.id, destination_channel.id)
        )
        if not self.cursor.fetchone():
            webhook = await destination_channel.create_webhook(name = "ChannelMirror", reason = "ChannelMirror webhook creation")
            self.cursor.execute(
                "INSERT INTO webhooks (guild_id, channel_id, webhook_id) VALUES (?, ?, ?)",
                (destination_guild.id, destination_channel.id, webhook.id)
            )
            if destination_guild.id not in self.webhook_cache.keys():
                self.webhook_cache[destination_guild.id] = {}
            self.webhook_cache[destination_guild.id][destination_channel.id] = webhook

    async def delete_webhook(self, destination_guild, destination_channel):
        self.cursor.execute(
            "SELECT * FROM channelmirror WHERE destination_guild_id = ? AND destination_channel_id = ?",
            (destination_guild.id, destination_channel.id)
        )
        if not self.cursor.fetchone():
            webhooks = await destination_channel.webhooks()
            for webhook in webhooks:
                self.cursor.execute(
                    "SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?",
                    (destination_guild.id, destination_channel.id)
                )
                if webhook.id == self.cursor.fetchone()[0]:
                    await webhook.delete()
                    break
            self.cursor.execute(
                "DELETE FROM webhooks WHERE guild_id = ? AND channel_id = ?",
                (destination_guild.id, destination_channel.id)
            )
            self.webhook_cache[destination_guild.id].pop(destination_channel.id)

    async def get_channelmirrors(self, guild_id):
        self.cursor.execute("SELECT * FROM channelmirror")
        mirrors = self.cursor.fetchall()
        out = {}
        order = []
        for mirror in mirrors:
            if mirror[1] == guild_id or mirror[3] == guild_id:
                source_guild = await get_or_fetch_guild(self.bot, None, mirror[1])
                destination_guild = await get_or_fetch_guild(self.bot, None, mirror[3])
                source_channel = await get_or_fetch_channel(None, source_guild, mirror[2])
                destination_channel = await get_or_fetch_channel(None, destination_guild, mirror[4])
                out[mirror[0]] = (source_guild, source_channel, destination_guild, destination_channel)
                order.append(mirror[0])
        order.sort()
        return [out[i] for i in order]

    async def get_or_fetch_webhook(self, guild_id, channel_id):
        if guild_id not in self.webhook_cache.keys():
            self.webhook_cache[guild_id] = {}
        if channel_id in self.webhook_cache[guild_id].keys():
            return self.webhook_cache[guild_id][channel_id]
        destination_guild = await get_or_fetch_guild(self.bot, None, guild_id)
        if not destination_guild:
            return
        destination_channel = await get_or_fetch_channel(None, destination_guild, channel_id)
        if not destination_channel:
            return
        webhooks = await destination_channel.webhooks()
        self.cursor.execute(
            "SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id)
        )
        webhook_id = self.cursor.fetchone()
        if webhook_id:
            for webhook in webhooks:
                if webhook.id == webhook_id[0]:
                    self.webhook_cache[guild_id][channel_id] = webhook
                    return webhook
        if channel_id not in self.webhook_cache[guild_id].keys():
            webhook = await destination_channel.create_webhook(name = "ChannelMirror", reason = "ChannelMirror webhook creation")
            self.cursor.execute(
                "SELECT * FROM webhooks WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id)
            )
            if self.cursor.fetchone():
                self.cursor.execute(
                    "UPDATE webhooks SET webhook_id = ? WHERE guild_id = ? AND channel_id = ?",
                    (webhook.id, guild_id, channel_id)
                )
            else:
                self.cursor.execute(
                    "INSERT INTO webhooks (guild_id, channel_id, webhook_id) VALUES (?, ?, ?)",
                    (guild_id, channel_id, webhook.id)
                )
            self.db.commit()
            self.webhook_cache[guild_id][channel_id] = webhook
            return webhook

async def get_or_fetch_guild(bot, ctx, guild_id):
    try:
        return bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
    except Forbidden:
        if ctx:
            await ctx.respond("Not a member of destination guild", ephemeral = True)
        return
    except NotFound:
        if ctx:
            await ctx.respond("Destination guild doesn't exist", ephemeral = True)
        return
    except:
        if ctx:
            await ctx.respond("An error occurred", ephemeral = True)
        return

async def get_or_fetch_channel(ctx, guild, channel_id):
    try:
        return guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
    except Forbidden:
        if ctx:
            await ctx.respond("I Can't see the destination Channel", ephemeral = True)
        return
    except NotFound:
        if ctx:
            await ctx.respond("Destination channel doesn't exist", ephemeral = True)
        return
    except:
        if ctx:
            await ctx.respond("An error occurred", ephemeral = True)
        return

class NukeView(View):
    def __init__(self, bot, db, cursor):
        super().__init__(timeout=5)
        self.bot = bot
        self.db = db
        self.cursor = cursor

    @button(label = "Yes", style = ButtonStyle.danger, custom_id = "yes")
    async def yes(self, button: Button, interaction: Interaction):
        await self.message.delete()
        await interaction.response.send_message(content = "Do you REALLY want to Nuke ALL Channel Mirrors?", view = NukeView2(self.bot, self.db, self.cursor), ephemeral=True)
        self.stop()

    @button(label = "No", style = ButtonStyle.success, custom_id = "no")
    async def no(self, button: Button, interaction: Interaction):
        await self.message.edit(content = "Canceled", view = None)
        self.stop()

    async def on_timeout(self):
        await self.message.edit(content = "Timed out", view = None)

class NukeView2(View):
    def __init__(self, bot, db, cursor):
        super().__init__(timeout=5)
        self.bot = bot
        self.db = db
        self.cursor = cursor

    @button(label = "Yes", style = ButtonStyle.danger, custom_id = "yes")
    async def yes(self, button: Button, interaction: Interaction):
        self.cursor.execute("SELECT * FROM webhooks")
        for webhook in self.cursor.fetchall():
            destination_guild = await get_or_fetch_guild(self.bot, None, webhook[0])
            if not destination_guild:
                continue
            destination_channel = await get_or_fetch_channel(None, destination_guild, webhook[1])
            if not destination_channel:
                continue
            webhooks = await destination_channel.webhooks()
            for webhook in webhooks:
                self.cursor.execute(
                    "SELECT webhook_id FROM webhooks WHERE guild_id = ? AND channel_id = ?",
                    (destination_guild.id, destination_channel.id)
                )
                if webhook.id == self.cursor.fetchone()[0]:
                    await webhook.delete()
                    break
        self.cursor.execute("DELETE FROM channelmirror")
        self.cursor.execute("DELETE FROM messageids")
        self.cursor.execute("DELETE FROM webhooks")
        self.db.commit()
        await self.message.delete()
        await interaction.response.send_message(content = "Nuked all Channel Mirrors", view = None, ephemeral=True)
        self.stop()

    async def on_timeout(self):
        await self.message.edit(content = "Timed out", view = None)

    @button(label = "No", style = ButtonStyle.success, custom_id = "no")
    async def no(self, button: Button, interaction: Interaction):
        await self.message.edit(content = "Canceled", view = None)
        self.stop()

def setup(bot):
    bot.add_cog(ChannelMirror(bot))
