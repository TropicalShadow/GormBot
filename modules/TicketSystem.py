import asyncio
from discord import (
    ApplicationContext,
    ButtonStyle,
    CategoryChannel,
    Colour,
    Embed,
    Guild,
    Interaction,
    Member,
    PartialEmoji,
    PermissionOverwrite,
    Permissions,
    Role,
    SlashCommandGroup,
    TextChannel,
    VoiceChannel,
    VoiceState,
    option,
)
from discord.ext.commands import Cog, Bot
from utils.Constants import (
    BUILDER_TEAM_ROLE_ID,
    DEV_TEAM_ROLE_ID,
    TICKET_CATEGORY_ID,
    MAIN_GUILD_ID,
)

from typing import TYPE_CHECKING, Optional, Tuple, cast

from discord.ui import Button, View, button
from discord.utils import format_dt, utcnow

from db import IndividualTicket, TicketCategory

if TYPE_CHECKING:
    from utils import GormBot
    from modules.CommissionTracking import CommissionTracking


def allow_user_permissions(
    category: CategoryChannel, member: Member
) -> dict[Role | Member, PermissionOverwrite]:
    overwrites = category.overwrites
    overwrites[category.guild.default_role] = PermissionOverwrite(view_channel=False)
    overwrites[member] = PermissionOverwrite(
        use_slash_commands=True,
        view_channel=True,
        read_message_history=True,
        attach_files=True,
        embed_links=True,
        send_messages=True,
    )
    return overwrites


async def create_ticket(
    bot: "GormBot", user: Member, guild: Guild, category: TicketCategory
) -> Tuple[Optional[IndividualTicket], str | TextChannel]:

    ticket_category = cast(CategoryChannel, guild.get_channel(TICKET_CATEGORY_ID))
    if ticket_category is None:
        return (
            None,
            f"Ticket category Id not found (ticket.json), please contact an admin, {TICKET_CATEGORY_ID}",
        )

    permissions = allow_user_permissions(ticket_category, user)

    channel = await ticket_category.create_text_channel(
        f"{category.value.title()}-{user.display_name}",
        topic=f"{category.value.title()} ticket for {user}",
        reason="Ticket System",
        overwrites=permissions,
    )

    ticket = IndividualTicket(
        channel_id=channel.id,
        category=category,
        author_id=user.id,
        author_name=user.display_name,
    )

    async with bot.db.ticket_session() as tickets:
        err = await tickets.create_ticket(ticket)
        if err is not None:
            bot.logger.error("failed to create ticket")
            asyncio.create_task(channel.delete(reason="Database insert failed"))
            return (None, "failed to create ticket")

    emb = Embed(
        title=f"{category.value.title()} ticket",
        colour=Colour.blue(),
        timestamp=utcnow(),
    )
    emb.add_field(name="Opened By", value=f"{user.mention}", inline=True)
    emb.add_field(name="Category", value=f"{category.value.title()}", inline=True)
    emb.add_field(name="Status", value="Open", inline=True)
    emb.add_field(name="Open Time", value=f"{format_dt(utcnow())}", inline=True)

    emb.set_footer(text=f"ticket for {user}", icon_url=user.display_avatar)

    content = user.mention
    if category == TicketCategory.builder:
        content += f" <@&{BUILDER_TEAM_ROLE_ID}>"
    elif category == TicketCategory.developer:
        content += f" <@&{DEV_TEAM_ROLE_ID}>"

    first_message = await channel.send(content=content, embed=emb, view=CloseTicket())

    ticket.first_message = first_message.id
    async with bot.db.ticket_session() as tickets:
        await tickets.upsert_ticket(ticket)

    return ticket, channel


