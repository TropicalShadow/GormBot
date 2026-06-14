import asyncio
from discord import ApplicationContext, ButtonStyle, CategoryChannel, Colour, Embed, Guild, Interaction, Member, Option, PartialEmoji, PermissionOverwrite, Permissions, SlashCommandGroup, TextChannel, option, slash_command
from discord.ext.commands import Cog, Bot

from typing import TYPE_CHECKING, Optional, Tuple, cast

from discord.ui import Button, View, button
from discord.utils import format_dt, utcnow

from db import TICKET_CATEGORY
from db.TicketConnection import IndividualTicket

if TYPE_CHECKING:
    from utils import GormBot

TICKET_CATEGORY_ID = 1515417410369487010
GUILD_ID = 1515413540972789790


class TicketSystem(Cog):

    def __init__(self, bot: 'GormBot'):
        self.bot: GormBot = bot

    async def _audit_log(self, content: str):
        audit = self.bot.get_cog("AuditSystem")
        if audit:
            await audit.send_log(content=content)

    TICKET_SLASH_COMMAND_GROUP = SlashCommandGroup(name="ticket", description="management of the ticket system")

    @TICKET_SLASH_COMMAND_GROUP.command(name="send_ticket_menu", default_member_permissions=Permissions(administrator=True))
    async def send_ticket_menu(self, context: ApplicationContext):
        channel = context.channel

        emb = Embed(title="Ticket Creation")

        await channel.send(embed=emb, view=TicketSelector())

        await context.respond(content="Sent Menu", ephemeral=True)

    @TICKET_SLASH_COMMAND_GROUP.command(name="debug_ticket", default_member_permissions=Permissions(administrator=True))
    async def send_debug_ticket(self, context: ApplicationContext):
        with self.bot.db.ticket_system_table as ticket:
            data = ticket["tickets"]
            if data is None:
                await context.respond(content="No Data Found")
            else:
                await context.respond(content=str(data)[:2000])

    @TICKET_SLASH_COMMAND_GROUP.command(name="add_member")
    @option("member", Member, description="member to add to the ticket")
    async def add_member_to_ticket(self, context: ApplicationContext, member: Member):
        if member is None:
            await context.respond(content="unknown member", ephemeral=True)
            return

        channel_id = context.channel_id
        exists = self.bot.db.ticket_system_table.channel_exists(channel_id)
        if not exists:
            await context.respond(content="This isn't a ticket channel", ephemeral=True)
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
            reason=f"added by {context.author.display_name}"
        )
        await context.respond(content=f"{member.display_name} has been given access to the channel", ephemeral=True)
        emb = Embed(
            title=f"{member.mention} has been added to the ticket!",
            colour=0x00FF00
        )
        await channel.send(embed=emb)

    @TICKET_SLASH_COMMAND_GROUP.command(name="remove_member")
    @option("member", Member, description="member to remove from the ticket")
    async def remove_member_from_ticket(self, context: ApplicationContext, member: Member):
        if member is None:
            await context.respond(content="unknown member", ephemeral=True)
            return

        channel_id = context.channel_id
        exists = self.bot.db.ticket_system_table.channel_exists(channel_id)
        if not exists:
            await context.respond(content="This isn't a ticket channel", ephemeral=True)
            return

        channel = context.channel
        await channel.set_permissions(member, overwrite=None, reason=f"removed by {context.author.display_name}")
        await context.respond(content=f"{member.mention} has been removed from the ticket", ephemeral=True)
        emb = Embed(
            title=f"{member.display_name} has been removed from the ticket!",
            colour=0xFF0000
        )
        await channel.send(embed=emb)

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: TextChannel):
        if channel.category_id is None or channel.category_id != TICKET_CATEGORY_ID:
            return

        channel_id = channel.id
        exists = self.bot.db.ticket_system_table.channel_exists(channel_id)
        if not exists:
            return

        deleted = self.bot.db.ticket_system_table.delete_ticket(channel_id)
        if deleted:
            await self._audit_log(f"<@{deleted.author_id}>'s {deleted.category} ticket was deleted")

    @Cog.listener()
    async def on_ready(self):
        ticket_ids = self.bot.db.ticket_system_table.get_all_ticket_ids()

        guild = self.bot.get_guild(GUILD_ID)
        tickets_to_delete = []
        for ticket in ticket_ids:
            channel = guild.get_channel(int(ticket))
            if channel is None:
                tickets_to_delete.append(ticket)

        for ticket in tickets_to_delete:
            deleted = self.bot.db.ticket_system_table.delete_ticket(ticket)
            if deleted:
                await self._audit_log(f"<@{deleted.author_id}>'s {deleted.category} ticket was deleted")


