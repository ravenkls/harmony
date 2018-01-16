from discord.ext import commands
from PIL import Image
from io import BytesIO
from functools import partial, lru_cache
from bs4 import BeautifulSoup
from math import ceil
from fuzzywuzzy import process
from operator import itemgetter
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy
import json
import asyncio
import discord
import youtube_dl
import os
import aiohttp
import time
import isodate
import datetime
import random

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
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")


class SpotifyAPI:
    def __init__(self):
        client_credentials_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID,
                                                              client_secret=SPOTIFY_CLIENT_SECRET)
        self.spotify_api = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

    def get_spotify_playlist(self, uri):
        user_id = uri.split(":")[2]
        playlist_id = uri.split(":")[4]
        playlist = self.spotify_api.user_playlist(user_id, playlist_id)
        return playlist

    def get_all_playlists(self, user_id):
        response = {}
        offset = 0

        while len(response) % 50 == 0:
            playlists = self.spotify_api.user_playlists(user_id, limit=50, offset=offset)
            for playlist in playlists.get("items"):
                response[playlist.get("name")] = playlist.get("uri")
            offset += 50

        return response

    def search_playlist_file(self, query, file="playlists.json"):
        with open(file) as playlists_file:
            playlists = json.loads(playlists_file.read())

        results = process.extract(query, playlists.keys())
        top = max(results, key=itemgetter(1))
        return {"name": top[0], "uri": playlists.get(top[0])}


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
            payload = {"id": self.channel_id, "part": "snippet", "key": YOUTUBE_API_KEY}
            url = "https://www.googleapis.com/youtube/v3/channels"
            web = await session.request("get", url, params=payload)
            resp = await web.json()
            snippet = resp.get("items")[0].get("snippet")
            self.author_avatar = snippet["thumbnails"]["default"].get("url")
        return self.author_avatar

    async def get_duration(self):
        with aiohttp.ClientSession() as session:
            payload = {"id": self.video_id, "part": "contentDetails", "key": YOUTUBE_API_KEY}
            url = "https://www.googleapis.com/youtube/v3/videos"
            web = await session.request("get", url, params=payload)
            resp = await web.json()
            video = resp["items"][0]["contentDetails"]
            self.duration = isodate.parse_duration(video["duration"]).total_seconds()
        return self.duration

    async def download(self, loop=None):
        self.info = ytdl.extract_info(self.video_id, download=False)
        self.streaming_url = self.info.get("url")
        duration = await self.get_duration()
        avatar = await self.get_author_avatar()
        self.avatar_average_colour = await Music.get_average_colour(avatar)

    @property
    def source(self):
        return discord.FFmpegPCMAudio(self.streaming_url)

    @classmethod
    async def from_url(cls, ctx, url):
        data = await cls.search_yt(url)
        video_id = data["id"]
        data = data["snippet"]
        data["id"] = video_id
        return cls(ctx, data)

    @staticmethod
    async def search_yt(query):
        """ Searches Youtube API v3 and returns video """
        async with aiohttp.ClientSession() as session:
            payload = {"maxResults": "1", "part": "snippet", "type": "video",
                       "key": YOUTUBE_API_KEY, "q": query.replace(" ", "+")}
            url = "https://www.googleapis.com/youtube/v3/search"
            web = await session.request("get", url, params=payload)
            resp = await web.json()
            if len(resp["items"]) > 0:
                # Decode the JSON
                video = resp.get("items")[0]
                if isinstance(video.get("id"), str):
                    video_id = video["id"]
                else:
                    video_id = video["id"]["videoId"]

                video["id"] = video_id
                return video


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
        self.looping_queue = []
        self.shuffled_queue = []
        self.shuffle = False
        self.player = None
        self.leave_task_ctx = None

    def reset(self):
        self.now_playing = None
        self.player = None
        self.voice = None
        self.song_started = 0
        self.queue = []
        self.looping_queue = []
        self.shuffled_queue = []
        self.shuffle = False

    async def audio_player_task(self):
        while True:
            await self.next_song.wait()
            self.next_song.clear()
            if not self.voice.is_connected():
                self.queue = []
                self.looping_queue = []
                self.shuffled_queue = []
                self.shuffle = False
            self.get_now_playing_embed.cache_clear()
            if len(self.queue) < 1:
                if self.looping_queue:
                    self.queue = list(self.looping_queue)
                    if self.shuffle:
                        self.shudffled_queue = list(self.queue)
                        random.shuffle(self.shuffled_queue)
                else:
                    await self.now_playing.ctx.send("Queue concluded.")
                    if self.voice:
                        await self.voice.disconnect()
                        self.reset()
                    continue
            if self.shuffle:
                self.player, self.now_playing = self.shuffled_queue.pop(0)
                self.queue.remove((self.player, self.now_playing))
            else:
                self.player, self.now_playing = self.queue.pop(0)
            await self.now_playing.download()
            self.player(self.now_playing.source, after=self.toggle_next)
            self.song_started = time.time()

    def loopqueue(self):
        if self.looping_queue:
            self.looping_queue = []
        else:
            self.looping_queue = list(self.queue)
            self.looping_queue.insert(0, (self.player, self.now_playing))
        return len(self.looping_queue) > 0

    def shuffle_queue(self):
        if self.shuffle:
            self.shuffle = False
            self.shuffled_queue = []
        else:
            self.shuffle = True
            self.shuffled_queue = list(self.queue)
            random.shuffle(self.shuffled_queue)
        return self.shuffle

    def add_to_queue(self, value):
        self.queue.append(value)
        if self.shuffle:
            self.shuffled_queue.append(value)
        if self.looping_queue:
            self.looping_queue.append(value)

    def skip(self):
        if self.is_playing():
            self.voice.stop()
            return True

    async def stop(self):
        if self.is_playing():
            await self.voice.disconnect()
            return True

    def toggle_next(self, error):
        self.bot.loop.call_soon_threadsafe(self.next_song.set)

    def is_playing(self):
        if self.voice is None:
            return False

        return self.voice.is_playing()

    @lru_cache(maxsize=1)
    def get_now_playing_embed(self):
        if self.is_playing():
            duration = self.now_playing.duration
            current_time = time.time() - self.song_started
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

            slider = "".join(seeker)
            footer = f"{string_current} / {string_duration} - {str(self.now_playing.requester)}"
            avatar = self.now_playing.author_avatar
            avg_colour = self.now_playing.avatar_average_colour
            np_embed = discord.Embed(colour=discord.Colour.from_rgb(*avg_colour), title=slider)
            np_embed.set_author(name=self.now_playing.title,
                                url=f"https://www.youtube.com/watch?v={self.now_playing.video_id}",
                                icon_url=avatar)
            np_embed.set_footer(text=footer, icon_url="https://i.imgur.com/2CK3w4E.png")
            return np_embed
        else:
            return None


