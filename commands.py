from hashlib import sha512
import hmac
import time
import aiohttp
from fateslist.classes import UserState, Status
from fateslist import UserClient, APIResponse
from fateslist.utils import etrace 
from fateslist.system import SystemClient
from discord import Color, Embed, User
from discord.ext import commands, tasks

import json

class Users(commands.Cog):
    """Commands made specifically for users to use"""

    def __init__(self, bot):
        self.bot = bot
        self.msg = None
        self.statloop.start()

    @commands.command(
        name="catid",
        description="Get the category ID of a channel",
    )
    async def catid(self, inter):
        return await self._catid(inter)
    
    @commands.slash_command(
        name="vote",
        description="Vote for a bot",
    )
    async def _vote_slash(self, inter, bot: User):
        await self._vote_(inter, bot)

    @commands.command(
        name="vote",
        description="Vote for a bot"
    )
    async def _vote_normal(self, ctx, bot: User):
        await self._vote_(ctx, bot)
    
    async def _vote_(self, inter, bot: User):
        if not bot.bot:
            return await inter.send(
                "You can only vote for bots at this time!"
            )
        
        # Get vote token
        ts = int(time.time())

        hash = hmac.new(
            self.bot.config["vote_token_access_key"].encode(),
            f"{inter.author.id}/{bot.id}/{ts}/Shadowsight",
            sha512
        )

        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                f"https://api.fateslist.xyz/api/dragon/users/{inter.author.id}/bots/{bot.id}/ts/{ts}/_vote-token",
                headers={"Authorization": "Vote " + hash.hexdigest()}
            ) as resp:
                if resp.status != 200:
                    return await inter.send(
                        "Failed to get vote token!"
                    )
                token = await resp.json()
        
            async with sess.patch(
                f"https://api.fateslist.xyz/api/dragon/bots/{bot.id}/votes",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": token["ctx"],
                    "Mistystar": "1"
                },
                json={"user_id": str(inter.author.id), "test": False}
            ) as res:
                if res.status >= 400:
                    json = await res.json()
                    return await inter.send(f'{json["reason"]}\n**Status Code:** {res.status}')
                return await inter.send("Successfully voted for this bot!")

    @commands.command(name="chanid",
                            description="Get channel id")
    async def chanid(self, inter):
        return await inter.send(str(inter.channel.id))

    @commands.command(name="flstats",
                            description="Show Fates List Stats")
    async def stats(self, inter):
        sc = SystemClient()
        stats = await sc.blstats()
        return await inter.send(embed=stats.embed())

    @commands.slash_command(
        name="flprofile",
        description="Get your own or another users profile",
    )
    async def flprofile(self, inter, user: User = None):
        return await self._profile(inter, user)

    @tasks.loop(seconds=60)
    async def statloop(self):
        try:
            sc = SystemClient()
            stats = await sc.blstats()
            if not self.msg:
                channel = self.bot.get_channel(int(self.bot.config["stats_channel"]))
                await channel.purge(
                    limit=100, check=lambda m: m.author.id != m.guild.owner_id
                )  # Delete old messages there
                self.msg = await channel.send(embed=stats.embed())
                await self.msg.pin(reason="Stat Message Pin")
                await channel.purge(
                    limit=1)  # Remove Fates List Manager has pinned...
            else:
                await self.msg.edit(embed=stats.embed())
        except Exception as exc:
            print(etrace(exc), flush=True)

    def cog_unload(self):
        self.statloop.cancel()

    @staticmethod
    async def _catid(inter):
        if inter.channel.category:
            return await inter.send(str(inter.channel.category.id))
        return await inter.send("No category attached to this channel")

    @staticmethod
    async def _profile(inter, user=None):
        """Gets a users profile (Not yet done)"""
        target = user if user else inter.author
        uc = UserClient(target.id)
        _profile = await uc.get_user()
        if isinstance(_profile, APIResponse):
            return
        embed = Embed(title=f"{target}'s Profile",
                      description="Here is your profile")

        _profile = _profile.dict()

        # Base fields
        embed.add_field(name="User ID", value=_profile["user"]["id"])
        embed.add_field(name="Username", value=_profile["user"]["username"])
        embed.add_field(name="Discriminator/Tag",
                        value=_profile["user"]["disc"])
        embed.add_field(name="Avatar", value=_profile["user"]["avatar"])
        embed.add_field(name="Description",
                        value=_profile["profile"]["description"])
        embed.add_field(
            name="Status",
            value=f"{_profile['user']['status']} ({Status(_profile['user']['status']).__doc__})",
        )
        embed.add_field(
            name="State",
            value=f"{_profile['profile']['state']} ({UserState(_profile['profile']['state']).__doc__})",
        )
        embed.add_field(
            name="User CSS",
            value=_profile["profile"]["user_css"]
            if _profile["profile"]["user_css"] else "No custom user CSS set",
        )

        await inter.send(embed=embed)