import asyncio
import logging
import os

import aioredis

import discord
import setproctitle
from discord.ext import commands
from loguru import logger

from commands import Users

import json

logging.basicConfig(level=logging.INFO)

from fateslist.utils import etrace

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
    fates.redis = await aioredis.from_url("redis://localhost:1001", db=2)
    fates.add_cog(Users(fates))
    logger.info("Init done")

@fates.event
async def on_command_error(ctx, err):
    print(etrace(err))

fates.run(fates.config["token"])