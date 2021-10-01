import asyncio
import functools
import itertools
import math
import random
import discord
import youtube_dl
from async_timeout import timeout
from discord.ext import commands

ownerid1 = 539965252897472523
ownerid2 = 866392964079026188

def check_if_it_is_me1():
    def predicate(ctx):
        return ctx.author.id == ownerid1
    return commands.check(predicate)


def check_if_it_is_me2():
    def predicate(ctx):
        return ctx.author.id == ownerid2
    return commands.check(predicate)

# Silence useless bug reports messages
youtube_dl.utils.bug_reports_message = lambda: ''


class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    def __str__(self):
        return '**{0.title}** by **{0.uploader}**'.format(self)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError('Couldn\'t find anything that matches `{}`'.format(search))

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError('Couldn\'t find anything that matches `{}`'.format(search))

        webpage_url = process_info['webpage_url']
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError('Couldn\'t fetch `{}`'.format(webpage_url))

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError('Couldn\'t retrieve any matches for `{}`'.format(webpage_url))

        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append('{} days'.format(days))
        if hours > 0:
            duration.append('{} hours'.format(hours))
        if minutes > 0:
            duration.append('{} minutes'.format(minutes))
        if seconds > 0:
            duration.append('{} seconds'.format(seconds))

        return ', '.join(duration)


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self, now):
        fixedURL = self.source.url.split("https://")[1].split("/")[0]
        if now == 0:
            embed = (discord.Embed(title='Now playing',
                                   description='```css\n{0.source.title}\n```'.format(self),
                                   color=discord.Color.blurple())
                     .add_field(name='Duration', value=self.source.duration)
                     .add_field(name='Requested by', value=self.requester.mention)
                     .add_field(name='Uploader', value='[{0.source.uploader}]({0.source.uploader_url})'.format(self))
                     .add_field(name='URL', value='[{0}]({1})'.format(fixedURL, self.source.url))
                     .set_thumbnail(url=self.source.thumbnail))
        elif now == 1:
            embed = (discord.Embed(title='Currently playing song',
                                   description='```css\n{0.source.title}\n```'.format(self),
                                   color=discord.Color.blurple())
                     .add_field(name='Duration', value=self.source.duration)
                     .add_field(name='Requested by', value=self.requester.mention)
                     .add_field(name='Uploader', value='[{0.source.uploader}]({0.source.uploader_url})'.format(self))
                     .add_field(name='URL', value='[{0}]({1})'.format(fixedURL, self.source.url))
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

    def shuffle(self):
        random.shuffle(self._queue)

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

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task(ctx))

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self, ctx: commands.Context):
        while True:
            self.next.clear()

            if not self.loop:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                try:
                    async with timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    await ctx.voice_state.stop()
                    del self.voice_states[ctx.guild.id]
                    return

            self.current.source.volume = self._volume
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
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)


    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('{}'.format(str(error)))
        await ctx.message.add_reaction('🐒')

    @commands.command(name='join', invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context):
        """Joins a voice channel."""

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()
    @commands.command(name='summon')
    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Summons the bot to a voice channel.
        If no channel was specified, it joins your channel.
        """
        if not channel and not ctx.author.voice:
            raise VoiceError('You are neither connected to a voice channel nor specified a channel to join.')
        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    async def _leave(self, ctx: commands.Context):
        """Clears the queue and leaves the voice channel."""
        if not ctx.voice_state.voice:
            return await ctx.send('Yo retard. Im not in a vc.')

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    async def _volume(self, ctx: commands.Context, *, volume: int):
        """Sets the volume of the player."""

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        if 0 > volume > 100:
            return await ctx.send('Volume must be between 0 and 100')

        ctx.voice_state.volume = volume / 100
        await ctx.send('Volume of the player set to {}%'.format(volume))

    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        """Displays the currently playing song."""

        await ctx.send(embed=ctx.voice_state.current.create_embed(1))

    @commands.command(name='pause')
    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    async def _pause(self, ctx: commands.Context):
        """Pauses the currently playing song."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='resume')
    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    async def _resume(self, ctx: commands.Context):
        """Resumes a currently paused song."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='stop')
    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    async def _stop(self, ctx: commands.Context):
        """Stops playing song and clears the queue."""

        ctx.voice_state.songs.clear()

        if not ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('⏹')


    @commands.command(name='skip', aliases=['s'])
    async def _skip(self, ctx: commands.Context):

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing is playing retard')
            await ctx.message.add_reaction('🐒')
        if ctx.voice_state.voice:
            print(len(ctx.channel.members()))
            if (len(ctx.channel.members())) == 1 or (len(ctx.channel.members())) == 2:

               skip_count = 1
            else:
                skip_count = int(len(ctx.channel.members())) - 2

        voter = ctx.message.author
        if voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= skip_count:
                await ctx.send('**{0}/{1}**'.format(total_votes, skip_count))
                await ctx.send('Skipping...')
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send('Skip vote added, currently at **{0}/{1}**'.format(total_votes, skip_count))

        else:
            await ctx.send('Ok chump boi, you cant vote twice.')
            await ctx.message.add_reaction('🐒')
            await ctx.message.add_reaction('👨‍❤️‍💋‍👨')
            await ctx.message.add_reaction('🇷')
            await ctx.message.add_reaction('🇪')
            await ctx.message.add_reaction('🇹')
            await ctx.message.add_reaction('🇦')
            await ctx.message.add_reaction('🇩')

    @commands.command(name='forceskip', aliases=['fs'])
    async def _forceskip(self, ctx: commands.Context):
        print(ctx.get_channel(self.bot.message.channel))
        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing is playing retard')
            await ctx.message.add_reaction('🐒')
        else:
            ctx.voice_state.skip()

    @commands.command(name='queue')
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Theres nothing in the queue monkey.')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)
        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(i + 1, song)

        embed = (discord.Embed(description='**{} tracks:**\n\n{}'.format(len(ctx.voice_state.songs), queue))
                 .set_footer(text='Viewing page {}/{}'.format(page, pages)))
        await ctx.send(embed=embed)

    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffles the queue."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Theres nothing in the queue monkey.')

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('✅')

    @commands.check_any(commands.has_permissions(manage_guild=True), check_if_it_is_me1(), check_if_it_is_me2())
    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):
        """Removes a song from the queue at a given index."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Theres nothing in the queue monkey.')
            await ctx.message.add_reaction('🐒')

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction('✅')

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        await ctx.send("I don't know why but this is broken. Ima fix it soon enough don't worry.")
        #if not ctx.voice_state.is_playing:
        #    return await ctx.send('Listen retard, can you not hear that no music is play. How slow are you?')
        #    await ctx.message.add_reaction('🐒')

        #ctx.voice_state.loop = not ctx.voice_state.loop
        #await ctx.message.add_reaction('✅')

    @commands.command(name='play', aliases=['p'])
    async def _play(self, ctx: commands.Context, *, search: str):
        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)
        async with ctx.typing():
            try:
                await ctx.message.add_reaction('✅')
                finding_message = await ctx.send(embed=(discord.Embed(title='Searching for song...')))
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except:
                await finding_message.delete()
                await ctx.send(embed=(discord.Embed(title='Could not find any results for: `{}`'.format(search))))
                await ctx.message.remove_reaction('✅', bot.user)
                await ctx.message.add_reaction('❌')
            else:
                await finding_message.delete()
                supervar = str(ctx.voice_state.songs).find("_getters")
                song = Song(source)
                await ctx.voice_state.songs.put(song)
                if supervar == -1:
                    fixedURL = source.url.split("https://")[1].split("/")[0]
                    theEmbed = (discord.Embed(title='Queued song',
                                                description='```css\n{}\n```'.format(source.title),
                                                color=discord.Color.blurple())
                                .add_field(name='Duration', value=source.duration)
                                .add_field(name='Requested by', value=source.requester.mention)
                                .add_field(name='Uploader', value='[{0}]({1})'.format(source.uploader, source.uploader_url))
                                .add_field(name='URL', value='[{0}]({1})'.format(fixedURL, source.url))
                                .set_thumbnail(url=source.thumbnail))
                    await ctx.send(embed=theEmbed)

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('You are not in a call bozo. L + Ratio')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('Buddy im already in another VC. Be patient.')


mode = 1



if mode == 0:
    bot = commands.Bot('!', description='L')
else:
    bot = commands.Bot('?', description='L')

bot.add_cog(Music(bot))

@bot.event
async def on_ready():
    print('Logged in as:\n{0.user.name}\n{0.user.id}'.format(bot))
    await bot.change_presence(activity=discord.Game("Made by Swiftzerr"))


if mode == 0:
    bot.run('NzU1ODUwMzk0NTc5NTAxMTU5.X2JSiQ.X0kCbDgZV3t2VwwJ5OpASU0M2xY')
else:
    bot.run('ODkzMjk0MjMwMTQ1OTk4ODU5.YVZXFQ.BjtEA6CVH8qG21IShY6vh2INjRY')
