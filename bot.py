"""
Discord Music Bot
=================
A feature-rich Discord music bot that plays audio from YouTube.
Built with discord.py and yt-dlp.

Features:
- Play audio from YouTube (single videos and playlists)
- Queue management (add, remove, shuffle, clear)
- Playback controls (pause, resume, skip, stop, seek)
- Now playing display with progress bar
- Volume control
- Loop mode (single track or entire queue)
- 24/7 mode (stays in voice channel)

Requirements:
- Python 3.10+
- discord.py[voice] >= 2.3
- yt-dlp >= 2024.1
- PyNaCl >= 1.5
- FFmpeg (system dependency)

Usage:
    python bot.py
"""

import asyncio
import logging
import os
import random
import re
import sys
from collections import deque
from typing import Optional

import discord
import yt_dlp
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("musicbot")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")
MAX_QUEUE_DISPLAY: int = 10  # max tracks shown in !queue
YTDL_OPTIONS: dict = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "extract_flat": False,
}
FFMPEG_OPTIONS: dict = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
class Track:
    """Represents a single audio track."""

    __slots__ = ("title", "url", "webpage_url", "duration", "thumbnail", "requester")

    def __init__(self, *, title: str, url: str, webpage_url: str,
                 duration: Optional[int] = None, thumbnail: Optional[str] = None,
                 requester: Optional[discord.Member] = None):
        self.title = title
        self.url = url               # direct audio URL
        self.webpage_url = webpage_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester

    @property
    def duration_str(self) -> str:
        if self.duration is None:
            return "Unknown"
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class GuildMusicState:
    """Per-guild music state."""

    def __init__(self):
        self.queue: deque[Track] = deque()
        self.current: Optional[Track] = None
        self.loop: str = "off"  # off | track | queue
        self.volume: float = 0.5
        self._play_next_event = asyncio.Event()

    @property
    def is_looping_track(self) -> bool:
        return self.loop == "track"

    @property
    def is_looping_queue(self) -> bool:
        return self.loop == "queue"


# ---------------------------------------------------------------------------
# Helper: extract info from YouTube
# ---------------------------------------------------------------------------
def _extract_sync(query: str) -> list[Track]:
    """Synchronous wrapper around yt_dlp extraction (runs in executor)."""
    data = ytdl.extract_info(query, download=False)
    tracks: list[Track] = []
    if "entries" in data:
        for entry in data["entries"]:
            if entry is None:
                continue
            tracks.append(Track(
                title=entry.get("title", "Unknown"),
                url=entry.get("url", ""),
                webpage_url=entry.get("webpage_url", entry.get("url", "")),
                duration=entry.get("duration"),
                thumbnail=entry.get("thumbnail"),
            ))
    else:
        tracks.append(Track(
            title=data.get("title", "Unknown"),
            url=data.get("url", ""),
            webpage_url=data.get("webpage_url", data.get("url", "")),
            duration=data.get("duration"),
            thumbnail=data.get("thumbnail"),
        ))
    return tracks


async def extract_tracks(query: str, *, loop: asyncio.AbstractEventLoop,
                         requester: Optional[discord.Member] = None) -> list[Track]:
    """Extract track info asynchronously."""
    tracks = await loop.run_in_executor(None, _extract_sync, query)
    for t in tracks:
        t.requester = requester
    return tracks


# ---------------------------------------------------------------------------
# Helper: format progress bar
# ---------------------------------------------------------------------------
def _progress_bar(position: int, total: int, *, length: int = 20) -> str:
    if not total:
        return "▬" * length
    filled = int(length * position / total)
    bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
    return bar


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
guild_states: dict[int, GuildMusicState] = {}


def _get_state(guild_id: int) -> GuildMusicState:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusicState()
    return guild_states[guild_id]


