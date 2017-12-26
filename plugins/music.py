from discord.ext import commands
from PIL import Image
from io import BytesIO
import asyncio
import discord
import youtube_dl
import os
import aiohttp
import time
import isodate
from math import ceil
import datetime
import random
from functools import partial

if not discord.opus.is_loaded():
    discord.opus.load_opus('libopus.so')

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

cache_directory = "cache"

ytdl_format_options = {
    'format': 'bestaudio',
    'outtmpl': os.path.join(cache_directory, '%(id)s.%(ext)s'),
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
APIKEY = "AIzaSyCpTUiTsBy5dfgVVrmA9OFAbqU6fVkokMw"


async def search_yt(query):
    """ Searches Youtube API v3 and returns video """
    async with aiohttp.ClientSession() as session:
        payload = {"maxResults": "1", "part": "snippet", "type": "video",
                   "key": APIKEY, "q": query.replace(" ", "+")}
        url = "https://www.googleapis.com/youtube/v3/search"
        web = await session.request("get", url, params=payload)
        resp = await web.json()
        if len(resp["items"]) > 0:
            video = resp["items"][0]
            video_id = video["id"] if type(video["id"]) == str else video["id"]["videoId"]
            video["id"] = video_id
            return video
        else:
            return None


class YTDLSource:
    def __init__(self, ctx, data):
        self.requester = ctx.author
        self.data = data
        self.ctx = ctx
        self.video_id = data.get("id")
        self.channel_id = data.get("channelId")
        self.title = data.get('title')
        self.thumb = data["thumbnails"]["default"].get("url")
        self.duration = None
        self.author_avatar = None

    async def get_author_avatar(self):
        with aiohttp.ClientSession() as session:
            payload = {"id": self.channel_id, "part": "snippet", "key": APIKEY}
            url = "https://www.googleapis.com/youtube/v3/channels"
            web = await session.request("get", url, params=payload)
            resp = await web.json()
            snippet = resp.get("items")[0].get("snippet")
            self.author_avatar = snippet["thumbnails"]["default"].get("url")
        return self.author_avatar

    async def get_duration(self):
        with aiohttp.ClientSession() as session:
            payload = {"id": self.video_id, "part": "contentDetails", "key": APIKEY}
            url = "https://www.googleapis.com/youtube/v3/videos"
            web = await session.request("get", url, params=payload)
            resp = await web.json()
            video = resp["items"][0]["contentDetails"]
            self.duration = isodate.parse_duration(video["duration"]).total_seconds()
        return self.duration

    async def download(self, loop=None):
        self.info = ytdl.extract_info(self.video_id, download=False)
        self.streaming_url = self.info.get("url")

    @property
    def source(self):
        return discord.FFmpegPCMAudio(self.streaming_url)

    @classmethod
    async def from_url(cls, ctx, url):
        data = await search_yt(url)
        video_id = data["id"]
        data = data["snippet"]
        data["id"] = video_id
        return cls(ctx, data)


class VoiceState:
    def __init__(self, music, bot):
        self.music = music
        self.now_playing = None
        self.voice = None
        self.queue = []
        self.bot = bot
        self.song_started = 0
        self.next_song = asyncio.Event()
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    async def audio_player_task(self):
        while True:
            await self.next_song.wait()
            self.next_song.clear()
            if len(self.queue) < 1:
                await self.now_playing.ctx.voice_client.disconnect()
                await self.now_playing.ctx.send("Queue concluded.")
                self.now_playing = None
                self.next_song.clear()
                continue
            player, self.now_playing = self.queue.pop(0)
            await self.now_playing.download()
            player(self.now_playing.source, after=self.toggle_next)
            self.song_started = time.time()

    def skip(self):
        if self.is_playing():
            self.voice.stop()
            return True

    async def stop(self):
        if self.is_playing():
            await self.voice.disconnect()
            self.queue = []
            self.voice = None
            self.now_playing = None
            return True

    def toggle_next(self, error):
        self.bot.loop.call_soon_threadsafe(self.next_song.set)

    def is_playing(self):
        if self.voice is None or self.now_playing is None:
            return None

        return self.voice.is_playing()


class Music:
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, guild):
        state = self.voice_states.get(guild.id)
        if state is None:
            state = VoiceState(self, self.bot)
            self.voice_states[guild.id] = state

        return state

    async def create_voice_client(self, channel):
        try:
            voice = await channel.connect()
        except discord.ClientException:  # already in channel
            voice = channel.guild.voice_client
            await voice.move_to(channel)
        state = self.get_voice_state(channel.guild)
        state.voice = voice

    @commands.command(aliases=["yt"])
    @commands.guild_only()
    async def play(self, ctx, *, query):
        """Streams from a url (almost anything youtube_dl supports)"""
        state = self.get_voice_state(ctx.guild)
        if state.voice is None:
            if ctx.author.voice and ctx.author.voice.channel:
                await self.create_voice_client(ctx.author.voice.channel)
            else:
                return await ctx.send("Not connected to a voice channel.")
        else:
            if ctx.author.voice.channel is not state.voice.channel:
                await state.voice.move_to(ctx.author.voice.channel)

        player = await YTDLSource.from_url(ctx, query)
        state.queue.append((state.voice.play, player))

        if state.now_playing is None:
            state.next_song.set()
            while not state.is_playing():
                await asyncio.sleep(1)
            return await self.nowplaying.invoke(ctx)

        await ctx.send(":minidisc: `{}` has been added to the queue at position `{}`".format(player.title, len(state.queue)))

    async def get_average_colour(self, image_url):
        async with aiohttp.ClientSession() as session:
            response = await session.get(image_url)
            image_bytes = await response.read()
            image_file = BytesIO(image_bytes)
            image = Image.open(image_file)
        w, h = image.size
        pixels = image.getcolors(w * h)
        light_pixels = [c for c in pixels if sum(c[1]) > 25]  # remove black from colours
        most_frequent = max(light_pixels, key=lambda x: x[0])
        return most_frequent[1]

    async def get_now_playing_embed(self, guild):
        state = self.get_voice_state(guild)
        if state.is_playing():
            duration = state.now_playing.duration or await state.now_playing.get_duration()
            current_time = time.time() - state.song_started
            percent = current_time / duration
            seeker_index = ceil(percent * 30)

            minutes, seconds = divmod(duration, 60)
            hours, minutes = divmod(minutes, 60)
            string_duration = datetime.time(*map(int, [hours, minutes, seconds])).strftime("%M:%S")

            minutes, seconds = divmod(current_time, 60)
            hours, minutes = divmod(minutes, 60)
            string_current = datetime.time(*map(int, [hours, minutes, seconds])).strftime("%M:%S")

            seeker = ["▬"] * 30
            seeker.insert(seeker_index - 1, "🔘")

            slider = "`" + "".join(seeker) + "`"
            footer = f"{string_current} / {string_duration} - {str(state.now_playing.requester)}"
            avatar = state.now_playing.author_avatar or await state.now_playing.get_author_avatar()
            avg_colour = await self.get_average_colour(avatar)
            np_embed = discord.Embed(colour=discord.Colour.from_rgb(*avg_colour), title=slider)
            np_embed.set_author(name=state.now_playing.title,
                                url=f"https://www.youtube.com/watch?v={state.now_playing.video_id}",
                                icon_url=avatar)
            np_embed.set_footer(text=footer, icon_url="https://i.imgur.com/2CK3w4E.png")
            return np_embed

    @commands.command(aliases=["np"])
    @commands.guild_only()
    async def nowplaying(self, ctx):
        """ Shows you the currently playing song """
        state = self.get_voice_state(ctx.guild)
        if state.is_playing():
            np_embed = await self.get_now_playing_embed(ctx.guild)
            state.now_playing_message = await ctx.send(embed=np_embed)
        else:
            await ctx.send("Nothing is being played")

    @commands.command()
    @commands.guild_only()
    async def skip(self, ctx):
        """ Skips the song """
        state = self.get_voice_state(ctx.guild)
        if not state.skip():
            await ctx.send("Nothing is being played")

    @commands.command()
    @commands.guild_only()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        state = self.get_voice_state(ctx.guild)
        disconnected = await state.stop()
        if not disconnected:
            await ctx.send("Nothing is being played")

    @commands.command(aliases=["q", "list"], name="queue")
    @commands.guild_only()
    async def _queue(self, ctx, page: int=1):
        """ Shows you the current music queue """
        state = self.get_voice_state(ctx.guild)
        if len(state.queue) < 1:
            await ctx.send("The queue is empty")
        else:
            offset = 10 * (page - 1)
            pages = ceil(len(state.queue) / 10)
            if page > pages or page < 0:
                await ctx.send("That page does not exist")
            else:
                view = state.queue[offset:offset + 10]

                #nowplaying_fmt = await self.get_now_playing_(ctx.guild)
                s_fmt = "{0}. {1[1].title}"
                song_queue_fmt = "\n".join([s_fmt.format(i + 1 + offset, s) for i, s in enumerate(view)])

                queue_embed = discord.Embed(description="\n".join(["```", song_queue_fmt, "```"]))
                queue_embed.set_footer(text="Page {}/{}".format(page, pages))
                queue_embed.set_thumbnail(url=state.now_playing.thumb)
                await ctx.send(embed=queue_embed)


def setup(bot):
    bot.add_cog(Music(bot))
