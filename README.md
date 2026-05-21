# Discord Music Bot

A feature-rich Discord music bot that plays audio from YouTube, built with `discord.py` and `yt-dlp`.

## Features

- **Play** — Play audio from YouTube (single videos & playlists) via URL or search terms
- **Queue Management** — Add, remove, shuffle, and clear the queue
- **Playback Controls** — Pause, resume, skip, stop
- **Now Playing** — Rich embed with track info, thumbnail, and duration
- **Volume Control** — Adjustable 0–100%
- **Loop Modes** — Off, single track, or entire queue
- **Auto-disconnect** — Leaves channel when alone

## Requirements

- Python 3.10+
- [discord.py[voice]](https://discordpy.readthedocs.io/) >= 2.3
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) >= 2024.1
- [PyNaCl](https://pynacl.readthedocs.io/) >= 1.5
- [FFmpeg](https://ffmpeg.org/) (system dependency)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/discord-music-bot.git
cd discord-music-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg (Ubuntu/Debian)
sudo apt install ffmpeg

# Or on macOS
brew install ffmpeg
```

## Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your Discord bot token:
   ```
   DISCORD_TOKEN=your_bot_token_here
   COMMAND_PREFIX=!
   ```

3. **Get a Discord Bot Token:**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application → Bot → Add Bot
   - Copy the token
   - Enable **Message Content Intent** in the Bot settings
   - Invite the bot to your server with `bot` and `applications.scopes` permissions

## Usage

```bash
python bot.py
```

### Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `!play <query>` | `!p` | Play a song or add to queue (URL or search) |
| `!skip` | `!s`, `!next` | Skip the current song |
| `!stop` | — | Stop playback, clear queue, and disconnect |
| `!pause` | — | Pause the current track |
| `!resume` | — | Resume a paused track |
| `!queue` | `!q` | Display the current queue |
| `!nowplaying` | `!np` | Show the currently playing track |
| `!volume <0-100>` | `!vol` | Set the playback volume |
| `!loop <off\|track\|queue>` | — | Set loop mode |
| `!shuffle` | — | Shuffle the queue |
| `!remove <index>` | — | Remove a track by position number |
| `!clear` | — | Clear the entire queue |
| `!disconnect` | `!dc`, `!leave` | Disconnect from voice channel |

## Project Structure

```
discord-music-bot/
├── bot.py              # Main bot source code
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## Architecture

- **`Track`** — Data class representing a single audio track (title, URL, duration, thumbnail, requester)
- **`GuildMusicState`** — Per-guild state (queue, current track, loop mode, volume)
- **`_playback_task`** — Async background task driving playback for each voice channel
- **Command handlers** — discord.py commands for all user-facing operations

## License

MIT
