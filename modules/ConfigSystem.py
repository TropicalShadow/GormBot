from typing import cast, TYPE_CHECKING
import discord
from discord.ext.commands import Cog, Bot
from discord import (
    ApplicationContext,
    Permissions,
    SlashCommandGroup,
    Embed,
    Colour,
    option,
)

if TYPE_CHECKING:
    from utils import GormBot


class ConfigSystem(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    CONFIG_GROUP = SlashCommandGroup(
        name="config",
        description="Bot configuration",
        default_member_permissions=Permissions(administrator=True),
    )

    PAYMENTS_GROUP = CONFIG_GROUP.create_subgroup(
        name="payments",
        description="Payment provider configuration",
    )

    @PAYMENTS_GROUP.command(name="status")
    async def payments_status(self, ctx: ApplicationContext):
        bot = cast("GormBot", ctx.bot)
        async with bot.db.config_session() as config:
            stripe_enabled = await config.get("stripe_enabled") or "true"
            crypto_enabled = await config.get("crypto_enabled") or "true"

        embed = Embed(title="Payment Configuration", colour=Colour.blue())
        embed.add_field(
            name="Stripe",
            value="Enabled" if stripe_enabled == "true" else "Disabled",
            inline=True
        )
        embed.add_field(
            name="Crypto",
            value="Enabled" if crypto_enabled == "true" else "Disabled",
            inline=True
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @PAYMENTS_GROUP.command(name="stripe")
    @option("action", str, choices=["enable", "disable"])
    async def stripe_toggle(self, ctx: ApplicationContext, action: str):
        bot = cast("GormBot", ctx.bot)
        value = "true" if action == "enable" else "false"
        async with bot.db.config_session() as config:
            await config.set("stripe_enabled", value)
        await ctx.respond(f"Stripe payments {action}d.", ephemeral=True)

    @PAYMENTS_GROUP.command(name="crypto")
    @option("action", str, choices=["enable", "disable"])
    async def crypto_toggle(self, ctx: ApplicationContext, action: str):
        bot = cast("GormBot", ctx.bot)
        value = "true" if action == "enable" else "false"
        async with bot.db.config_session() as config:
            await config.set("crypto_enabled", value)
        await ctx.respond(f"Crypto payments {action}d.", ephemeral=True)


def setup(bot: Bot):
    bot.add_cog(ConfigSystem(bot))
