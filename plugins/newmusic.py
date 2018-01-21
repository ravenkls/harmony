from spotipy.oauth2 import SpotifyClientCredentials
from discord.ext import commands
from operator import itemgetter
from fuzzywuzzy import process
import youtube_dl
import datetime
import spotipy
import discord
import asyncio
import aiohttp
import random
import json
import math
import os
import re


if not discord.opus.is_loaded():
    discord.opus.load_opus('libopus.so')


YOUTUBE_DL_OPTIONS = {
    'format': 'bestaudio',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
}

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

api_keys = {"youtube": os.environ.get("YOUTUBE_API_KEY", ""),
            "spotify": os.environ.get("SPOTIFY_CLIENT_ID", ""),
            "spotify_secret": os.environ.get("SPOTIFY_CLIENT_SECRET", "")}


class QueueEmpty(Exception):
    """Exception used when the queue is empty"""
    pass


class MusicNotPlaying(Exception):
    """Exception used when no music is being played"""
    pass


class SpotifyPlaylist:
    def __init__(self, playlist, *, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.ytdl = youtube_dl.YoutubeDL(YOUTUBE_DL_OPTIONS)
        self.data = playlist

    def __str__(self):
        return self.data.get("name")

    def __repr__(self):
        return "<SpotifyPlaylist: {}>".format(self.__str__())

    async def songs(self):
        youtube = YouTube(self.loop)
        for song in self.data["tracks"]["items"]:
            track = song.get("track")
            track_name = track.get("name")
            track_artists = ", ".join([artist["name"] for artist in track["artists"]])
            query = f"{track_name} - {track_artists}"
            video = await youtube.search(query)
            yield video

    @classmethod
    def from_uri(cls, uri, *, loop=None):
        """Create a spotify playlist object from a URI"""
        uri_pattern = re.search(r"^spotify:user:(.*?):playlist:(.*?)$", uri)
        if uri_pattern is None:
            return None

        manager = SpotifyClientCredentials(client_id=api_keys.get("spotify"),
                                           client_secret=api_keys.get("spotify_secret"))
        spotify_api = spotipy.Spotify(client_credentials_manager=manager)

        user_id = uri_pattern.group(1)
        playlist_id = uri_pattern.group(2)
        playlist = spotify_api.user_playlist(user_id, playlist_id)

        return cls(playlist, loop=loop)

    @classmethod
    def from_file(cls, query, file="playlists.json", *, loop=None):
        """Searches a json file for a playlist uri"""
        with open(file) as playlists_file:
            playlists = json.loads(playlists_file.read())

        results = process.extract(query, playlists.keys())
        top = max(results, key=itemgetter(1))
        uri = playlists.get(top[0])

        return cls.from_uri(uri, loop=loop)


class YouTube:
    def __init__(self, loop):
        """Handles all YouTube video and playlists information"""
        self.loop = loop

    @staticmethod
    def is_video_url(url):
        """Checks whether a string is a YouTube url, returns URL if it is"""
        url_pattern = re.search(r"http[s]?:\/\/www\.youtube\.com\/watch\?v=\S{11}", url)  # normal youtube URL
        if url_pattern is not None:
            return url_pattern.group()

        url_pattern = re.search(r"http[s]?:\/\/youtu\.be\/\S{11}", url)  # youtu.be links
        if url_pattern is not None:
            return url_pattern.group()

        return False

    async def api_call(self, endpoint, params):
        """Sends a request to the YouTube v3 API"""
        params.update({"key": api_keys.get("youtube")})  # add api key to the payload
        async with aiohttp.ClientSession() as session:
            endpoint = "https://www.googleapis.com/youtube/v3/" + endpoint
            response = await session.get(endpoint, params=params)
            youtube_json = await response.json()  # Convert response to json
            if youtube_json.get("error"):  # If the request returned an error raise an exception
                message = youtube_json["error"]["errors"][0]["reason"]
                raise aiohttp.http_exceptions.HttpBadRequest(message)
        return youtube_json

    async def search(self, query):
        """Searches YouTube for videos, returns list"""
        payload = {"maxResults": "1",
                   "part": "snippet",
                   "type": "video",
                   "q": query}

        youtube_json = await self.api_call("search", params=payload)

        if youtube_json.get("items"):
            video = youtube_json["items"][0]
            video_id = video["id"]["videoId"]
            video_title = video["snippet"]["title"]
            return YouTubeVideo(video_id, title=video_title, loop=self.loop)
        else:
            return None

    async def search_many(self, query, limit=5):
        """Searches YouTube for videos, returns list"""
        payload = {"maxResults": str(limit),
                   "part": "snippet",
                   "type": "video",
                   "q": query}

        youtube_json = await self.api_call("search", params=payload)

        videos_json = youtube_json.get("items")
        video_ids = (video["id"]["videoId"] for video in videos_json)  # All video IDs
        video_titles = (video["snippet"]["title"] for video in videos_json)  # All video title
        videos = []
        for video_title, video_id in zip(video_titles, video_ids):
            videos.append(YouTubeVideo(video_id, title=video_title, loop=self.loop))

        return videos


class YouTubeVideo:
    def __init__(self, video_url, title=None, *, loop=None):
        """Represents a YouTube video"""
        self.video_url = video_url
        self.loop = loop or asyncio.get_event_loop()
        self.ytdl = youtube_dl.YoutubeDL(YOUTUBE_DL_OPTIONS)
        self.title = title
        self.channel = None
        self.requester = None
        self.downloaded = False

    def __str__(self):
        return self.title or self.video_url

    def __repr__(self):
        return "<YoutubeVideo: {}>".format(self.__str__())

    async def download(self):
        if not self.downloaded:
            data = await self.loop.run_in_executor(None, self.ytdl.extract_info, self.video_url, False)
            for name, value in data.items():
                if type(value) not in (list, tuple, dict):
                    setattr(self, name, value)  # convert dictionary into variables
            self.downloaded = True

    @property
    def embed(self):
        if self.downloaded:
            embed = discord.Embed(title=self.title, url=self.webpage_url)
            embed.set_thumbnail(url=self.thumbnail)
            minutes, seconds = divmod(self.duration, 60)
            hours, minutes = divmod(minutes, 60)
            duration = datetime.time(hours, minutes, seconds).strftime("%M:%S")
            embed.add_field(name="Duration", value=duration)
            # embed.add_field("Song starting in", value)  # how long until the song will start
            embed.add_field(name="Requester", value=str(self.requester))
        else:
            embed = discord.Embed(title=self.title or self.video_url)

        return embed

    @property
    def source(self):
        if self.downloaded:
            return discord.FFmpegPCMAudio(self.url)
        else:
            return None

    @classmethod
    async def from_url(cls, video_url, *, loop=None):
        video = cls(video_url, loop=loop)
        await video.download()
        return video


class MusicQueue:
    def __init__(self):
        """Represents a music queue"""
        self.normal = []
        self.shuffled = []
        self.looping = []

    def loop(self, *, nowplaying):
        """Enables or disables looping"""
        if not self.looping:
            self.looping = list(self.visible)
            self.looping.insert(0, nowplaying)
            if not self.visible:
                self.visible = list(self.looping)
        else:
            self.looping = []

        return bool(self.looping)

    def shuffle(self):
        """Enables or disables shuffling"""
        if not self.shuffled:
            self.shuffled = list(self.visible)
            random.shuffle(self.shuffled)
        else:
            self.shuffled = []

        return bool(self.shuffled)

    def clear(self):
        """Clears all playlists"""
        self.normal = []
        self.shuffled = []
        self.looping = []

    def get_next_song(self):
        """Gets the next song in the queue, accounts for shuffled queues"""
        try:
            song = None
            song = self.normal[0]
            song = self.shuffled[0]
        except IndexError:
            pass

        return song

    def remove(self, obj):
        """Removes a song from the list, accounts for shuffled and looping queues"""
        self.normal.remove(obj)
        if self.shuffled:
            self.shuffled.remove(obj)

        if not self.normal:
            self.normal = list(self.looping)
            self.shuffled = list(self.looping)

    def add(self, obj):
        """Adds a song to the queue, accounts for shuffled and looping queues"""
        self.normal.append(obj)
        if self.shuffled:
            self.shuffled.append(obj)
        if self.looping:
            self.looping.append(obj)

    @property
    def visible(self):
        """Returns the queue which the user will see"""
        if self.shuffled:
            return self.shuffled
        else:
            return self.normal

    @visible.setter
    def visible(self, new)
        """Changes the queue, and changes the shuffled queue if necessary"""
        if self.shuffled:
            self.shuffled = new
        self.normal = new


class VoiceState:
    def __init__(self, bot):
        """Represents a voice connection to a guild"""
        self.bot = bot
        self.current = None
        self.voice = None
        self.play_next_song = asyncio.Event()
        self.queue = MusicQueue()
        self.music_player = self.bot.loop.create_task(self.music_player_task())
        self.allow_batch_jobs = True
        self.batch_job = False

    def is_playing(self):
        """Shows you if the bot is playing or not, returns boolean"""
        if self.voice is None:
            return False
        return self.voice.is_playing()

    def add_song_to_playlist(self, song, batch_job=False, *, context):
        """Adds a song to the playlist"""
        if batch_job:
            self.batch_job = True
            if not self.allow_batch_jobs:
                self.allow_batch_jobs = True
                return False

        song.channel = context.channel
        song.requester = context.author
        self.queue.add(song)
        if self.current is None:
            self.play_next_song.set()
        return True

    def toggle_next_song(self, error):
        """Toggles the next song by setting the play_next_song event"""
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def music_player_task(self):
        """Manages the voice interaction with the guild"""
        await self.play_next_song.wait()

        while self.queue.get_next_song() is not None:
            self.play_next_song.clear()

            self.current = self.queue.get_next_song()
            # await self.current.channel.send(f"Now playing {self.current}")
            await self.current.download()
            self.queue.remove(self.current)
            self.voice.play(self.current.source, after=self.toggle_next_song)

            await self.play_next_song.wait()

        await self.current.channel.send("Queue concluded.")
        self.current = None
        self.play_next_song.clear()
        self.music_player = self.bot.loop.create_task(self.music_player_task())

    async def join_voice_channel(self, voice_channel):
        """Joins a voice channel, returns discord.VoiceClient object"""
        if self.voice is not None:
            return await self.voice.move_to(voice_channel)

        self.voice = await voice_channel.connect()
        return self.voice

    def shuffle(self):
        """Shuffles or unshuffles the queue"""
        if self.queue.visible:
            return self.queue.shuffle()
        else:
            raise QueueEmpty("Can't shuffle when the queue is empty")

    def loop(self):
        """Enables or disbales looping of the queue"""
        if self.queue.visible or self.current:
            return self.queue.loop(nowplaying=self.current)
        else:
            raise QueueEmpty("Can't loop when the queue is empty")

    def skip(self):
        """Skips the song by stopping the current song"""
        if self.is_playing():
            self.voice.stop()
            return True

    def stop(self):
        if self.is_playing():
            """Stops the bot by skipping the song and clearing the queue"""
            if self.batch_job:
                self.allow_batch_jobs = False  # stop any ongoing batch jobs
            self.queue.clear()
            self.voice.stop()
            return True


class Music:
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}
        self.youtube = YouTube(self.bot.loop)

    def get_voice_state(self, guild):
        """Gets the VoiceState object associated with the guild"""
        state = self.voice_states.get(guild)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[guild] = state
        return state

    @commands.command()
    @commands.guild_only()
    async def spotify(self, ctx, *, query="Today's Top Hits"):
        """Searches Spotify's playlists to unpack (default: Today's Top Hits)"""
        if ctx.author.voice is None:
            raise discord.ClientException("You aren't in a voice channel")

        message = await ctx.send(f"Searching Spotify for `{query}`...")
        playlist = SpotifyPlaylist.from_file(query, loop=self.bot.loop)

        await message.edit(content=f"Should I add `{playlist}` to the queue? Or would you prefer the playlist url?")
        await message.add_reaction("\U00002705")  # check mark
        await message.add_reaction("\U0000274E")  # cross mark
        await message.add_reaction("\U0001F517")  # link emoji

        def check(reaction, user):
            """Checks whether the user reacted and whether the reaction was valid"""
            if user == ctx.author:
                return str(reaction) in ("\U00002705", "\U0000274E", "\U0001F517")  # cross or check mark or link
            return False

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("User failed to respond in 30 seconds")
        finally:
            await message.delete()

        if str(reaction) == "\U0000274E":  # if the user reacted with a cross mark (i.e. no)
            return
        elif str(reaction) == "\U0001F517":  # if the user reacted with link (i.e. url)
            match = re.search(r"https:\/\/api\.spotify\.com\/v1\/users\/(.*?)\/playlists\/(.*?)$",
                              playlist.data.get("href"))
            user_id, playlist_id = match.group(1), match.group(2)
            return await ctx.send(f"https://open.spotify.com/user/{user_id}/playlist/{playlist_id}")

        message = await ctx.send(f"Unpacking `{playlist}`...")

        state = self.get_voice_state(ctx.guild)
        await state.join_voice_channel(ctx.author.voice.channel)
        async for song in playlist.songs():  # unpack the songs into the queue as a batch job
            success = state.add_song_to_playlist(song, context=ctx, batch_job=True)
            if not success:
                break
        await message.edit(content=f"`{playlist}` has been unpacked")

    @commands.command()
    @commands.guild_only()
    async def play(self, ctx, *, query):
        """Streams from a url or search query (almost anything youtube_dl supports)"""
        if ctx.author.voice is None:
            return await ctx.send("You aren't in a voice channel")

        youtube_url = self.youtube.is_video_url(query)
        if youtube_url:
            song = await YouTubeVideo.from_url(youtube_url, loop=self.bot.loop)
        else:
            song = await self.youtube.search(query)

        state = self.get_voice_state(ctx.guild)
        await state.join_voice_channel(ctx.author.voice.channel)
        state.add_song_to_playlist(song, context=ctx)

        await ctx.send(f"{song} has been added to the queue")

    @commands.command(aliases=["np"])
    @commands.guild_only()
    async def nowplaying(self, ctx):
        """Shows the currently playing song"""
        state = self.get_voice_state(ctx.guild)
        if state.current is None:
            raise MusicNotPlaying("Can't show now playing when nothing is being played")
        await ctx.send(embed=state.current.embed)

    @commands.command(aliases=["q"])
    @commands.guild_only()
    async def queue(self, ctx, page: int=1):
        """Shows the queue"""
        state = self.get_voice_state(ctx.guild)
        if state.current is None:
            raise QueueEmpty("The queue is empty and nothing is being played")

        queue = state.queue.visible
        pages = math.ceil(len(queue) / 10)
        queue_embed = discord.Embed(title="Now Playing",
                                    description=state.current.title)
        queue_embed.set_thumbnail(url=state.current.thumbnail)

        if 0 < page <= pages:
            offset = 10 * (page - 1)
            view = queue[offset:offset + 10]
            song_queue = "\n".join("**{}**. {}".format(pos + offset + 1, song.title)
                                   for pos, song in enumerate(view))
            queue_embed.add_field(name="Song Queue", value=song_queue)
        elif page != 1:
            raise IndexError(f"Please request a page within the range 1-{pages}")

        await ctx.send(embed=queue_embed)

    @commands.command()
    @commands.guild_only()
    async def shuffle(self, ctx):
        """Shuffles or unshuffles the queue"""
        state = self.get_voice_state(ctx.guild)
        if state.shuffle():
            await ctx.send("The queue is now shuffled")
        else:
            await ctx.send("The queue has been unshuffled")

    @commands.command()
    @commands.guild_only()
    async def loop(self, ctx):
        state = self.get_voice_state(ctx.guild)
        if state.loop():
            await ctx.send("The queue will now loop")
        else:
            await ctx.send("The queue will no longer loopw")

    @commands.command()
    @commands.guild_only()
    async def skip(self, ctx):
        """Skips the current playing song"""
        state = self.get_voice_state(ctx.guild)
        if state.skip():
            await ctx.send("Skipping...")
        else:
            raise MusicNotPlaying("Can't skip song when music isn't playing")

    @commands.command()
    @commands.guild_only()
    async def stop(self, ctx):
        """Stops the music"""
        state = self.get_voice_state(ctx.guild)
        if not state.stop():
            raise MusicNotPlaying("The music has already stopped")


def setup(bot):
    bot.add_cog(Music(bot))
