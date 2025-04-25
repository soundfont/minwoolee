import discord
from discord.ext import commands

class EmbedContext(commands.Context):
    async def send(self, content=None, **kwargs):
        # if there's content passed, wrap it in an embed
        if content:
            embed = discord.Embed(
                title="",
                description=str(content),
                color=discord.Color.blurple()
            )
            kwargs["embed"] = embed
            kwargs.pop("content", None)
        return await super().send(**kwargs)
