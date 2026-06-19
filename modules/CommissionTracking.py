from typing import cast, TYPE_CHECKING
import discord
from discord.ext.commands import Cog, Bot
from discord import Interaction, InteractionResponse, Member, SlashCommandGroup, ApplicationContext, TextChannel
from discord.ui import Modal, InputText

from db import IndividualTicket, TicketCategory
from db.DatabaseSchema import Commission
from .TicketSystem import create_ticket

if TYPE_CHECKING:
    from utils import GormBot
    from .AuditSystem import AuditSystem


class CommissionTracking(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    COMMISSION_SLASH_COMMAND_GROUP = SlashCommandGroup(name="commission", description="management of the commission system")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="create")
    async def create_commission_command(self, ctx: ApplicationContext):
        await self.create_commission(ctx.response)

    async def create_commission(self, response: InteractionResponse):
        await response.send_modal(CreateCommissionModal())


class CreateCommissionModal(Modal):
    def __init__(self):
        super().__init__(title="Create Commission")

        self.add_item(
            InputText(
                label="Project Name",
                placeholder="Survival Spawn",
                required=True,
                max_length=100,
            )
        )

        self.add_item(
            InputText(
                label="Budget",
                placeholder="$300",
                required=True,
                max_length=25,
            )
        )

        self.add_item(
            InputText(
                label="Brief Description",
                placeholder="A big blue house",
                required=True,
            )
        )

        self.add_item(
            InputText(
                label="Description",
                placeholder="Detailed description",
                style=discord.InputTextStyle.long,
                required=True,
                max_length=2000,
            )
        )

    async def callback(self, interaction: Interaction):
        bot = cast("GormBot", interaction.client)
        member = cast("Member", interaction.user)
        channel = cast("TextChannel", interaction.channel)

        project_name = self.children[0].value
        budget = self.children[1].value
        brief = self.children[2].value
        description = self.children[3].value

        embed = discord.Embed(
            title=f"📁 {project_name}",
            description=description,
        )

        embed.add_field(name="Brief", value=brief, inline=True)
        embed.add_field(name="Budget", value=budget, inline=True)
        embed.add_field(name="Client", value=interaction.user.mention, inline=False)

        await interaction.response.defer(ephemeral=True)

        is_ticket = False
        async with bot.db.ticket_session() as session:
            if channel:
                is_ticket = await session.channel_exists(channel.id)

        ticket: IndividualTicket | None = None
        text_channel: TextChannel | None = None
        if not is_ticket:
            ticket, res = await create_ticket(bot, member, member.guild, TicketCategory.application)
            if not ticket:
                await interaction.followup.send("Failed to create ticket :(")
                return
            if isinstance(res, TextChannel):
                text_channel = res
        else:
            async with bot.db.ticket_session() as session:
                ticket = await session.get_ticket(channel.id)
            if ticket:
                text_channel = bot.get_channel(ticket.channel_id)

        comm = Commission(
            project_name=project_name,
            budget=budget,
            brief=brief,
            description=description,
            ticket_channel_id=ticket.channel_id if ticket else None
        )

        async with bot.db.commission_session() as session:
            await session.create_commission(comm)

        if text_channel:
            await text_channel.send(embed=embed)

        audit_system = cast("AuditSystem", bot.get_cog("AuditSystem"))
        if audit_system:
            await audit_system.send_log(embed)


def setup(bot: Bot):
    bot.add_cog(CommissionTracking(bot))