class Music:
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}
        self.spotify_api = SpotifyAPI()

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
        self.bot.log("Voice state created at {}".format(channel.guild.name), "MUSIC")

    @commands.command()
    @commands.is_owner()
    async def musicstates(self, ctx):
        states = dict(filter(lambda s: s[1].is_playing(), self.voice_states.items()))
        response = f"**{len(states)} guilds are using voice**"
        for guild_id, state in states.items():
            guild = self.bot.get_guild(guild_id)
            response += f"\n* {guild.name} - {state.now_playing.title}"
        await ctx.send(response)

    @commands.command()
    @commands.guild_only()
    async def spotify(self, ctx, *, query="Today's Top Hits"):
        """Adds a spotify playlist to the music queue by query or randomly"""
        ask_message = await ctx.send(f"Searching spotify for `{query}`...")
        state = self.get_voice_state(ctx.guild)

        playlist_info = self.spotify_api.search_playlist_file(query)
        playlist = self.spotify_api.get_spotify_playlist(playlist_info.get("uri"))

        def check(reaction, user):
            if user == ctx.author:
                return str(reaction) in ("\U00002705", "\U0000274E")
            return False

        await ask_message.edit(content=f"Should I add `{playlist.get('name')}` to the queue?")
        await ask_message.add_reaction("\U00002705")  # cjeck mark
        await ask_message.add_reaction("\U0000274E")  # cross mark
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ask_message.delete()
            return await ctx.send("User failed to respond in 30 seconds")
        else:
            await ask_message.delete()
            if str(reaction) == "\U0000274E":  # cross mark
                return

        if state.voice is None:
            if ctx.author.voice and ctx.author.voice.channel:
                await self.create_voice_client(ctx.author.voice.channel)
            else:
                return await ctx.send("Not connected to a voice channel.")
        else:
            if ctx.author.voice.channel is not state.voice.channel:
                await state.voice.move_to(ctx.author.voice.channel)

        unpacking_message = await ctx.send(f"Unpacking `{playlist.get('name')}` playlist")

        for song in playlist["tracks"]["items"]:
            name = song["track"]["name"]
            artist = ", ".join(artist["name"] for artist in song["track"]["artists"])
            song = await YTDLSource.from_url(ctx, " ".join([name, "-", artist]))
            try:
                state.add_to_queue((state.voice.play, song))
            except AttributeError:
                state.reset()
                break
            if state.looping_queue:
                state.looping_queue.append((state.voice.play, song))
            if not state.is_playing():
                state.next_song.set()
                await ctx.send("Now playing `{}`".format(song.title))

        await unpacking_message.edit(content=f"`{playlist.get('name')}` has been unpacked into the queue")

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

        song = await YTDLSource.from_url(ctx, query)
        state.add_to_queue((state.voice.play, song))
        if state.looping_queue:
            state.looping_queue.append((state.voice.play, song))

        if not state.is_playing():
            state.next_song.set()
            return await ctx.send("Now playing `{}`".format(song.title))

        await ctx.send("`{}` has been added to the queue at position `{}`".format(song.title, len(state.queue)))

    @commands.command()
    @commands.guild_only()
    async def loopqueue(self, ctx):
        """Loops the current queue"""
        state = self.get_voice_state(ctx.guild)
        if state.is_playing():
            looping = state.loopqueue()
            if looping:
                await ctx.send("The current queue will now loop")
            else:
                await ctx.send("The queue will no longer loop")
        else:
            await ctx.send("Nothing is being played")

    @commands.command()
    @commands.guild_only()
    async def remove(self, ctx, position):
        """Removes an item from the queue"""
        state = self.get_voice_state(ctx.guild)
        if len(state.queue) >= int(position):
            if state.shuffle:
                player, song = state.shuffled_queue.pop(int(position) - 1)
                state.queue.remove((player, song))
            else:
                player, song = state.queue.pop(int(position) - 1)

            if state.looping_queue:
                state.looping_queue.remove((player, song))
            await ctx.send(f"`{song.title}` has been removed from the list")
        else:
            await ctx.send("That position doesn't exist")

    @commands.command()
    @commands.guild_only()
    async def move(self, ctx, old_position, new_position):
        """Moves an item from one position to another in a queue"""
        state = self.get_voice_state(ctx.guild)
        if len(state.queue) >= int(old_position):
            if len(state.queue) >= int(new_position):
                if state.shuffle:
                    player, song = state.shuffled_queue.pop(int(old_position) - 1)
                    state.shuffled_queue.insert(int(new_position) - 1, (player, song))
                else:
                    player, song = state.queue.pop(int(old_position) - 1)
                    state.queue.insert(int(new_position) - 1, (player, song))
                await ctx.send(f"`{song.title}` has been moved from position `{old_position}` to `{new_position}`")
            else:
                await ctx.send(f"I can't move a song to a position that doesn't exist")
        else:
            await ctx.send("That position doesn't exist")

    @commands.command()
    @commands.guild_only()
    async def shuffle(self, ctx):
        """Shuffles the queue"""
        state = self.get_voice_state(ctx.guild)
        if state.is_playing():
            shuffling = state.shuffle_queue()
            if shuffling:
                await ctx.send("The queue has been shuffled")
            else:
                await ctx.send("The queue has been unshuffled")
        else:
            await ctx.send("Nothing is being played")

    @commands.command()
    async def lyrics(self, ctx, *, song):
        """Get the lyrics of a song (provided by azlyrics.com)"""
        async with aiohttp.ClientSession() as session:
            search_url = "https://search.azlyrics.com/search.php"
            web = await session.request("get", search_url, params={"q": song})
            text = await web.text()
        soup = BeautifulSoup(text, "html.parser")
        panels = soup.findAll("div", {"class": "panel"})
        if not panels:
            song_results = None
        for p in panels:
            if "Song results" in p.select_one(".panel-heading").text:
                song_results = p
                break
        if not song_results:
            desc = "Sorry, your search returned no results. Try to compose less restrictive search query or check spelling."
        else:
            items = song_results.findAll("td", {"class": "text-left"})
            results = []
            for item in items[:5]:
                anchor = item.select_one("a")
                title, artist = item.findAll("b")[:2]
                results.append(f"[{title.text} by {artist.text}]({anchor.get('href')})")
            desc = "\n".join(f"**{n+1}.** {href}" for n, href in enumerate(results))
        lyrics_embed = discord.Embed(description=desc, colour=0x9292C5)
        lyrics_embed.set_author(name="AZLyrics", icon_url="https://i.imgur.com/uGJZtDB.png")
        await ctx.send(embed=lyrics_embed)

    @staticmethod
    async def get_average_colour(image_url):
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
        state = self.get_voice_state(ctx.guild)
        if state.is_playing():
            np_embed = state.get_now_playing_embed()
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
        """Shows you the current music queue"""
        state = self.get_voice_state(ctx.guild)
        if state.shuffle:
            current_queue = state.shuffled_queue
        else:
            current_queue = state.queue

        if len(state.queue) < 1:
            await ctx.send("The queue is empty")
        else:
            offset = 10 * (page - 1)
            pages = ceil(len(current_queue) / 10)
            if page > pages or page < 0:
                await ctx.send("That page does not exist")
            else:
                tmp_queue = list(current_queue)
                view = tmp_queue[offset:offset + 10]

                s_fmt = "**{0}.** {1[1].title}"
                song_queue_fmt = "\n".join([s_fmt.format(i + 1 + offset, s) for i, s in enumerate(view)])

                queue_embed = discord.Embed(title="Now Playing",
                                            description=state.now_playing.title,
                                            colour=self.bot.embed_colour())
                queue_embed.add_field(name="Song queue", value=song_queue_fmt)
                footer_text = "Page {}/{}".format(page, pages)
                if state.looping_queue:
                    footer_text += " (Looping) "
                if state.shuffle:
                    footer_text += " (Shuffled) "
                queue_embed.set_footer(text=footer_text)
                await ctx.send(embed=queue_embed)


def setup(bot):
    bot.add_cog(Music(bot))