class TicketSystem(Cog):

    def __init__(self, bot: "GormBot"):
        self.bot: GormBot = bot

    async def _audit_log(self, content: str):
        audit = self.bot.get_cog("AuditSystem")
        if audit:
            await audit.send_log(content=content)

    async def _close_ticket(
        self, bot: "GormBot", guild: Guild, channel: TextChannel, closed_by: Member
    ):
        async with bot.db.ticket_session() as tickets:
            ticket = await tickets.get_ticket(channel.id)
            author_name = ticket.author_name if ticket else "unknown"
            author_id = ticket.author_id if ticket else "unknown"
            category = ticket.category.value if ticket else "unknown"

            if ticket and ticket.voice_channel:
                voice_channel = guild.get_channel(ticket.voice_channel)
                if voice_channel:
                    await voice_channel.delete(reason="ticket closed")

            await channel.edit(name=f"closed-{author_name}")
            await asyncio.sleep(1)
            await tickets.delete_ticket(channel.id)
            await self._audit_log(
                f"{closed_by.id} {closed_by.display_name} Closed {author_id} {author_name}'s {category} ticket"
            )
            await channel.delete(
                reason=f"Ticket Closed by {closed_by.id} {closed_by.display_name}"
            )

    TICKET_SLASH_COMMAND_GROUP = SlashCommandGroup(
        name="ticket", description="management of the ticket system"
    )

    @TICKET_SLASH_COMMAND_GROUP.command(
        name="send_ticket_menu",
        default_member_permissions=Permissions(administrator=True),
    )
    async def send_ticket_menu(self, context: ApplicationContext):
        channel = context.channel

        emb = Embed(title="Ticket Creation")

        await channel.send(embed=emb, view=TicketSelector())

        await context.respond(content="Sent Menu", ephemeral=True)

    @TICKET_SLASH_COMMAND_GROUP.command(
        name="debug_ticket", default_member_permissions=Permissions(administrator=True)
    )
    async def send_debug_ticket(self, context: ApplicationContext):
        async with self.bot.db.ticket_session() as tickets:
            ticket_ids = await tickets.get_all_ticket_ids()
            if not ticket_ids:
                await context.respond(content="No tickets found")
                return
            ticket_strs = []
            for tid in ticket_ids:
                ticket = await tickets.get_ticket(tid)
                if ticket:
                    ticket_strs.append(
                        f"<#{tid}>: {ticket.category.value} by {ticket.author_name}"
                    )
            await context.respond(
                content=(
                    "\n".join(ticket_strs)[:2000] if ticket_strs else "No tickets found"
                )
            )

    @TICKET_SLASH_COMMAND_GROUP.command(name="close")
    async def close_ticket_command(self, context: ApplicationContext):
        author = cast(Member, context.user)
        channel = cast(TextChannel, context.channel)
        guild = cast(Guild, context.guild)
        bot = cast("GormBot", context.client)

        await self._close_ticket(bot, guild, channel, author)

    @TICKET_SLASH_COMMAND_GROUP.command(name="create_voice_channel")
    async def create_voice_channel(self, context: ApplicationContext):
        author = cast(Member, context.user)
        channel = cast(TextChannel, context.channel)
        bot = cast("GormBot", context.client)
        guild = cast(Guild, context.guild)
        category = cast(CategoryChannel, guild.get_channel(TICKET_CATEGORY_ID))

        await context.response.defer(ephemeral=True)

        async with bot.db.ticket_session() as tickets:
            ticket = await tickets.get_ticket(channel.id)

            if ticket is None:
                await context.followup.send(
                    "This channel is not a ticket", ephemeral=True
                )
                return

            if ticket.voice_channel is not None:
                await context.followup.send(
                    f"Voice channel already exists at <#{ticket.voice_channel}>",
                    ephemeral=True,
                )
                return

            voice_channel = await category.create_voice_channel(
                channel.name + "-voice",
                overwrites=channel.overwrites,
                reason=f"user requested {author.id} {author.display_name}",
            )

            ticket.voice_channel = voice_channel.id
            await tickets.upsert_ticket(ticket)

        emb = Embed(
            colour=Colour.blurple(),
            title=f"{author.display_name} created a voice chat {voice_channel.mention}",
        )
        await channel.send(embed=emb)
        await context.followup.send("Voice Channel created", ephemeral=True)

    @TICKET_SLASH_COMMAND_GROUP.command(name="add_member")
    @option("member", Member, description="member to add to the ticket")
    async def add_member_to_ticket(self, context: ApplicationContext, member: Member):
        if member is None:
            await context.respond(content="unknown member", ephemeral=True)
            return

        async with self.bot.db.ticket_session() as tickets:
            exists = await tickets.channel_exists(context.channel_id)
            if not exists:
                await context.respond(
                    content="This isn't a ticket channel", ephemeral=True
                )
                return

        channel = context.channel
        await channel.set_permissions(
            member,
            overwrite=PermissionOverwrite(
                use_slash_commands=True,
                view_channel=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                send_messages=True,
            ),
            reason=f"added by {context.author.display_name}",
        )
        await context.respond(
            content=f"{member.display_name} has been given access to the channel",
            ephemeral=True,
        )
        emb = Embed(
            title=f"{member.mention} has been added to the ticket!", colour=0x00FF00
        )
        await channel.send(embed=emb)

    @TICKET_SLASH_COMMAND_GROUP.command(name="remove_member")
    @option("member", Member, description="member to remove from the ticket")
    async def remove_member_from_ticket(
        self, context: ApplicationContext, member: Member
    ):
        if member is None:
            await context.respond(content="unknown member", ephemeral=True)
            return

        async with self.bot.db.ticket_session() as tickets:
            exists = await tickets.channel_exists(context.channel_id)
            if not exists:
                await context.respond(
                    content="This isn't a ticket channel", ephemeral=True
                )
                return

        channel = context.channel
        await channel.set_permissions(
            member, overwrite=None, reason=f"removed by {context.author.display_name}"
        )
        await context.respond(
            content=f"{member.mention} has been removed from the ticket", ephemeral=True
        )
        emb = Embed(
            title=f"{member.display_name} has been removed from the ticket!",
            colour=0xFF0000,
        )
        await channel.send(embed=emb)

    async def remove_ticket_channel(self, channel: VoiceChannel):
        async with self.bot.db.ticket_session() as tickets:
            is_active = await tickets.is_active_voice_channel(channel.id)
            if not is_active:
                return

        await channel.delete(reason="Voice expired :)")

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: TextChannel):
        if channel.category_id is None or channel.category_id != TICKET_CATEGORY_ID:
            return

        async with self.bot.db.ticket_session() as tickets:
            exists = await tickets.channel_exists(channel.id)
            if not exists:
                return

            deleted = await tickets.delete_ticket(channel.id)
            if deleted:
                await self._audit_log(
                    f"<@{deleted.author_id}>'s {deleted.category.value} ticket was deleted"
                )

    @Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        if before.channel is not None and after.channel is None:
            channel = before.channel
            if channel.members:
                return
            await self.remove_ticket_channel(before.channel)

    @Cog.listener()
    async def on_ready(self):
        async with self.bot.db.ticket_session() as tickets:
            ticket_ids = await tickets.get_all_ticket_ids()

            guild = self.bot.get_guild(MAIN_GUILD_ID)
            tickets_to_delete = []
            for ticket_id in ticket_ids:
                channel = guild.get_channel(ticket_id)
                if channel is None:
                    tickets_to_delete.append(ticket_id)

            for ticket_id in tickets_to_delete:
                deleted = await tickets.delete_ticket(ticket_id)
                if deleted:
                    await self._audit_log(
                        f"<@{deleted.author_id}>'s {deleted.category.value} ticket was deleted"
                    )


