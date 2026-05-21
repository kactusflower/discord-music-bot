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
git clone https://github.com/kactusflower/discord-music-bot.git
cd discord-music-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (includes python-dotenv for .env file support)
pip install -r requirements.txt

# Install FFmpeg (Ubuntu/Debian)
sudo apt install ffmpeg

# Or on macOS
brew install ffmpeg
```

## Configuration

### Step 1: Create your `.env` file

Copy the example environment file and add your token:
```bash
cp .env.example .env
```

Edit `.env` and add your Discord bot token:
```
DISCORD_TOKEN=your_bot_token_here
COMMAND_PREFIX=!
```

> **Note:** The bot now automatically loads the `.env` file via `python-dotenv`. No need to manually source it.

### Step 2: Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → give it a name
3. Go to the **Bot** tab → click **Add Bot**
4. Under **Privileged Gateway Intents**, enable:
   - **Message Content Intent** (required for commands)
5. Click **Reset Token** and copy your token
6. Paste the token into your `.env` file

### Step 3: Invite the bot to your server

1. Go to **OAuth2** → **URL Generator**
2. Under **Scopes**, select `bot` and `applications.commands`
3. Under **Bot Permissions**, select:
   - Send Messages
   - Read Messages/View Channels
   - Connect (Voice)
   - Speak (Voice)
4. Copy the generated URL and open it in your browser
5. Select your server and authorize

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

## Troubleshooting

### Bot won't start
- **"No module named 'discord'"**: Run `pip install -r requirements.txt`
- **"DISCORD_TOKEN environment variable is not set"**: Make sure your `.env` file exists in the same directory as `bot.py` and contains `DISCORD_TOKEN=your_token`. The bot loads `.env` automatically via `python-dotenv`.
- **"No module named 'dotenv'"**: Run `pip install python-dotenv` or `pip install -r requirements.txt`
- **401 Unauthorized**: Your Discord bot token is invalid. Regenerate it in the Discord Developer Portal
- **SSL errors on Linux**: You may need to install `libssl-dev` (`sudo apt install libssl-dev`)
- **PyNaCl not found**: Run `pip install PyNaCl` (required for voice features)

### Bot connects but no audio
- Ensure FFmpeg is installed: `ffmpeg -version`
- Check that the bot has `Connect` and `Speak` permissions in the voice channel
- Some YouTube videos may be region-restricted or age-restricted

## License

MIT