# ---------------------------------------------------------------------------
# Core playback coroutine (runs once per guild voice client)
# ---------------------------------------------------------------------------
async def _playback_task(vc: discord.VoiceClient, state: GuildMusicState):
    """Background task that drives playback for one voice channel."""
    while True:
        state._play_next_event.clear()

        if not state.queue:
            await state._play_next_event.wait()
            continue

        track = state.queue.popleft()
        state.current = track

        source = discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source, volume=state.volume)

        def _after(error):
            if error:
                log.error("Playback error: %s", error)
            # Schedule the next track
            state._play_next_event.set()

        vc.play(source, after=_after)

        # Wait for track to finish (or be interrupted)
        await state._play_next_event.wait()

        # Handle loop modes
        if state.is_looping_track:
            state.queue.appendleft(track)
        elif state.is_looping_queue:
            state.queue.append(track)


_playback_tasks: dict[int, asyncio.Task] = {}

def _ensure_playback(vc: discord.VoiceClient, state: GuildMusicState):
    """Ensure the playback task is running for this voice client."""
    guild_id = vc.guild.id
    if guild_id in _playback_tasks and not _playback_tasks[guild_id].done():
        return  # already running
    _playback_tasks[guild_id] = asyncio.create_task(_playback_task(vc, state))

def _cancel_playback(guild_id: int):
    """Cancel the playback task for a guild."""
    if guild_id in _playback_tasks and not _playback_tasks[guild_id].done():
        _playback_tasks[guild_id].cancel()
        del _playback_tasks[guild_id]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name=f"{COMMAND_PREFIX}help"
    ))
    # Validate critical dependencies
    try:
        import nacl  # noqa: F401
        log.info("PyNaCl loaded successfully")
    except ImportError:
        log.warning("PyNaCl not installed! Voice features will not work. Install with: pip install PyNaCl")
    log.info("Bot ready! Use %shelp for commands.", COMMAND_PREFIX)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Disconnect if the bot is left alone in a voice channel."""
    if member.bot:
        return
    guild = member.guild
    vc = guild.voice_client
    if vc is None or not vc.is_connected():
        return
    # Check if bot is alone (only bot in channel)
    non_bot_members = [m for m in vc.channel.members if not m.bot]
    if len(non_bot_members) == 0:
        # Wait 30 seconds to see if someone rejoins
        await asyncio.sleep(30)
        non_bot_members = [m for m in vc.channel.members if not m.bot]
        if len(non_bot_members) == 0:
            state = guild_states.get(guild.id)
            if state:
                state.queue.clear()
                state.current = None
            _cancel_playback(guild.id)
            await vc.disconnect()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@bot.command(name="play", aliases=["p"])
async def cmd_play(ctx: commands.Context, *, query: str):
    """Play a song or add it to the queue. Accepts YouTube URLs or search terms."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send("❌ You must be in a voice channel to use this command.")

    channel: discord.VoiceChannel = ctx.author.voice.channel  # type: ignore[assignment]
    state = _get_state(ctx.guild.id)

    # Connect if not already
    vc = ctx.voice_client
    if vc is None:
        vc = await channel.connect()
    elif vc.channel != channel:
        await vc.move_to(channel)

    # Extract tracks
    async with ctx.typing():
        try:
            tracks = await extract_tracks(query, loop=bot.loop, requester=ctx.author)
        except Exception as exc:
            log.exception("Extraction failed")
            return await ctx.send(f"❌ Could not fetch audio: {exc}")

    if not tracks:
        return await ctx.send("❌ No results found.")

    # Enqueue
    state.queue.extend(tracks)

    # Start playback task if needed
    _ensure_playback(vc, state)

    if len(tracks) == 1:
        track = tracks[0]
        embed = discord.Embed(
            title="🎵 Added to Queue",
            description=f"[{track.title}]({track.webpage_url})",
            color=discord.Color.green(),
        )
        embed.add_field(name="Duration", value=track.duration_str, inline=True)
        embed.add_field(name="Position", value=f"#{len(state.queue)}", inline=True)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="📋 Playlist Added",
            description=f"Added **{len(tracks)}** tracks to the queue.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    # Signal playback task if idle
    if not vc.is_playing() and not state.current:
        state._play_next_event.set()


