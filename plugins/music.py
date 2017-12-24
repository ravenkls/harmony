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
import pafy

if not discord.opus.is_loaded():
    discord.opus.load_opus('libopus.so')

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

cache_directory = "cache"

ytdl_format_options = {
    'format': 'webm',
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
        self.data = data
        self.ctx = ctx
        self.video_id = data.get("id")
        self.title = data.get('title')
        self.thumb = data["thumbnails"]["default"].get("url")
        pafy_vid = pafy.new(self.video_id)
        bestaudio = pafy_vid.getbestaudio()
        self.streaming_url = bestaudio.url
        self.duration = None
        self.filename = None

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
        if not os.path.exists(os.path.join(cache_directory, self.video_id + ".webm")):
            loop = loop or asyncio.get_event_loop()
            dl = await loop.run_in_executor(None, ytdl.extract_info, self.video_id)
            self.filename = os.path.join(cache_directory, self.video_id + "." + dl["ext"])
        else:
            self.filename = os.path.join(cache_directory, self.video_id + ".webm")
        return self.filename

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


class Music:
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.next_song = asyncio.Event()
        self.now_playing = None
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())
        self.song_started = 0

    def toggle_next(self, error):
        self.bot.loop.call_soon_threadsafe(self.next_song.set)

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

    def is_playing(self, ctx):
        if ctx.voice_client is None or self.now_playing is None:
            return None

        return ctx.voice_client.is_playing()

    @commands.command(aliases=["yt"])
    @commands.guild_only()
    async def play(self, ctx, *, query):
        """Streams from a url (almost anything youtube_dl supports)"""
        if ctx.voice_client is None:
            if ctx.author.voice and ctx.author.voice.channel:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send("Not connected to a voice channel.")
        else:
            if ctx.author.voice.channel is not ctx.voice_client.channel:
                await ctx.voice_client.move_to(ctx.author.voice.channel)

        player = await YTDLSource.from_url(ctx, query)
        self.queue.append((ctx.voice_client.play, player))

        await ctx.send(":minidisc: `{}` has been added to the queue at position `{}`".format(player.title, len(self.queue)))

        if self.now_playing is None:
            self.next_song.set()

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

    @commands.command(aliases=["np"])
    @commands.guild_only()
    async def nowplaying(self, ctx):
        """ Shows you the currently playing song """
        if self.is_playing(ctx):
            duration = self.now_playing.duration or await self.now_playing.get_duration()
            current_time = time.time() - self.song_started
            percent = current_time / duration
            seeker_index = ceil(percent * 25)

            minutes, seconds = divmod(duration, 60)
            hours, minutes = divmod(minutes, 60)
            string_duration = datetime.time(*map(int, [hours, minutes, seconds])).strftime("%M:%S")

            minutes, seconds = divmod(current_time, 60)
            hours, minutes = divmod(minutes, 60)
            string_current = datetime.time(*map(int, [hours, minutes, seconds])).strftime("%M:%S")

            seeker = ["▬"] * 25
            seeker.insert(seeker_index - 1, ":radio_button:")
            nowplaying_fmt = "**Now playing:** [{}](https://www.youtube.com/watch?v={})"
            controls = ":play_pause: :sound: `{} / {}`".format(string_current, string_duration)
            desc = "\n".join([nowplaying_fmt.format(self.now_playing.title, self.now_playing.video_id), "~~" + "".join(seeker) + "~~", controls])
            avg_colour = await self.get_average_colour(self.now_playing.thumb)
            np_embed = discord.Embed(description=desc, colour=discord.Colour.from_rgb(*avg_colour))
            np_embed.set_thumbnail(url=self.now_playing.thumb)
            await ctx.send(embed=np_embed)
        else:
            await ctx.send("Nothing is being played")

    @commands.command()
    @commands.guild_only()
    async def skip(self, ctx):
        """ Skips the song """
        if self.is_playing(ctx):
            self.bot.log("skipping")
            ctx.voice_client.stop()
            # self.toggle_next(None)
        else:
            await ctx.send("Nothing is being played")

    @commands.command()
    @commands.guild_only()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        if self.is_playing(ctx):
            await ctx.voice_client.disconnect()
        else:
            await ctx.send("Nothing is being played")

    @commands.command(aliases=["q", "list"], name="queue")
    @commands.guild_only()
    async def _queue(self, ctx, page: int=1):
        """ Shows you the current music queue """
        if len(self.queue) < 1:
            await ctx.send("The queue is empty")
        else:
            offset = 10 * (page - 1)
            pages = ceil(len(self.queue) / 10)
            if page > pages or page < 0:
                await ctx.send("That page does not exist")
            else:
                view = self.queue[offset:offset + 10]
                nowplaying_fmt = "[{}](https://www.youtube.com/watch?v={})".format(self.now_playing.title, self.now_playing.video_id)
                queue_embed = discord.Embed(title="Now playing", description=nowplaying_fmt, colour=random.randint(0, 0xFFFFFF))
                s_fmt = "**{0}**. {1[1].title}"
                queue_embed.add_field(name="Song Queue", value="\n".join([s_fmt.format(i + 1 + offset, s) for i, s in enumerate(view)]))
                queue_embed.set_footer(text="Page {}/{}".format(page, pages))
                await ctx.send(embed=queue_embed)


def setup(bot):
    bot.add_cog(Music(bot))
