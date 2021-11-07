import asyncio
import functools
import itertools
import math
import os.path
import random
import discord
import yt_dlp
from async_timeout import timeout
from discord.ext import commands
import mysql.connector
from os.path import exists
import json

print("Starting...")

with open("phrases.txt", "r") as f:
    phrases = [line.strip() for line in f]

def get_prefix(bot, message):
    config = "configs/" + str(message.guild.id) + ".json"
    if exists(config):
        with open(config, 'r') as f: ##we open and read the prefixes.json, assuming it's in the same file
            loaded = json.load(f) #load the json as prefixes
        return loaded["prefix"]
    else:
        default_config = {'prefix': '!', 'channel': 'None'}
        with open(config, "w") as file:
            json.dump(default_config, file, sort_keys=True, indent=4)
        return default_config["prefix"]
def RanPhase():
    return random.choice(phrases)


owner_id_1 = 539965252897472523
owner_id_2 = 866392964079026188


def check_if_it_is_me1():
    def predicate(ctx):
        return ctx.author.id == owner_id_1

    return commands.check(predicate)


def check_if_it_is_me2():
    def predicate(ctx):
        return ctx.author.id == owner_id_2

    return commands.check(predicate)


def addSongDatabase(song_name, requester_id, requester_name):
    mydb = mysql.connector.connect(
        host="na05-sql.pebblehost.com",
        user="customer_222209_songs",
        password="WazzyFangIsBad123!",
        database="customer_222209_songs"
    )

    mycursor = mydb.cursor()

    mycursor.execute("INSERT INTO songs (song, requester_id, requester_name) VALUES (%s, %s, %s)", (song_name, str(requester_id), requester_name))

    mydb.commit()
    mydb.close()

    print("\n\nAdded values to Database\nSong Name: " + song_name + "\nRequester ID: " + str(requester_id) + "\nRequester Name: " + requester_name)

yt_dlp.utils.bug_reports_message = lambda: ""


class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        "format": "bestaudio/best",
        "extractaudio": True,
        "audioformat": "mp3",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "noplaylist": False,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "source_address": "0.0.0.0",
    }

    FFMPEG_OPTIONS = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn",
    }

    ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get("uploader")
        self.uploader_url = data.get("uploader_url")
        date = data.get("upload_date")
        self.upload_date = date[6:8] + "." + date[4:6] + "." + date[0:4]
        self.title = data.get("title")
        self.thumbnail = data.get("thumbnail")
        self.description = data.get("description")
        self.duration = self.parse_duration(int(data.get("duration")))
        self.tags = data.get("tags")
        self.url = data.get("webpage_url")
        self.views = data.get("view_count")
        self.likes = data.get("like_count")
        self.dislikes = data.get("dislike_count")
        self.stream_url = data.get("url")

    def __str__(self):
        return "**{0.title}** by **{0.uploader}**".format(self)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError("Couldn\'t find anything that matches `{}`".format(search))

        if "entries" not in data:
            process_info = data
        else:
            process_info = None
            for entry in data["entries"]:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError("Couldn\'t find anything that matches `{}`".format(search))

        webpage_url = process_info["webpage_url"]
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError("Couldn\'t fetch `{}`".format(webpage_url))

        if "entries" not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info["entries"].pop(0)
                except IndexError:
                    raise YTDLError("Couldn\'t retrieve any matches for `{}`".format(webpage_url))

        return cls(ctx, discord.FFmpegPCMAudio(info["url"], **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append("{} days".format(days))
        if hours > 0:
            duration.append("{} hours".format(hours))
        if minutes > 0:
            duration.append("{} minutes".format(minutes))
        if seconds > 0:
            duration.append("{} seconds".format(seconds))

        return ", ".join(duration)


class Song:
    __slots__ = ("source", "requester")

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self, now):
        fixedURL = self.source.url.split("https://")[1].split("/")[0]
        if now == 0:
            embed = (discord.Embed(title="Now playing",
                                   description="```css\n{0.source.title}\n```".format(self),
                                   color=discord.Color.blurple())
                     .add_field(name="Duration", value=self.source.duration)
                     .add_field(name="Requested by", value=self.requester.mention)
                     .add_field(name="Uploader", value="[{0.source.uploader}]({0.source.uploader_url})".format(self))
                     .add_field(name="URL", value="[{0}]({1})".format(fixedURL, self.source.url))
                     .set_footer(text=RanPhase())
                     .set_thumbnail(url=self.source.thumbnail))
        elif now == 1:
            embed = (discord.Embed(title="Currently playing song",
                                   description="```css\n{0.source.title}\n```".format(self),
                                   color=discord.Color.blurple())
                     .add_field(name="Duration", value=self.source.duration)
                     .add_field(name="Requested by", value=self.requester.mention)
                     .add_field(name="Uploader", value="[{0.source.uploader}]({0.source.uploader_url})".format(self))
                     .add_field(name="URL", value="[{0}]({1})".format(fixedURL, self.source.url))
                     .set_footer(text=RanPhase())
                     .set_thumbnail(url=self.source.thumbnail))

        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def remove(self, index: int):
        del self._queue[index]


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task(ctx))

    def __del__(self):
        self.audio_player.cancel()

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self, ctx: commands.Context):
        while True:
            self.next.clear()

            try:
                async with timeout(999999999999999999):
                    self.current = await self.songs.get()
            except asyncio.TimeoutError:
                self.songs.clear()

                if self.voice:
                    await self.voice.disconnect()
                    self.voice = None
                return

            self.current.source.volume = 0.5
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(embed=self.current.create_embed(0))
            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage("This command can\'t be used in DM channels.")

        return True


    # Runs right before you do a command. Useful for updating variables
    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    @commands.command(name="leave", aliases=["disconnect"])
    async def _leave(self, ctx: commands.Context):
        if not ctx.voice_state.voice:
            return await ctx.send("Yo retard. Im not in a vc.")

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name="now", aliases=["current", "playing"])
    async def _now(self, ctx: commands.Context):

        await ctx.send(embed=ctx.voice_state.current.create_embed(1))

    @commands.command(name="pause")
    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    async def _pause(self, ctx: commands.Context):

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction("\u2705")

    @commands.command(name="resume")
    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    async def _resume(self, ctx: commands.Context):

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction("\u2705")

    @commands.command(name="skip", aliases=["s"])
    async def _skip(self, ctx: commands.Context):

        members = len(ctx.voice_client.channel.voice_states)

        if not ctx.voice_state.is_playing:
            return await ctx.send("Nothing is playing retard")
        elif ctx.voice_state.voice:
            if members == 1 or members == 2 or members == 3:
                skip_count = 1
            else:
                skip_count = members - 3

        voter = ctx.message.author
        if voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= skip_count:
                await ctx.send("**{0}/{1}**".format(total_votes, skip_count))
                await ctx.send("Skipping...")
                ctx.voice_state.skip()
            else:
                await ctx.send("Skip vote added, currently at **{0}/{1}**".format(total_votes, skip_count))
        else:
            await ctx.send("U already voted fat monkey")

