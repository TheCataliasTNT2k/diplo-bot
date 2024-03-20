import re
import traceback
from re import findall

from discord import (
    SlashCommandGroup,
    TextChannel,
    Permissions,
    Webhook,
    Guild,
    ButtonStyle,
    Interaction, Message, Bot, Embed, Colour, SlashCommandOptionType, RawMessageDeleteEvent
)
from discord.commands import Option
from discord.ext.bridge import Context
from discord.ext.commands import Cog
from discord.ui import View, Button, button

from .database import get_cursor


class Mirror:
    mirror_id: int
    source_guild: Guild | None
    source_channel: TextChannel | None
    destination_guild: Guild | None
    destination_channel: TextChannel | None
    webhook: Webhook | None
    webhook_id: int

    @staticmethod
    async def from_db(bot: Bot, mirror: list):
        m = Mirror()
        m.mirror_id = mirror[0]
        m.source_guild = bot.get_guild(mirror[1])
        if m.source_guild:
            m.source_channel = m.source_guild.get_channel(mirror[2])
        m.destination_guild = bot.get_guild(mirror[3])
        if m.destination_guild:
            m.destination_channel = m.destination_guild.get_channel(mirror[4])
        m.webhook_id = mirror[5]
        m.webhook = None
        await m.fetch_or_create_webhook()
        if not m.check_init():
            # TODO logging, something does no longer exist, mirror will not work
            pass
        return m

    def check_init(self):
        return all([
            self.source_guild, self.source_channel,
            self.destination_guild, self.destination_channel
        ])

    @staticmethod
    async def create(ctx: Context, bot: Bot, source_channel: TextChannel, destination_channel: TextChannel):
        # create new channel mirror and webhook
        cur = get_cursor()
        webhook = await destination_channel.create_webhook(
            name=f"ChannelMirror from {source_channel.name} ({source_channel.guild.name})",
            reason="ChannelMirror webhook creation"
        )

        # save everything
        cur.execute(
            "INSERT INTO cmr_mirrors "
            "(source_guild_id, source_channel_id, destination_guild_id, destination_channel_id, webhook_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (source_channel.guild.id, source_channel.id, destination_channel.guild.id, destination_channel.id, webhook.id)
        )
        try:
            cur.connection.commit()
        except Exception:  # noqa
            print(traceback.format_exc())
            cur.connection.rollback()
            await respond_with_error_embed(ctx, "An error occurred! See log for more details.")

        cur.execute(
            "SELECT * FROM cmr_mirrors WHERE "
            "source_guild_id = ? AND source_channel_id = ? AND "
            "destination_guild_id = ? and destination_channel_id = ?",
            (source_channel.guild.id, source_channel.id, destination_channel.guild.id, destination_channel.id)
        )
        if data := cur.fetchone():
            mirror = await Mirror().from_db(bot, data)
            return mirror
        return None

    async def delete(self, cog: "ChannelMirror", ctx: Context | None = None):
        # delete webhook and mirror
        await self.delete_webhook()
        cur = get_cursor()
        cur.execute(
            "DELETE FROM cmr_mirrors WHERE channel_mirror_id = ?",
            (self.mirror_id, )
        )

        try:
            cur.connection.commit()
        except Exception:  # noqa
            print(traceback.format_exc())
            cur.connection.rollback()
            if ctx:
                await ctx.respond("An error occurred", ephemeral=True)
            return

        cur = get_cursor()
        cur.execute(
            "SELECT * FROM cmr_mirrors WHERE channel_mirror_id = ?",
            (self.mirror_id, )
        )
        if not cur.fetchall():
            if (mirrors := cog.channel_mirror_cache.get(self.source_channel.id)) and self in mirrors:
                mirrors.remove(self)
        if ctx:
            await ctx.respond(f"Deleted mirror from {self.source_channel.mention} to {self.destination_channel.mention}.",
                          ephemeral=True)

    # database stuff
    async def save(self, ctx: Context):
        cur = get_cursor()
        if not self.check_existence(self.source_channel.id, self.destination_channel.id):
            cur.execute(
                "INSERT INTO cmr_mirrors "
                "(source_guild_id, source_channel_id, destination_guild_id, destination_channel_id, webhook_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (self.source_guild.id, self.source_channel.id,
                 self.destination_guild.id, self.destination_channel.id,
                 self.webhook.id)
            )
        else:
            cur.execute(
                "UPDATE cmr_mirrors "
                "SET source_guild_id = ?, source_channel_id = ?, destination_guild_id = ?, "
                "destination_channel_id = ?, webhook_id = ? where channel_mirror_id = ? ",
                (self.source_guild.id, self.source_channel.id,
                 self.destination_guild.id, self.destination_channel.id,
                 self.webhook.id)
            )
        try:
            cur.connection.commit()
        except Exception:  # noqa
            print(traceback.format_exc())
            cur.connection.rollback()
            await respond_with_error_embed(ctx, "An error occurred! See log for more details.")

    @staticmethod
    async def check_existence(source_channel_id: int, destination_channel_id: int) -> bool:
        cur = get_cursor()
        cur.execute("SELECT (1) from cmr_mirrors where source_channel_id = ? and destination_channel_id = ?",
                    (source_channel_id, destination_channel_id)
                    )
        return bool(cur.fetchone())

    # Webhook handling
    async def create_webhook(self):
        if not self.check_init():
            return
        webhook = await self.destination_channel.create_webhook(
            name=f"ChannelMirror from {self.source_channel.name} ({self.source_channel.guild.name})",
            reason="ChannelMirror webhook creation"
        )
        self.webhook = webhook

    async def delete_webhook(self):
        if self.webhook or self.fetch_or_create_webhook(False):
            await self.webhook.delete()
            self.webhook = None

    async def fetch_or_create_webhook(self, create_if_missing: bool = True):
        if self.webhook:
            return self.webhook
        if not self.destination_channel:
            return
        if not self.destination_channel.permissions_for(self.destination_guild.me).manage_webhooks:
            return
        for webhook in await self.destination_channel.webhooks():
            if webhook.id == self.webhook_id:
                self.webhook = webhook
                return webhook

        if create_if_missing:
            await self.create_webhook()

    # Message handling
    async def forward_message(self, message: Message):
        content = message.content.replace("@everyone", "everyone").replace("@here", "here")
        nick = message.author.nick or message.author.display_name
        avatar_url = message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
        username = f"{nick} in '{message.channel.name}' on '{message.guild.name}'"
        for match in findall("discord", username, re.IGNORECASE):
            if (new := match.replace("i", "ⅰ")) != match:
                username = username.replace(match, new)
            elif (new := match.replace("I", "Ⅰ")) != match:
                username = username.replace(match, new)
            else:
                # TODO LOGGING
                pass

        files = []
        cur = get_cursor()
        for attachment in message.attachments:
            files.append(await attachment.to_file())

        webhook = await self.fetch_or_create_webhook()

        try:
            repl_message = await webhook.send(content=content, embeds=message.embeds, files=files,
                                              username=username,
                                              avatar_url=avatar_url, wait=True)
        except Exception:
            # TODO Logging
            return

        cur.execute(
            "INSERT INTO cmr_messages "
            "(channel_mirror_id, source_message_id, destination_message_id) VALUES (?, ?, ?)",
            (self.mirror_id, message.id, repl_message.id)
        )
        try:
            cur.connection.commit()
        except Exception:  # noqa
            # TODO LOGGING
            print(traceback.format_exc())
            cur.connection.rollback()

    async def edit_message(self, message: Message):
        # TODO lösung überlegen!
        """
        TODO
            aus den pycord docs:
            Since the data payload can be partial, care must be taken when accessing stuff in the dictionary.
            One example of a common case of partial data is when the 'content' key is inaccessible.
            This denotes an “embed” only edit, which is an edit in which only the embeds are updated by the Discord embed server.

            das kann, wenn man das ungeprüft übernimmt, im zweifel auch nachichteninhalte "verlieren"



        if not message.
        message = await source_channel.fetch_message(message.message_id)
        if message.author.bot:
            return

        cur = get_cursor()
        cur.execute(
            "SELECT * FROM cmr_messages WHERE source_guild_id = ? AND source_channel_id = ? AND source_message_id = ?",
            (message.guild.id, message.channel.id, message.id)
        )
        messageids = cur.fetchall()
        content = message.content.replace("@everyone", "everyone").replace("@here", "here")
        for messageid in messageids:
            destination_guild = await get_guild(self.bot, None, messageid[3])
            if not destination_guild:
                continue
            destination_channel = await get_channel(None, destination_guild, messageid[4])
            if not destination_channel:
                continue
            webhook = await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
            if not webhook:
                continue
            files = []
            for attachment in message.attachments:
                files.append(await attachment.to_file())
            try:
                await webhook.edit_message(messageid[5], content=content, embeds=message.embeds, files=files)
            except:
                self.webhook_cache[destination_guild.id].pop(destination_channel.id)
                await self.get_or_fetch_webhook(destination_guild.id, destination_channel.id)
                await webhook.edit_message(messageid[5], content=content, embeds=message.embeds, files=files)"""
        pass