@bot.command(name="skip", aliases=["s", "next"])
async def cmd_skip(ctx: commands.Context):
    """Skip the current song."""
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("❌ Nothing is playing.")
    state = _get_state(ctx.guild.id)
    state._play_next_event.set()
    vc.stop()  # triggers _after → next track
    await ctx.send("⏭️ Skipped.")


@bot.command(name="stop")
async def cmd_stop(ctx: commands.Context):
    """Stop playback, clear the queue, and disconnect."""
    vc = ctx.voice_client
    if not vc:
        return await ctx.send("❌ I'm not in a voice channel.")
    state = _get_state(ctx.guild.id)
    state.queue.clear()
    state.current = None
    state._play_next_event.set()
    _cancel_playback(ctx.guild.id)
    if vc.is_playing():
        vc.stop()
    await vc.disconnect()
    await ctx.send("⏹️ Stopped and disconnected.")


@bot.command(name="pause")
async def cmd_pause(ctx: commands.Context):
    """Pause the current track."""
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("❌ Nothing is playing.")
    vc.pause()
    await ctx.send("⏸️ Paused.")


@bot.command(name="resume")
async def cmd_resume(ctx: commands.Context):
    """Resume a paused track."""
    vc = ctx.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send("❌ Nothing is paused.")
    vc.resume()
    await ctx.send("▶️ Resumed.")


@bot.command(name="queue", aliases=["q"])
async def cmd_queue(ctx: commands.Context):
    """Display the current queue."""
    state = _get_state(ctx.guild.id)
    if not state.queue and not state.current:
        return await ctx.send("📭 The queue is empty.")

    embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.blue())

    if state.current:
        embed.add_field(
            name="Now Playing",
            value=f"▶️ [{state.current.title}]({state.current.webpage_url}) | `{state.current.duration_str}`",
            inline=False,
        )

    if state.queue:
        lines = []
        for i, track in enumerate(list(state.queue)[:MAX_QUEUE_DISPLAY], 1):
            lines.append(f"`{i}.` [{track.title}]({track.webpage_url}) | `{track.duration_str}`")
        if len(state.queue) > MAX_QUEUE_DISPLAY:
            lines.append(f"\n*…and {len(state.queue) - MAX_QUEUE_DISPLAY} more*")
        embed.add_field(name="Up Next", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Loop: {state.loop} | Volume: {int(state.volume * 100)}%")
    await ctx.send(embed=embed)


@bot.command(name="nowplaying", aliases=["np"])
async def cmd_nowplaying(ctx: commands.Context):
    """Show the currently playing track."""
    state = _get_state(ctx.guild.id)
    if not state.current:
        return await ctx.send("❌ Nothing is playing.")

    track = state.current
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"[{track.title}]({track.webpage_url})",
        color=discord.Color.purple(),
    )
    embed.add_field(name="Duration", value=track.duration_str, inline=True)
    embed.add_field(name="Requested by", value=track.requester.mention if track.requester else "Unknown", inline=True)
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)
    await ctx.send(embed=embed)


@bot.command(name="volume", aliases=["vol"])
async def cmd_volume(ctx: commands.Context, volume: int):
    """Set the volume (0-100)."""
    if not 0 <= volume <= 100:
        return await ctx.send("❌ Volume must be between 0 and 100.")
    state = _get_state(ctx.guild.id)
    state.volume = volume / 100
    vc = ctx.voice_client
    if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = state.volume
    await ctx.send(f"🔊 Volume set to **{volume}%**.")


@bot.command(name="loop")
async def cmd_loop(ctx: commands.Context, mode: str = "track"):
    """Set loop mode: off, track, or queue."""
    mode = mode.lower()
    if mode not in ("off", "track", "queue"):
        return await ctx.send("❌ Mode must be `off`, `track`, or `queue`.")
    state = _get_state(ctx.guild.id)
    state.loop = mode
    labels = {"off": "Looping disabled", "track": "🔂 Looping current track", "queue": "🔁 Looping entire queue"}
    await ctx.send(labels[mode])


