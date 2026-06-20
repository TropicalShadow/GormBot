from typing import cast, TYPE_CHECKING
import discord
from discord.ext.commands import Cog, Bot
from discord import Embed, Colour, Interaction, InteractionResponse, Member, SlashCommandGroup, ApplicationContext, TextChannel
from discord import option
from discord.ui import Modal, InputText

from db import IndividualTicket, TicketCategory
from db.DatabaseSchema import Commission, CommissionStatus
from .TicketSystem import create_ticket

if TYPE_CHECKING:
    from utils import GormBot
    from .AuditSystem import AuditSystem


class CommissionTracking(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    COMMISSION_SLASH_COMMAND_GROUP = SlashCommandGroup(name="commission", description="management of the commission system")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="create", description="Create a new commission with project details")
    async def create_commission_command(self, ctx: ApplicationContext):
        await self.create_commission(ctx.response)

    async def create_commission(self, response: InteractionResponse):
        await response.send_modal(CreateCommissionModal())

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="start", description="Start work on a commission (sets status to in progress)")
    async def start_commission(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            if comm.status != CommissionStatus.open:
                await ctx.respond(f"Commission is already {comm.status.value}.", ephemeral=True)
                return
            comm.status = CommissionStatus.in_progress
            await session.upsert_comm(comm)

        await ctx.respond("Commission started! Status: **In Progress**")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="cancel", description="Cancel the commission in this ticket")
    async def cancel_commission(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            comm.status = CommissionStatus.cancelled
            await session.upsert_comm(comm)

        await ctx.respond("Commission cancelled.")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="complete", description="Mark the commission as completed (requires full payment)")
    async def complete_commission(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return

        async with bot.db.billing_session() as billing:
            bill = await billing.get_bill_by_commission(comm.id)
            if bill and (not bill.deposit_paid or not bill.final_paid):
                await ctx.respond("Cannot complete: bill not fully paid.", ephemeral=True)
                return

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            comm.status = CommissionStatus.completed
            await session.upsert_comm(comm)

        await ctx.respond("Commission completed!")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="assign", description="Assign a team member to this commission")
    @option("member", Member, description="Member to assign")
    async def assign_member(self, ctx: ApplicationContext, member: Member):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            if await session.is_assigned(comm.id, member.id):
                await ctx.respond(f"{member.display_name} is already assigned.", ephemeral=True)
                return
            await session.assign_member(comm.id, member.id, member.display_name)

        await ctx.respond(f"{member.display_name} assigned to commission.")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="unassign", description="Remove a team member from this commission")
    @option("member", Member, description="Member to unassign")
    async def unassign_member(self, ctx: ApplicationContext, member: Member):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            removed = await session.unassign_member(comm.id, member.id)
            if not removed:
                await ctx.respond(f"{member.display_name} is not assigned.", ephemeral=True)
                return

        await ctx.respond(f"{member.display_name} unassigned from commission.")

    @COMMISSION_SLASH_COMMAND_GROUP.command(name="info", description="View commission details, assigned members, and billing status")
    async def commission_info(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        channel_id = ctx.channel_id

        async with bot.db.commission_session() as session:
            comm = await session.get_comm_by_channel(channel_id)
            if not comm:
                await ctx.respond("No commission found for this ticket.", ephemeral=True)
                return
            assignments = await session.get_assignments(comm.id)

        async with bot.db.billing_session() as billing:
            bill = await billing.get_bill_by_commission(comm.id)

        embed = Embed(title=f"Commission: {comm.project_name}", colour=Colour.blue())
        embed.add_field(name="Status", value=comm.status.value.replace("_", " ").title(), inline=True)
        embed.add_field(name="Budget", value=comm.budget, inline=True)
        embed.add_field(name="Brief", value=comm.brief, inline=False)

        if assignments:
            members = ", ".join(f"<@{a.member_id}>" for a in assignments)
            embed.add_field(name="Assigned", value=members, inline=False)
        else:
            embed.add_field(name="Assigned", value="No one", inline=False)

        if bill:
            deposit_amt = bill.total_amount * (bill.deposit_percent / 100)
            final_amt = bill.total_amount - deposit_amt
            bill_status = []
            bill_status.append(f"Deposit: ${deposit_amt:.2f} {'(Paid)' if bill.deposit_paid else '(Unpaid)'}")
            bill_status.append(f"Final: ${final_amt:.2f} {'(Paid)' if bill.final_paid else '(Unpaid)'}")
            embed.add_field(name="Bill", value="\n".join(bill_status), inline=False)
        else:
            embed.add_field(name="Bill", value="No bill created", inline=False)

        await ctx.respond(embed=embed)


class CreateCommissionModal(Modal):
    def __init__(self):
        super().__init__(title="Create Commission")

        self.add_item(
            InputText(
                label="Project Name",
                placeholder="PVP, Survivel, Big Castle",
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
            await audit_system.send_log(embed=embed)


def setup(bot: Bot):
    bot.add_cog(CommissionTracking(bot))