# Embed responses
async def respond_with_success_embed(ctx: Context, text: str, ephemeral=True) -> Message:
    return await ctx.respond(
        embed=Embed(colour=Colour.from_rgb(0, 255, 0), title="Success", description=text),
        ephemeral=ephemeral
    )


async def respond_with_error_embed(ctx: Context, text: str, ephemeral=True) -> Message:
    return await ctx.respond(
        embed=Embed(colour=Colour.from_rgb(255, 0, 0), title="Error", description=text),
        ephemeral=ephemeral
    )


class ChannelMirror(Cog):
    # mapping from "source channel ID" -> set[Mirror]
    channel_mirror_cache: dict[int, set[Mirror]]

    def __init__(self, bot: Bot):
        self.bot: Bot = bot

        # create tables if missing
        cur = get_cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS cmr_mirrors ("
            "channel_mirror_id INT NOT NULL AUTO_INCREMENT, "
            "source_guild_id BIGINT UNSIGNED, "
            "source_channel_id BIGINT UNSIGNED, "
            "destination_guild_id BIGINT UNSIGNED, "
            "destination_channel_id BIGINT UNSIGNED, "
            "webhook_id BIGINT UNSIGNED, "
            "Primary Key (channel_mirror_id), "
            "UNIQUE (source_channel_id, destination_channel_id))"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS cmr_messages ("
            "channel_mirror_id INT NOT NULL, "
            "source_message_id BIGINT UNSIGNED, "
            "destination_message_id BIGINT UNSIGNED, "
            "CONSTRAINT `message_mirror_key` "
            "FOREIGN KEY (channel_mirror_id) REFERENCES cmr_mirrors (channel_mirror_id) "
            "ON DELETE CASCADE "
            "ON UPDATE RESTRICT) "
        )
        cur.connection.commit()

        # init cache
        self.channel_mirror_cache = {}

    async def init_mirror_cache(self):
        cur = get_cursor()
        cur.execute("SELECT * FROM cmr_mirrors ORDER BY channel_mirror_id")
        mirrors = cur.fetchall()
        cache: dict[int, set[Mirror]] = {}
        for mirror in mirrors:
            m = await Mirror.from_db(self.bot, mirror)
            if not m.check_init():
                continue
            cache.setdefault(int(mirror[2]), set()).add(m)
        self.channel_mirror_cache = cache

    @Cog.listener("on_ready")
    async def on_ready(self):
        await self.init_mirror_cache()
        print("INFO: ChannelMirror ready!")

    @Cog.listener("on_message")
    async def on_message(self, message: Message):
        if message.author.bot:
            return
        if not (mirrors := self.channel_mirror_cache.get(message.channel.id)):
            return

        for mirror in mirrors:
            await mirror.forward_message(message)

    @Cog.listener("on_raw_message_edit")
    async def on_message_edit(self, message: Message):
        pass
        """ TODO fix me
        if message.author.bot:
            return
        if not (mirrors := self.channel_mirror_cache.get(message.channel.id)):
            return

        for mirror in mirrors:
            await mirror.edit_message(message)"""

    @Cog.listener("on_raw_message_delete")
    async def on_message_delete(self, message: RawMessageDeleteEvent):
        channel_id: int
        message_id: int
        cur = get_cursor()
        if message.cached_message:
            message = message.cached_message
            channel_id = message.channel.id
            message_id = message.id
        else:
            channel_id = message.channel_id
            message_id = message.message_id

        cur.execute("DELETE FROM cmr_messages where destination_message_id = ?", (message_id, ))

        cur.execute(
            "SELECT cmr_messages.channel_mirror_id, destination_message_id FROM cmr_messages "
            "JOIN diplo.cmr_mirrors cm on cm.channel_mirror_id = cmr_messages.channel_mirror_id "
            "WHERE source_message_id = ?",
            (message.id, )
        )
        messages = cur.fetchall()
        cur.execute("DELETE FROM cmr_messages where source_message_id = ?", (message.id, ))
        try:
            cur.connection.commit()
        except Exception:
            # TODO LOGGING
            print(traceback.format_exc())
            cur.connection.rollback()

        mirrors = self.channel_mirror_cache.get(channel_id)
        for msg in messages:
            for mirror in mirrors:
                if mirror.mirror_id == msg[0]:
                    webhook = await mirror.fetch_or_create_webhook(False)
                    try:
                        await webhook.delete_message(msg[1])
                    except Exception:
                        print(traceback.format_exc())
                        # TODO LOGGING
                        pass

    channel_mirror = SlashCommandGroup(name="channel_mirror", description="Commands for channel mirroring",)
                                       #default_member_permissions=Permissions(administrator=True)) # TODO wieder anschalten!

    @channel_mirror.command(name="create", description="Create a channel to mirror")
    async def create(self, ctx,
                     source_channel: Option(TextChannel, "The source channel to mirror"),
                     destination_guild_id: Option(str, "The guild id of the destination channel"),
                     destination_channel_id: Option(str, "The destination channel id of the mirror")
                     ):
        # can not be put into function definition, thanks pycord
        ctx: Context
        source_channel: TextChannel
        if not destination_guild_id.isnumeric() or not destination_channel_id.isnumeric():
            await respond_with_error_embed(ctx, "Destination values have to be ids!")
            return

        # get destination channel
        destination_guild_id = int(destination_guild_id)
        if not (destination_guild := self.bot.get_guild(destination_guild_id)):
            await respond_with_error_embed(
                ctx, "Destination guild was not found. Make sure that I am a member of that guild!"
            )
            return
        destination_channel_id = int(destination_channel_id)
        destination_channel: TextChannel
        if not (destination_channel := self.bot.get_channel(destination_channel_id)):  # noqa
            await respond_with_error_embed(
                ctx, "Destination channel was not found. Make sure that I can see the channel!"
            )
            return

        # other checks
        if not isinstance(destination_channel, TextChannel):
            await respond_with_error_embed(ctx, "Destination channel is not a text channel!")
            return
        if source_channel.id == destination_channel_id:
            await respond_with_error_embed(ctx, "Source and destination channel must be different!")
            return

        # check permissions
        if not source_channel.permissions_for(source_channel.guild.me).read_messages:
            await respond_with_error_embed(ctx, "I don't have permission to read messages in the source channel!")
            return
        if not destination_channel.permissions_for(ctx.author).manage_webhooks:
            await respond_with_error_embed(
                ctx,
                "You don't have permission to create a mirror in the destination channel!"
            )
            return
        if not destination_channel.permissions_for(destination_guild.me).manage_webhooks:
            await respond_with_error_embed(
                ctx,
                "I don't have permission to create a webhook in the destination channel!"
            )
            return

        # check if mirror already exists
        if await Mirror.check_existence(source_channel.id, destination_channel_id):
            await respond_with_error_embed(ctx, "Mirror already existing!")
            return

        mirror = await Mirror.create(ctx, self.bot, source_channel, destination_channel)

        # store new mirror in cache
        self.channel_mirror_cache.setdefault(source_channel.id, set()).add(mirror)
        await respond_with_success_embed(
            ctx,
            f"Created a mirror from {source_channel.mention} to {destination_channel.mention}."
        )

    @channel_mirror.command(name="delete", description="Delete a mirror")
    async def delete(self, ctx,
                     source_channel: Option(TextChannel, "The source channel to mirror"),
                     destination_channel_id: Option(str, "The destination channel id of the mirror")
                     ):
        # can not be put into function definition, thanks pycord
        ctx: Context
        source_channel: TextChannel
        if not destination_channel_id.isnumeric():
            await respond_with_error_embed(ctx, "Destination channel has to be a channel id!")
            return

        # check if given mirror exists
        if not (mirrors := self.channel_mirror_cache.get(source_channel.id)):
            await respond_with_error_embed(ctx, "Mirror not found!")
            return
        if not (matching := list(
                filter(lambda x: x.destination_channel and x.destination_channel.id == destination_channel_id, mirrors)
        )):
            await respond_with_error_embed(ctx, "Mirror not found!")
            return

        await matching[0].delete()
        await respond_with_success_embed(
            ctx,
            f"Mirror from {source_channel.mention} to {matching[0].destination_channel.mention} deleted."
        )

    @channel_mirror.command(name="delete_by_number", description="Delete a mirror by its index")
    async def delete_by_number(self, ctx,
                               link_number: Option(int, "The Link number to delete")
                               ):
        # can not be put into function definition, thanks pycord
        ctx: Context

        matching: list[Mirror]
        # check if given mirror exists
        if not (matching := list(
                filter(lambda x: x.mirror_id == link_number, [m for s in self.channel_mirror_cache.values() for m in s])
        )):
            await respond_with_error_embed(ctx, "Mirror not found!")
            return

        await matching[0].delete(self, ctx)

    @channel_mirror.command(name="list", description="List all mirrors for this server")
    async def list(self, ctx):
        # can not be put into function definition, thanks pycord
        ctx: Context
        await ctx.respond("Loading...", ephemeral=True)

        source_mirrors = []
        destination_mirrors = []
        for mirror in [m for s in self.channel_mirror_cache.values() for m in s]:
            if mirror.source_guild.id == ctx.guild.id:
                source_mirrors.append(mirror)
                continue
            if mirror.destination_guild.id == ctx.guild.id:
                destination_mirrors.append(mirror)
        if not source_mirrors and not destination_mirrors:
            await respond_with_error_embed(ctx, "No mirrors found!")
            return

        # create embed
        embed = Embed(colour=Colour.from_rgb(0, 255, 0), title="Channel Mirrors")
        sources = [
            (f":small_orange_diamond: {mirror.mirror_id} "
             f"{mirror.source_channel.mention} -> {mirror.destination_channel.mention} "
             f"\"({mirror.destination_guild.name})\"")
            for mirror in source_mirrors
        ]
        destinations = [
            (f":small_orange_diamond: {mirror.mirror_id} "
             f"{mirror.source_channel.mention} \"({mirror.source_guild.name})\" "
             f"-> {mirror.destination_channel.mention}")
            for mirror in destination_mirrors
        ]
        embed.add_field(name="Mirrors **from** here:", value="\n".join(sources) or "None", inline=False)
        embed.add_field(name="Mirrors **to** here:", value="\n".join(destinations) or "None", inline=False)

        await ctx.edit(content="", embed=embed)

    @channel_mirror.command(name="servers", description="List all servers of wich Bot is member")
    async def server(self, ctx):
        # can not be put into function definition, thanks pycord
        ctx: Context
        servers = self.bot.guilds

        # create embed
        embed = Embed(colour=Colour.from_rgb(0, 255, 0), title="Servers")

        if servers:
            embed.add_field(name="** **", value="\n".join([f"{i}. {server.name}" for i, server in enumerate(servers)]))
        else:
            embed.add_field(name="** **", value="None")

        await ctx.respond(embed=embed, ephemeral=True)

    @channel_mirror.command(name="reinit", description="Reload configuration from database (normally not needed)")
    async def reinit(self, ctx):
        # can not be put into function definition, thanks pycord
        ctx: Context
        await self.init_mirror_cache()
        await respond_with_success_embed(ctx, "Done")

    @channel_mirror.command(name="nuke", description="Delete ALL mirrors on ALL servers")
    async def nuke(self, ctx):
        await ctx.respond("Do you really want to Nuke all Channel Mirrors?", ephemeral=True, view=NukeView(self))


class NukeView(View):
    def __init__(self, bot):
        super().__init__(timeout=15)
        self.bot = bot

    @button(label="Yes", style=ButtonStyle.danger, custom_id="yes")
    async def confirm(self, _: Button, interaction: Interaction):
        await interaction.message.delete()
        await interaction.response.send_message(
            content="Do you ***REALLY*** want to ***DELETE ALL*** Channel Mirrors?",
            view=NukeView2(self.bot), ephemeral=True
        )
        self.stop()

    @button(label="No", style=ButtonStyle.green, custom_id="no")
    async def abort(self, _: Button, interaction: Interaction):
        await interaction.message.edit(content="Cancelled", view=None)
        self.stop()

    async def on_timeout(self):
        await self.message.edit(content="Timed out", view=None)


class NukeView2(View):
    def __init__(self, cog: ChannelMirror):
        super().__init__(timeout=15)
        self.cog = cog

    @button(label="Yes", style=ButtonStyle.danger, custom_id="yes")
    async def yes(self, _: Button, interaction: Interaction):
        for mirror in [m for s in self.cog.channel_mirror_cache.values() for m in s]:
            await mirror.delete(self.cog)
        await interaction.response.send_message(content="Nuked all Channel Mirrors", view=None, ephemeral=True)
        self.stop()

    @button(label="No", style=ButtonStyle.green, custom_id="no")
    async def no(self, _: Button, interaction: Interaction):
        await interaction.message.edit(content="Cancelled", view=None)
        self.stop()

    async def on_timeout(self):
        await self.message.edit(content="Timed out", view=None)


def setup(bot):
    bot.add_cog(ChannelMirror(bot))