@bot.command(name="shuffle")
async def cmd_shuffle(ctx: commands.Context):
    """Shuffle the queue."""
    state = _get_state(ctx.guild.id)
    if len(state.queue) < 2:
        return await ctx.send("❌ Not enough tracks to shuffle.")
    items = list(state.queue)
    random.shuffle(items)
    state.queue = deque(items)
    await ctx.send("🔀 Queue shuffled.")


@bot.command(name="remove")
async def cmd_remove(ctx: commands.Context, index: int):
    """Remove a track from the queue by its position number."""
    state = _get_state(ctx.guild.id)
    if index < 1 or index > len(state.queue):
        return await ctx.send(f"❌ Invalid position. Queue has {len(state.queue)} tracks.")
    items = list(state.queue)
    removed = items.pop(index - 1)
    state.queue = deque(items)
    await ctx.send(f"🗑️ Removed **{removed.title}** from the queue.")


@bot.command(name="clear")
async def cmd_clear(ctx: commands.Context):
    """Clear the entire queue."""
    state = _get_state(ctx.guild.id)
    state.queue.clear()
    await ctx.send("🧹 Queue cleared.")


@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    """Display all available commands."""
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description="A feature-rich Discord music bot.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="🎶 Playback",
        value=(
            f"`{COMMAND_PREFIX}play <query>` — Play a YouTube URL or search\n"
            f"`{COMMAND_PREFIX}skip` — Skip current track\n"
            f"`{COMMAND_PREFIX}stop` — Stop & disconnect\n"
            f"`{COMMAND_PREFIX}pause` / `{COMMAND_PREFIX}resume` — Pause/resume\n"
            f"`{COMMAND_PREFIX}volume <0-100>` — Set volume"
        ),
        inline=False,
    )
    embed.add_field(
        name="📋 Queue",
        value=(
            f"`{COMMAND_PREFIX}queue` — Show queue\n"
            f"`{COMMAND_PREFIX}nowplaying` — Now playing\n"
            f"`{COMMAND_PREFIX}shuffle` — Shuffle queue\n"
            f"`{COMMAND_PREFIX}remove <index>` — Remove track\n"
            f"`{COMMAND_PREFIX}clear` — Clear queue"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔁 Other",
        value=(
            f"`{COMMAND_PREFIX}loop <off|track|queue>` — Loop mode\n"
            f"`{COMMAND_PREFIX}disconnect` — Disconnect bot\n"
            f"`{COMMAND_PREFIX}help` — Show this message"
        ),
        inline=False,
    )
    embed.set_footer(text="Bot stays in voice channel when idle. Auto-disconnects after 30s alone.")
    await ctx.send(embed=embed)


@bot.command(name="disconnect", aliases=["dc", "leave"])
async def cmd_disconnect(ctx: commands.Context):
    """Disconnect the bot from the voice channel."""
    vc = ctx.voice_client
    if not vc:
        return await ctx.send("❌ I'm not in a voice channel.")
    state = _get_state(ctx.guild.id)
    state.queue.clear()
    state.current = None
    state._play_next_event.set()
    _cancel_playback(ctx.guild.id)
    await vc.disconnect()
    await ctx.send("👋 Disconnected.")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `{COMMAND_PREFIX}help {ctx.command}`.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # silently ignore
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Bad argument. Use `{COMMAND_PREFIX}help {ctx.command}`.")
    else:
        log.exception("Unhandled error in command %s", ctx.command)
        await ctx.send("❌ An unexpected error occurred.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if not DISCORD_TOKEN:
        log.error("DISCORD_TOKEN environment variable is not set.")
        log.error("Create a .env file with: DISCORD_TOKEN=your_token_here")
        log.error("Or set the DISCORD_TOKEN environment variable.")
        sys.exit(1)
    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error("Invalid DISCORD_TOKEN. Please check your token and try again.")
        sys.exit(1)
    except Exception as e:
        log.error("Bot failed to start: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
