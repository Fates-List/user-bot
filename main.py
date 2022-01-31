import asyncio
import logging
import os

import discord
import setproctitle
from discord.ext import commands
from loguru import logger

from commands import Users

setproctitle.setproctitle("manager-fl")

import json

logging.basicConfig(level=logging.INFO)

class FatesManagerBot(commands.Bot):
    async def on_command_error(self, *args, **kwargs):
        pass

    @staticmethod
    async def is_owner(user: discord.User):
        """Owner check patch"""
        if user.id == 563808552288780322:
            return True
        return False


fates = FatesManagerBot(
    command_prefix="+",
    intents=discord.Intents(guilds=True,
                            members=True,
                            dm_messages=True,
                            messages=True),
)

with open("cfg.json") as cfg:
    fates.config = json.load(cfg)

fates.load_extension("jishaku")

@fates.event
async def on_ready():
    fates.add_cog(Users(fates))
    logger.info("Init done")

fates.run(fates.config["token"])