class TicketSelector(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.ticket_category_id = TICKET_CATEGORY_ID
        self.builder_team_role_id = BUILDER_TEAM_ROLE_ID
        self.development_team_role_id = DEV_TEAM_ROLE_ID

    @button(
        label="Commission Ticket",
        style=ButtonStyle.primary,
        custom_id="ticketsystem:persistent:builder",
        emoji=PartialEmoji.from_str("🔨"),
    )
    async def builder(self, button: Button, interaction: Interaction):
        await interaction.response.defer()
        author = cast(Member, interaction.user)
        guild = cast(Guild, interaction.guild)
        bot = cast("GormBot", interaction.client)

        comission_tracking = cast("CommissionTracking", bot.get_cog("CommissionTracking"))
        if comission_tracking:
            await comission_tracking.create_commission(interaction.response)
            return

        result, msg = await create_ticket(
            bot, author, guild, TicketCategory.misc
        )
        if result:
            channel_mention = (
                msg.mention
                if isinstance(msg, TextChannel)
                else f"<#{self.ticket_category_id}>"
            )

            await interaction.followup.send(
                ephemeral=True,
                content=f"Your Ticket has been opened at {channel_mention}",
            )
            audit = bot.get_cog("AuditSystem")
            if audit:
                await audit.send_log(
                    content=f"{author.mention} {author.display_name} created a commission ticket at {channel_mention}"
                )
        else:
            await interaction.followup.send(
                ephemeral=True, content=f"Failed to create a ticket!\n{msg}"
            )

    @button(
        label="Support Ticket",
        style=ButtonStyle.danger,
        custom_id="ticketsystem:persistent:support",
        emoji=PartialEmoji.from_str("🎟️"),
        row=1,
    )
    async def support(self, button: Button, interaction: Interaction):
        await interaction.response.defer()
        author = cast(Member, interaction.user)
        guild = cast(Guild, interaction.guild)
        bot = cast("GormBot", interaction.client)

        result, msg = await create_ticket(
            bot, author, guild, TicketCategory.support
        )
        if result:
            channel_mention = (
                msg.mention
                if isinstance(msg, TextChannel)
                else f"<#{self.ticket_category_id}>"
            )

            await interaction.followup.send(
                ephemeral=True,
                content=f"Your Ticket has been opened at {channel_mention}",
            )
            audit = bot.get_cog("AuditSystem")
            if audit:
                await audit.send_log(
                    content=f"{author.mention} {author.display_name} created a support ticket at {channel_mention}"
                )
        else:
            await interaction.followup.send(
                ephemeral=True, content=f"Failed to create a ticket!\n{msg}"
            )

    @button(
        label="Apply",
        style=ButtonStyle.danger,
        custom_id="ticketsystem:persistent:apply",
        emoji=PartialEmoji.from_str("💼"),
        row=1,
    )
    async def apply(self, button: Button, interaction: Interaction):
        await interaction.response.defer()
        author = cast(Member, interaction.user)
        guild = cast(Guild, interaction.guild)
        bot = cast("GormBot", interaction.client)

        result, msg = await create_ticket(
            bot, author, guild, TicketCategory.application
        )
        if result:
            channel_mention = (
                msg.mention
                if isinstance(msg, TextChannel)
                else f"<#{self.ticket_category_id}>"
            )

            await interaction.followup.send(
                ephemeral=True,
                content=f"Your Ticket has been opened at {channel_mention}",
            )
            audit = bot.get_cog("AuditSystem")
            if audit:
                await audit.send_log(
                    content=f"{author.mention} {author.display_name} created a application ticket at {channel_mention}"
                )
        else:
            await interaction.followup.send(
                ephemeral=True, content=f"Failed to create a ticket!\n{msg}"
            )


class CloseTicket(View):

    def __init__(self):
        super().__init__(timeout=None)

    @button(
        label="Close",
        style=ButtonStyle.red,
        custom_id="ticketsystem:persistent:close_ticket",
    )
    async def closed_ticket(self, button: Button, interaction: Interaction):
        author = cast(Member, interaction.user)
        channel = cast(TextChannel, interaction.channel)
        guild = cast(Guild, interaction.guild)
        bot = cast("GormBot", interaction.client)

        ticket_system = bot.get_cog("TicketSystem")
        if ticket_system:
            await ticket_system._close_ticket(bot, guild, channel, author)

    @button(
        label="Voice",
        style=ButtonStyle.blurple,
        custom_id="ticketsystem:persistent:create_voice",
    )
    async def create_voice(self, button: Button, interaction: Interaction):
        author = cast(Member, interaction.user)
        channel = cast(TextChannel, interaction.channel)
        bot = cast("GormBot", interaction.client)
        guild = cast(Guild, interaction.guild)
        category = cast(CategoryChannel, guild.get_channel(TICKET_CATEGORY_ID))

        await interaction.response.defer(ephemeral=True)

        async with bot.db.ticket_session() as tickets:
            ticket = await tickets.get_ticket(channel.id)

            if ticket is None:
                await interaction.followup.send("This channel is not a ticket")
                return

            if ticket.voice_channel is not None:
                await interaction.followup.send(
                    f"Voice channel already exists at <#{ticket.voice_channel}>"
                )
                return

            voice_channel = await category.create_voice_channel(
                channel.name + "-voice",
                overwrites=channel.overwrites,
                reason=f"user requested {author.id} {author.display_name}",
            )

            ticket.voice_channel = voice_channel.id
            await tickets.upsert_ticket(ticket)

        emb = Embed(
            colour=Colour.blurple(),
            title=f"{author.display_name} created a voice chat {voice_channel.mention}",
        )
        await channel.send(embed=emb)
        await interaction.followup.send("Voice Channel created")


def setup(bot: Bot):
    bot.add_view(TicketSelector())
    bot.add_view(CloseTicket())
    bot.add_cog(TicketSystem(bot))
