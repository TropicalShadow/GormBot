
from typing import Optional
from discord.ext.commands import Cog, Bot
from discord import Embed

AUDIT_CHANNEL_ID = 1515785727131254855


class AuditSystem(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_log(self, content: Optional[str] = None, embed: Optional[Embed] = None):
        if (content is None and embed is None):
            return

        audit_channel = self.bot.get_channel(AUDIT_CHANNEL_ID)
        if audit_channel is None:
            return
        await audit_channel.send(content, embed=embed)


def setup(bot: Bot):
    bot.add_cog(AuditSystem(bot))
