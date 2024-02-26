from discord import (
    SlashCommandGroup,
    TextChannel,
    Permissions,
    Forbidden,
    NotFound,
    ChannelType,
    Webhook,
    Guild,
    ButtonStyle,
    Interaction
)
from discord.ui import View, Button, button
from discord.commands import Option
from discord.ext.commands import Cog

class ChannelMirror(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.cur.execute("CREATE TABLE IF NOT EXISTS cmr_mirrors (channelmirror_id INT NOT NULL AUTO_INCREMENT, source_guild_id BIGINT UNSIGNED, source_channel_id BIGINT UNSIGNED, destination_guild_id BIGINT UNSIGNED, destination_channel_id BIGINT UNSIGNED, Primary Key (channelmirror_id))")
        self.bot.cur.execute("CREATE TABLE IF NOT EXISTS cmr_msgids (source_guild_id BIGINT UNSIGNED, source_channel_id BIGINT UNSIGNED, source_message_id BIGINT UNSIGNED, destination_guild_id BIGINT UNSIGNED, destination_channel_id BIGINT UNSIGNED, destination_message_id BIGINT UNSIGNED)")
        self.bot.cur.execute("CREATE TABLE IF NOT EXISTS cmr_webhooks (guild_id BIGINT UNSIGNED, channel_id BIGINT UNSIGNED, webhook_id BIGINT UNSIGNED)")
        self.bot.con.commit()
        self.channelmirror_cache = {}
        self.bot.cur.execute("SELECT * FROM cmr_mirrors")
        for mirror in self.bot.cur:
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
        self.bot.cur.execute(
            "SELECT * FROM cmr_mirrors WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        )
        if self.bot.cur.fetchall():
            await ctx.respond("Mirror already exists", ephemeral = True)
            return
        if destination_channel.permissions_for(await destination_guild.fetch_member(1203722669376409611)).send_messages == False:
            await ctx.respond("I don't have permission to send messages in destination channel", ephemeral = True)
            return
        await self.create_webhook(destination_guild, destination_channel)
        self.bot.cur.execute(
            "INSERT INTO cmr_mirrors (source_guild_id, source_channel_id, destination_guild_id, destination_channel_id) VALUES (?, ?, ?, ?)",
            (source_channel.guild.id, source_channel.id, destination_guild.id, destination_channel.id)
        )
        try:
            self.bot.con.commit()
        except:
            self.bot.con.rollback()
            await ctx.respond("An error occurred", ephemeral = True)
            return
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
        self.bot.cur.execute(
            "SELECT * FROM cmr_mirrors WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        )
        if not self.bot.cur.fetchall():
            await ctx.respond("Mirror not found", ephemeral = True)
            return
        self.bot.cur.execute(
            "DELETE FROM cmr_mirrors WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_channel_guild_id, destination_channel_id)
        )
        self.bot.cur.execute(
            "DELETE FROM cmr_msgids WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_guild.id, destination_channel.id)
        )
        await self.delete_webhook(destination_guild, destination_channel)
        try:
            self.bot.con.commit()
        except:
            self.bot.con.rollback()
            await ctx.respond("An error occurred", ephemeral = True)
            return
        self.bot.cur.execute(
            "SELECT * FROM cmr_mirrors WHERE source_guild_id = ? AND source_channel_id = ?",
            (source_channel.guild.id, source_channel.id)
        )
        if not self.bot.cur.fetchall():
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
        self.bot.cur.execute(
            "DELETE FROM cmr_mirrors WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (mirror[0].id, mirror[1].id, mirror[2].id, mirror[3].id)
        )
        self.bot.cur.execute(
            "DELETE FROM cmr_msgids WHERE source_guild_id = ? AND source_channel_id = ? AND destination_guild_id = ? AND destination_channel_id = ?",
            (mirror[0].id, mirror[1].id, mirror[2].id, mirror[3].id)
        )
        await self.delete_webhook(mirror[2], mirror[3])
        try:
            self.bot.con.commit()
        except:
            self.bot.con.rollback()
            await ctx.respond("An error occurred", ephemeral = True)
            return
        self.bot.cur.execute(
            "SELECT * FROM cmr_mirrors WHERE source_guild_id = ? AND source_channel_id = ?",
            (mirror[0].id, mirror[1].id)
        )
        if not self.bot.cur.fetchall():
            if mirror[0].id in self.channelmirror_cache.keys():
                if mirror[1].id in self.channelmirror_cache[mirror[0].id]:
                    self.channelmirror_cache[mirror[0].id].remove(mirror[1].id)
        await ctx.respond(content = f"Deleted mirror from {mirror[1].mention} to {mirror[3].mention}", ephemeral = True)

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
                if mirror[0] and mirror[1]:
                    source_channel_mention = mirror[1].mention
                if mirror[2] and mirror[3]:
                    destination_channel_mention = mirror[3].mention
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
        await ctx.respond("Do you really want to Nuke all Channel Mirrors?", ephemeral = True, view = NukeView(self.bot))

    @Cog.listener("on_message")
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.guild.id not in self.channelmirror_cache.keys():
            return
        if message.channel.id not in self.channelmirror_cache[message.guild.id]:
            return
        self.bot.cur.execute(
            "SELECT * FROM cmr_mirrors WHERE source_guild_id = ? AND source_channel_id = ?",
            (message.guild.id, message.channel.id)
        )
        mirrors = self.bot.cur.fetchall()
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
            try:
                repl_message = await webhook.send(content = content, embeds = message.embeds, files = files, username = nick + " from " + message.guild.name, avatar_url = message.author.avatar.url, wait = True)
            except:
                self.webhook_cache[destination_guild.id].pop(destination_channel.id)
                await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
                repl_message = await webhook.send(content = content, embeds = message.embeds, files = files, username = nick + " from " + message.guild.name, avatar_url = message.author.avatar.url, wait = True)
            self.bot.cur.execute(
                "Insert INTO cmr_msgids (source_guild_id, source_channel_id, source_message_id, destination_guild_id, destination_channel_id, destination_message_id) VALUES (?, ?, ?, ?, ?, ?)",
                (message.guild.id, message.channel.id, message.id, repl_message.guild.id, repl_message.channel.id, repl_message.id)
            )
        try:
            self.bot.con.commit()
        except:
            self.bot.con.rollback()

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
        self.bot.cur.execute(
            "SELECT * FROM cmr_msgids WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ?",
            (message.guild.id, message.channel.id, message.id)
        )
        messageids = self.bot.cur.fetchall()
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
            try:
                await webhook.edit_message(messageid[5], content = content, embeds = message.embeds, files = files)
            except:
                self.webhook_cache[destination_guild.id].pop(destination_channel.id)
                await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
                await webhook.edit_message(messageid[5], content = content, embeds = message.embeds, files = files)

    @Cog.listener("on_raw_message_delete")
    async def on_message_delete(self, message):
        self.bot.cur.execute(
            "SELECT * FROM cmr_msgids WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ?",
            (message.guild_id, message.channel_id, message.message_id)
        )
        messageids = self.bot.cur.fetchall()
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
            try:
                await webhook.delete_message(messageid[5])
            except:
                self.webhook_cache[destination_guild.id].pop(destination_channel.id)
                await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
                await webhook.delete_message(messageid[5])
            self.bot.cur.execute(
                "DELETE FROM cmr_msgids WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ? AND destination_guild_id = ? AND destination_channel_id = ? AND destination_message_id = ?",
                (messageid[0], messageid[1], messageid[2], messageid[3], messageid[4], messageid[5])
            )
        try:
            self.bot.con.commit()
        except:
            self.bot.con.rollback()

    async def create_webhook(self, destination_guild, destination_channel):
        self.bot.cur.execute(
            "SELECT * FROM cmr_webhooks WHERE guild_id = ? AND channel_id = ?",
            (destination_guild.id, destination_channel.id)
        )
        if not self.bot.cur.fetchall():
            webhook = await destination_channel.create_webhook(name = "ChannelMirror", reason = "ChannelMirror webhook creation")
            self.bot.cur.execute(
                "INSERT INTO cmr_webhooks (guild_id, channel_id, webhook_id) VALUES (?, ?, ?)",
                (destination_guild.id, destination_channel.id, webhook.id)
            )
            if destination_guild.id not in self.webhook_cache.keys():
                self.webhook_cache[destination_guild.id] = {}
            self.webhook_cache[destination_guild.id][destination_channel.id] = webhook

    async def delete_webhook(self, destination_guild, destination_channel):
        self.bot.cur.execute(
            "SELECT * FROM cmr_mirrors WHERE destination_guild_id = ? AND destination_channel_id = ?",
            (destination_guild.id, destination_channel.id)
        )
        if not self.bot.cur.fetchall():
            webhooks = await destination_channel.webhooks()
            self.bot.cur.execute(
                "SELECT webhook_id FROM cmr_webhooks WHERE guild_id = ? AND channel_id = ?",
                (destination_guild.id, destination_channel.id)
            )
            webhook_id = self.bot.cur.fetchall()[0][0]
            for webhook in webhooks:
                if webhook.id == webhook_id:
                    await webhook.delete()
                    break
            self.bot.cur.execute(
                "DELETE FROM cmr_webhooks WHERE guild_id = ? AND channel_id = ?",
                (destination_guild.id, destination_channel.id)
            )
            self.webhook_cache[destination_guild.id].pop(destination_channel.id)

    async def get_channelmirrors(self, guild_id):
        self.bot.cur.execute("SELECT * FROM cmr_mirrors ORDER BY channelmirror_id ASC")
        mirrors = self.bot.cur.fetchall()
        out = []
        for mirror in mirrors:
            if mirror[1] == guild_id or mirror[3] == guild_id:
                source_guild = await get_or_fetch_guild(self.bot, None, mirror[1])
                destination_guild = await get_or_fetch_guild(self.bot, None, mirror[3])
                source_channel = await get_or_fetch_channel(None, source_guild, mirror[2])
                destination_channel = await get_or_fetch_channel(None, destination_guild, mirror[4])
                out.append((source_guild, source_channel, destination_guild, destination_channel))
        return out

    async def get_or_fetch_webhook(self, guild_id, channel_id) -> Webhook:
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
        self.bot.cur.execute(
            "SELECT webhook_id FROM cmr_webhooks WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id)
        )
        webhook_id = self.bot.cur.fetchall()[0][0]
        if webhook_id:
            for webhook in webhooks:
                if webhook.id == webhook_id:
                    self.webhook_cache[guild_id][channel_id] = webhook
                    return webhook
        webhook = await destination_channel.create_webhook(name = "ChannelMirror", reason = "ChannelMirror webhook creation")
        self.bot.cur.execute(
            "SELECT * FROM cmr_webhooks WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id)
        )
        if self.bot.cur.fetchall():
            self.bot.cur.execute(
                "UPDATE cmr_webhooks SET webhook_id = ? WHERE guild_id = ? AND channel_id = ?",
                (webhook.id, guild_id, channel_id)
            )
        else:
             self.bot.cur.execute(
               "INSERT INTO cmr_webhooks (guild_id, channel_id, webhook_id) VALUES (?, ?, ?)",
                (guild_id, channel_id, webhook.id)
            )
        try:
            self.bot.con.commit()
        except:
            self.bot.con.rollback()
        self.webhook_cache[guild_id][channel_id] = webhook
        return webhook

async def get_or_fetch_guild(bot, ctx, guild_id) -> Guild:
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

async def get_or_fetch_channel(ctx, guild, channel_id) -> TextChannel:
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
    def __init__(self, bot):
        super().__init__(timeout=5)
        self.bot = bot

    @button(label = "Yes", style = ButtonStyle.danger, custom_id = "yes")
    async def yes(self, button: Button, interaction: Interaction):
        await self.message.delete()
        await interaction.response.send_message(content = "Do you REALLY want to Nuke ALL Channel Mirrors?", view = NukeView2(self.bot), ephemeral=True)
        self.stop()

    @button(label = "No", style = ButtonStyle.success, custom_id = "no")
    async def no(self, button: Button, interaction: Interaction):
        await self.message.edit(content = "Canceled", view = None)
        self.stop()

    async def on_timeout(self):
        await self.message.edit(content = "Timed out", view = None)

class NukeView2(View):
    def __init__(self, bot):
        super().__init__(timeout=5)
        self.bot = bot

    @button(label = "Yes", style = ButtonStyle.danger, custom_id = "yes")
    async def yes(self, button: Button, interaction: Interaction):
        self.bot.cur.execute("SELECT * FROM cmr_webhooks")
        for webhook in self.bot.cur.fetchall():
            destination_guild = await get_or_fetch_guild(self.bot, None, webhook[0])
            if not destination_guild:
                continue
            destination_channel = await get_or_fetch_channel(None, destination_guild, webhook[1])
            if not destination_channel:
                continue
            webhooks = await destination_channel.webhooks()
            self.bot.cur.execute(
                "SELECT webhook_id FROM cmr_webhooks WHERE guild_id = ? AND channel_id = ?",
                (destination_guild.id, destination_channel.id)
            )
            webhook_id = self.bot.cur.fetchall()[0][0]
            for webhook in webhooks:
                if webhook.id == webhook_id:
                    await webhook.delete()
                    break
        self.bot.cur.execute("DELETE FROM cmr_mirrors")
        self.bot.cur.execute("DELETE FROM cmr_msgids")
        self.bot.cur.execute("DELETE FROM cmr_webhooks")
        try:
            self.bot.con.commit()
        except:
            self.bot.con.rollback()
            await self.message.delete()
            await interaction.response.send_message(content = "An error occurred", view = None, ephemeral=True)
            self.stop()
            return
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