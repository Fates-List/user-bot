from hashlib import sha512
import hmac
import time
import aiohttp
from fateslist.classes import UserState, BotState, Status, LongDescType
from fateslist import BotClient, UserClient, APIResponse
from fateslist.utils import etrace 
from fateslist.system import SystemClient
from discord import Color, Embed, User, ButtonStyle, Client
from discord.ui import Button, View
from discord.ext import commands, tasks

class Users(commands.Cog):
    """Commands made specifically for users to use"""

    def __init__(self, bot):
        self.bot: Client = bot
        self.msg = None
        self.statloop.start()
        self.vote_reminder.start()
    
    # Vote reminder handler
    @tasks.loop(minutes=1)
    async def vote_reminder(self):
        sc = SystemClient()
        vote_reminders = await sc.get_vote_reminders()
        for user in vote_reminders["reminders"]:
            channel_id = user["vote_reminder_channel"]
            if channel_id and channel_id.isdigit():
                channel = self.bot.get_channel(int(channel_id))
            else:
                # TODO: Make this a config option
                channel = self.bot.get_channel(939123825885474898)
            if not channel:
                continue
            
            has_one_pending_bot = False

            bot_str = ""
            
            for i, bot in enumerate(user["can_vote"]):
                check = await self.bot.redis.get(f"vote_reminder_ack:{user['user_id']}-{bot}")
                if not check:
                    await self.bot.redis.set(f"vote_reminder_ack:{user['user_id']}-{bot}", "0", ex=60*60*6)
                    has_one_pending_bot = True
                bot_str += f", <@{bot}> ({bot})" if i < len(user["can_vote"]) - 1 else f" and <@{bot}> ({bot})"
            
            if has_one_pending_bot:
                await channel.send(f"Hey <@{user['user_id']}>, you can now vote for {bot_str} or did you forget?\n\n*This will keep repeating every 6 hours until a vote*")

    @commands.command(
        name="catid",
    )
    async def catid(self, inter):
        """Get the category ID of a channel"""
        return await self._catid(inter)
    
    @commands.slash_command(
        name="vote",
        description="Vote for a bot",
    )
    async def _vote_slash(self, inter, bot: User):
        await self._vote_(inter, bot)

    @commands.command(
        name="vote",
    )
    async def _vote_normal(self, ctx, bot: User):
        """Vote for a bot"""
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
            f"{inter.author.id}/{bot.id}/{ts}/Shadowsight".encode(),
            sha512
        )

        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                f"https://api.fateslist.xyz/api/dragon/users/{inter.author.id}/bots/{bot.id}/ts/{ts}/_vote-token",
                headers={"Authorization": hash.hexdigest()}
            ) as resp:
                if resp.status == 408:
                    return await inter.send(
                        "Fates List is down for maintenance"
                    )
                if resp.status != 200:
                    return await inter.send(
                        f"Failed to get vote token with status {resp.status}!"
                    )
                token = await resp.json()
                print(token)
        
            async with sess.patch(
                f"https://api.fateslist.xyz/api/dragon/bots/{bot.id}/votes",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Vote " + token["ctx"],
                    "Mistystar": "1"
                },
                json={"user_id": str(inter.author.id), "test": False}
            ) as res:
                if res.status >= 400:
                    json = await res.json()
                    return await inter.send(f'{json["reason"]}\n**Status Code:** {res.status}')
            
            await inter.send(
                "Successfully voted for this bot!"
            )

            class VoteReminderView(View):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.add_item(Button(url=f"https://fateslist.xyz/bot/{bot.id}/reminders", label="Remind Me!"))

            await inter.send("**Want vote reminders?**", view=VoteReminderView())



    @commands.command(name="chanid")
    async def chanid(self, inter):
        """Get the channel ID of the current channel"""
        return await inter.send(str(inter.channel.id))

    @commands.command(name="stats")
    async def stats(self, inter):
        """Show Fates List statistics"""
        sc = SystemClient()
        stats = await sc.blstats()
        return await inter.send(embed=stats.embed())

    @commands.command(name="profile")
    async def _flprofile_normal(self, inter, user: User = None):
        """Show a user's Fates List profile"""
        if user is None:
            user = inter.author
        return await self._profile(inter, user)

    @commands.slash_command(
        name="profile",
        description="Get your own or another users profile",
    )
    async def flprofile(self, inter, user: User = None):
        if user is None:
            user = inter.author
        return await self._profile(inter, user)
    
    @commands.command(name="bot")
    async def _bot_normal(self, inter, user: User):
        """Get a user's bot profile"""
        if not user.bot:
            return await inter.send("You can only get a bot like this!")
        return await self._bot(inter, user)

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
        self.vote_reminder.cancel()

    @staticmethod
    async def _catid(inter):
        if inter.channel.category:
            return await inter.send(str(inter.channel.category.id))
        return await inter.send("No category attached to this channel")

    @staticmethod
    async def _bot(inter, user: User):
        """Returns a bot"""
        bc = BotClient(user.id)
        _bot = await bc.get_bot(compact=False)
        if isinstance(_bot, APIResponse):
            return await inter.send("Failed to get bot!")
        embed = Embed(
            title=f"{user}'s Info", 
            color=Color.blue(),
            description="Here is your profile")
        
        # Base fields
        embed.add_field(name="User ID", value=_bot.user["id"])
        embed.add_field(name="Username", value=_bot.user["username"])
        embed.add_field(name="Discriminator/Tag",
                        value=_bot.user["disc"])
        embed.add_field(name="Avatar", value=_bot.user["avatar"])
        embed.add_field(name="Description",
                        value=_bot.description)
        embed.add_field(name="Long Description",
                        value=_bot.long_description[:128]+"...")
        embed.add_field(name="Long Description Type",
                        value=f"{_bot.long_description_type} ({LongDescType(_bot.long_description_type).__doc__})")
        embed.add_field(name="State",
                        value=f"{_bot.state} ({BotState(_bot.state).__doc__})")
        embed.add_field(name="Tags",
                        value=", ".join(_bot.tags))


        class BotButtonView(View):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.add_item(Button(url=f"https://fateslist.xyz/bot/{_bot.user['id']}", label="View"))
                self.add_item(Button(url=f"https://fateslist.xyz/bot/{_bot.user['id']}/vote", label="Vote"))    
                self.add_item(Button(url=f"https://fateslist.xyz/bot/{_bot.user['id']}/settings", label="Settings"))    


        return await inter.send(
            embed=embed, 
            view=BotButtonView())

    @staticmethod
    async def _profile(inter, target: User):
        """Gets a users profile"""
        uc = UserClient(target.id)
        _profile = await uc.get_user()
        if isinstance(_profile, APIResponse):
            return await inter.send("Failed to get profile!")
        embed = Embed(title=f"{target}'s Profile",
                      description="Here is your profile")

        # Base fields
        embed.add_field(name="User ID", value=_profile.user["id"])
        embed.add_field(name="Username", value=_profile.user["username"])
        embed.add_field(name="Discriminator/Tag",
                        value=_profile.user["disc"])
        embed.add_field(name="Avatar", value=_profile.user["avatar"])
        embed.add_field(name="Description",
                        value=_profile.profile["description"])
        embed.add_field(
            name="Status",
            value=f"{_profile.user['status']} ({Status(_profile.user['status']).__doc__})",
        )
        embed.add_field(
            name="State",
            value=f"{_profile.profile['state']} ({UserState(_profile.profile['state']).__doc__})",
        )
        embed.add_field(
            name="User CSS",
            value=_profile.profile["user_css"]
            if _profile.profile["user_css"] else "No custom user CSS set",
        )

        await inter.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(
                f"You are missing a required argument: {error.param}!"
            )
        if isinstance(error, commands.BadArgument):
            return await ctx.send(
                f"You have provided an invalid argument: {error}!"
            )
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(
                f"You are on cooldown!"
            )
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send(
                f"You are missing permissions!"
            )
        if isinstance(error, commands.CommandInvokeError):
            return await ctx.send(
                f"An error occured! {error}"
            )
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(
                f"You are on cooldown!"
            )
        if isinstance(error, commands.CommandError):
            return await ctx.send(
                f"An error occured!"
            )