class TicketSelector(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.ticket_category_id = TICKET_CATEGORY_ID
        self.builder_team_role_id = 1515419068952481903
        self.development_team_role_id = 1515490644565430364

    @button(
        label="Builder Ticket",
        style=ButtonStyle.primary,
        custom_id="ticketsystem:persistent:builder",
        emoji=PartialEmoji.from_str("🔨"),
    )
    async def builder(self, button: Button, interaction: Interaction):
        await interaction.response.defer()
        author = cast(Member, interaction.user)
        guild = cast(Guild, interaction.guild)
        bot = cast('GormBot', interaction.client)

        result, msg = await self.create_ticket(bot, author, guild, "builder")
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
                await audit.send_log(content=f"{author.mention} {author.display_name} created a builder ticket at {channel_mention}")
        else:
            await interaction.followup.send(
                ephemeral=True, content=f"Failed to create a ticket!\n{msg}"
            )

    @button(
        label="Developer Ticket",
        style=ButtonStyle.primary,
        custom_id="ticketsystem:persistent:developer",
        emoji=PartialEmoji.from_str("🖥️"),
    )
    async def developer(self, button: Button, interaction: Interaction):
        await interaction.response.defer()
        author = cast(Member, interaction.user)
        guild = cast(Guild, interaction.guild)
        bot = cast('GormBot', interaction.client)

        result, msg = await self.create_ticket(bot, author, guild, "developer")
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
                await audit.send_log(content=f"{author.mention} {author.display_name} created a developer ticket at {channel_mention}")
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
        bot = cast('GormBot', interaction.client)

        result, msg = await self.create_ticket(
            bot, author, guild, "support"
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
                await audit.send_log(content=f"{author.mention} {author.display_name} created a support ticket at {channel_mention}")
        else:
            await interaction.followup.send(
                ephemeral=True, content=f"Failed to create a ticket!\n{msg}"
            )

    async def create_ticket(
        self, bot: 'GormBot', user: Member, guild: Guild, category: TICKET_CATEGORY
    ) -> Tuple[Optional[IndividualTicket], str | TextChannel]:
        """Create A ticket channel for the user
        This will create a ticket channel for the user and return the channel object

        Args:
            bot (GormBot): bot
            user (Member): the user who created the ticket
            guild (Guild): the guild where the ticket was created
            category (str): the type of ticket to create

        Returns:
            Tuple[Optional[IndividualTicket], str | TextChannel]: _description_
        """

        ticket_category = cast(
            CategoryChannel, guild.get_channel(self.ticket_category_id)
        )
        if ticket_category is None:
            return (
                None,
                f"Ticket category Id not found (ticket.json), please contact an admin, {self.ticket_category_id}",
            )

        overwrites = ticket_category.overwrites
        overwrites[guild.default_role] = PermissionOverwrite(view_channel=False)
        overwrites[user] = PermissionOverwrite(
            use_slash_commands=True,
            view_channel=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            send_messages=True,
        )

        channel = await ticket_category.create_text_channel(
            f"{category.title()}-{user.display_name}",
            topic=f"{category.title()} ticket for {user}",
            reason="Ticket System",
            overwrites=overwrites,
        )
        ticket = IndividualTicket(
            channel_id=channel.id,
            category=category,
            author_id=user.id,
            author_name=user.display_name
        )
        err = bot.db.ticket_system_table.create_ticket(ticket)
        if err is not None:
            bot.logger.error("failed to create ticket")
            asyncio.create_task(channel.delete(reason="Database insert failed"))
            return (None, "failed to create ticket")

        emb = Embed(
            title=f"{category.title()} ticket", colour=Colour.blue(), timestamp=utcnow()
        )
        #  emb.add_field(name="Ticket ID", value=f"{ticket_id:04}", inline=True)
        emb.add_field(name="Opened By", value=f"{user.mention}", inline=True)
        emb.add_field(name="Category", value=f"{category.title()}", inline=True)
        emb.add_field(name="Status", value="Open", inline=True)
        emb.add_field(name="Open Time", value=f"{format_dt(utcnow())}", inline=True)

        emb.set_footer(text=f"ticket for {user}", icon_url=user.display_avatar)

        content = user.mention
        if category == "builder":
            content += f" <@&{self.builder_team_role_id}>"
        elif category == "developer":
            content += f" <@&{self.development_team_role_id}>"

        first_message = await channel.send(
            content=content,
            embed=emb,
            view=CloseTicket()
        )

        ticket.first_message = first_message.id
        bot.db.ticket_system_table.upsert_ticket(ticket)

        return ticket, channel


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
        bot = cast('GormBot', interaction.client)

        ticket = bot.db.ticket_system_table.get_ticket(channel.id)
        author_name = ticket.author_name if ticket else "unknown"
        author_id = ticket.author_id if ticket else "unknown"
        category = ticket.category if ticket else "unknown"

        await channel.edit(name=f"closed-{author_name}")
        await asyncio.sleep(1)
        bot.db.ticket_system_table.delete_ticket(channel.id)
        audit = bot.get_cog("AuditSystem")
        if audit:
            await audit.send_log(content=f"{author.id} {author.display_name} Closed {author_id} {author_name}'s {category} ticket")
        await channel.delete(reason=f"Ticket Closed by {author.id} {author.display_name}")


def setup(bot: Bot):
    bot.add_view(TicketSelector())
    bot.add_view(CloseTicket())
    bot.add_cog(TicketSystem(bot))