#    @commands.command(name="settings")
#    async def _settings(self, ctx: commands.Context,  setting: str, value="none"):
#        if setting == "prefix":
#            if value == "none":
#                print("Must specify a prefix!")
#            else:


    @commands.command(name="forceskip", aliases=["fs"])
    async def _forceskip(self, ctx: commands.Context):
        role = discord.utils.get(ctx.guild.roles, name="DJ")
        if role in ctx.author.roles:
            ctx.voice_state.skip()
            await ctx.message.add_reaction("\u2705")
        else:
            await ctx.channel.send("No perms lol")

    @commands.command(name="leaderboard")
    async def _leaderboard(self, ctx: commands.Context):
        mydb = mysql.connector.connect(
            host="na05-sql.pebblehost.com",
            user="customer_222209_songs",
            password="WazzyFangIsBad123!",
            database="customer_222209_songs"
        )

        mycursor = mydb.cursor()

        mycursor.execute("SELECT song, count(*) as SameValue from songs GROUP BY song;")
        leaderboardsongs = mycursor.fetchall()
        mydb.close()
        leaderboardsongs.sort(key=lambda x: x[1])
        leaderboardsongs.reverse()

        fixedlist = []
        i = 1
        daword = ""
        for songs in leaderboardsongs:
            if len(songs[0]) > 50:
                fixedsong = songs[0][:50] + "..."
            else:
                fixedsong = songs[0]

            if songs[1] == 1:
                times = " time"
            else:
                times = " times"
            daword += "**" + str(i) + ")** `" + fixedsong + "` - **" + str(songs[1]) + times + "**\n"
            if i > 9:
                break
            i = i + 1

        await ctx.send(embed=(discord.Embed(title="**Top 10 Most Played Songs**", description=(daword))))

    @commands.command(name="queue")
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send("Theres nothing in the queue monkey.")

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)
        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ""
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += "`{0}.` [**{1.source.title}**]({1.source.url})\n".format(i + 1, song)

        embed = (discord.Embed(description="**{} tracks:**\n\n{}".format(len(ctx.voice_state.songs), queue))
                 .set_footer(text="Viewing page {}/{}".format(page, pages)))
        await ctx.send(embed=embed)

    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    @commands.command(name="remove")
    async def _remove(self, ctx: commands.Context, index: int):

        if len(ctx.voice_state.songs) == 0:
            await ctx.send("Theres nothing in the queue monkey.")
            return await ctx.message.add_reaction("\u1f412")

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction("\u2705")

    @commands.command(name="loop")
    async def _loop(self, ctx: commands.Context):
        await ctx.send("I don\'t know why but this is broken. Ima fix it soon enough don\'t worry.")
        # if not ctx.voice_state.is_playing:
        #    return await ctx.send("Listen retard, can you not hear that no music is playing. How slow are you?")
        #    await ctx.message.add_reaction("??")

        # ctx.voice_state.loop = not ctx.voice_state.loop
        # await ctx.message.add_reaction("?")

    @commands.command(name="help", aliases=["h"])
    async def _help(self, ctx: commands.Context):
        await ctx.send(embed=discord.Embed(title="Help", color=discord.Color.blurple(), description="```!play {url or search}```\n**Plays a song**\n\n```!skip```\n**Vote to skip the current song**\n\n```!forceskip```\n**Force-skip the current song (requires DJ role)**\n\n```!queue```\n**View the queue**\n\n```!remove {queue number}```\n**Removes the stated song from the queue**"))

    @commands.command(name="play", aliases=["p", "cock"])
    async def _play(self, ctx: commands.Context, *, search: str):
        if not ctx.voice_state.voice:
            destination = ctx.author.voice.channel
            if ctx.voice_state.voice:
                await ctx.voice_state.voice.move_to(destination)
                return

            ctx.voice_state.voice = await destination.connect()
        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                if len(ctx.voice_client.channel.members) == 1:
                    await ctx.invoke(self._join)
                    ctx.voice_state.songs.clear()
                    async with ctx.typing():
                        try:
                            await ctx.message.add_reaction("\u2705")
                            finding_message = await ctx.send(
                                embed=(discord.Embed(title="Searching for song...", color=discord.Color.blurple())))
                            source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
                        except:
                            await finding_message.delete()
                            await ctx.send(embed=(
                                discord.Embed(title="Could not find any results for: `{}`".format(search),
                                              color=discord.Color.blurple())))
                            await ctx.message.remove_reaction("\u2705", bot.user)
                            await ctx.message.add_reaction("\u274c")
                        else:
                            await finding_message.delete()
                            supervar = str(ctx.voice_state.songs).find("_getters")
                            song = Song(source)
                            await ctx.voice_state.songs.put(song)
                            addSongDatabase(source.title, source.requester.id, source.requester.name)
                            if supervar == -1:
                                fixedURL = source.url.split("https://")[1].split("/")[0]
                                theEmbed = (discord.Embed(title="Queued song",
                                                          description="```css\n{}\n```".format(source.title),
                                                          color=discord.Color.blurple())
                                            .add_field(name="Duration", value=source.duration)
                                            .add_field(name="Requested by", value=source.requester.mention)
                                            .add_field(name="Uploader",
                                                       value="[{0}]({1})".format(source.uploader, source.uploader_url))
                                            .add_field(name="URL", value="[{0}]({1})".format(fixedURL, source.url))
                                            .set_footer(text=RanPhase())
                                            .set_thumbnail(url=source.thumbnail))
                                await ctx.send(embed=theEmbed)
                else:
                    await ctx.send("Someone else is using the bot retard")
                    ctx.message.add_reaction("\u1f921")
            else:
                async with ctx.typing():
                    try:
                        await ctx.message.add_reaction("\u2705")
                        finding_message = await ctx.send(
                            embed=(discord.Embed(title="Searching for song...", color=discord.Color.blurple())))
                        source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
                    except:
                        await finding_message.delete()
                        await ctx.send(embed=(discord.Embed(title="Could not find any results for: `{}`".format(search),
                                                            color=discord.Color.blurple())))
                        await ctx.message.remove_reaction("\u2705", bot.user)
                        await ctx.message.add_reaction("\u274c")
                    else:
                        await finding_message.delete()
                        supervar = str(ctx.voice_state.songs).find("_getters")
                        song = Song(source)
                        await ctx.voice_state.songs.put(song)
                        addSongDatabase(source.title, source.requester.id, source.requester.name)
                        if supervar == -1:
                            fixedURL = source.url.split("https://")[1].split("/")[0]
                            theEmbed = (discord.Embed(title="Queued song",
                                                      description="```css\n{}\n```".format(source.title),
                                                      color=discord.Color.blurple())
                                        .add_field(name="Duration", value=source.duration)
                                        .add_field(name="Requested by", value=source.requester.mention)
                                        .add_field(name="Uploader",
                                                   value="[{0}]({1})".format(source.uploader, source.uploader_url))
                                        .add_field(name="URL", value="[{0}]({1})".format(fixedURL, source.url))
                                        .set_footer(text=RanPhase())
                                        .set_thumbnail(url=source.thumbnail))
                            await ctx.send(embed=theEmbed)

    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("You are not in a call bozo. L + Ratio")


bot = commands.Bot(command_prefix=(get_prefix),)
bot.remove_command("help")
bot.add_cog(Music(bot))

default_config = {'prefix': '!', 'channel': 'None'}

@bot.event
async def on_guild_join(guild):
    config = "configs/" + str(guild.id) + ".json"
    if not(exists(config)):
        with open(config, "w") as file:
            json.dump(default_config, file, sort_keys=True, indent=4)


@bot.event
async def on_ready():
    print("\n\n\nLogged in as:\n{0.user.name}\n{0.user.id}".format(bot))
    await bot.change_presence(activity=discord.Game("Made by grayhawk25"))

bot.run("NzU1ODUwMzk0NTc5NTAxMTU5.X2JSiQ.X0kCbDgZV3t2VwwJ5OpASU0M2xY")