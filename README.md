# groupchat-podcast

Convert iMessage group chats into podcast-style audio using ElevenLabs text-to-speech.

Each participant gets their own voice, messages are read in order, and the result is a single MP3 you can listen to on the go.

## Requirements

- **macOS** (reads directly from the iMessage database)
- **Python 3.9+**
- **ffmpeg** for audio processing
- **ElevenLabs API key** ([get one here](https://elevenlabs.io))
- **Full Disk Access** granted to your terminal app

## Installation

```bash
pip install groupchat-podcast
```

Or install from source:

```bash
git clone https://github.com/youruser/groupchat-podcast.git
cd groupchat-podcast
pip install .
```

## Quick Start

### Interactive mode (default)

```bash
groupchat-podcast
```

The tool walks you through selecting a group chat, date range, and voice assignments.

### With flags

```bash
groupchat-podcast \
  --chat-id 42 \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  -o january-recap.mp3
```

Any flags you omit will fall back to interactive prompts.

## CLI Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--db-path` | Path to iMessage `chat.db` | `~/Library/Messages/chat.db` |
| `--chat-id` | Group chat ID (skips selection) | Interactive |
| `--start-date` | Start date (`YYYY-MM-DD`) | Interactive |
| `--end-date` | End date (`YYYY-MM-DD`) | Interactive |
| `-o`, `--output` | Output MP3 file path | `podcast_YYYYMMDD_HHMMSS.mp3` |
| `--version` | Print version and exit | |

Run `groupchat-podcast --help` for full details.

## Setup

### Full Disk Access

macOS restricts access to `~/Library/Messages/chat.db`. You need to grant Full Disk Access to whichever terminal app you use:

1. Open **System Settings > Privacy & Security > Full Disk Access**
2. Add your terminal app (Terminal, iTerm2, etc.)
3. Restart your terminal

### ffmpeg

```bash
brew install ffmpeg
```

### ElevenLabs API Key

Set the `ELEVENLABS_API_KEY` environment variable, or create a `.env` file:

```bash
ELEVENLABS_API_KEY=your-api-key-here
```

If not set, the tool will prompt you on each run.

## How It Works

1. Reads messages from your local iMessage database (nothing leaves your machine except text sent to ElevenLabs for TTS)
2. Filters by date range and strips reactions/tapbacks
3. Reorders threaded replies to appear after their parent message
4. Converts each message to speech using ElevenLabs with per-participant voices
5. Stitches audio segments with pauses into a single MP3

## Cost

ElevenLabs charges per character. The tool shows a cost estimate before generating so you can review before committing. Pricing varies by plan -- check [ElevenLabs pricing](https://elevenlabs.io/pricing) for current rates.

## Development

```bash
git clone https://github.com/youruser/groupchat-podcast.git
cd groupchat-podcast
pip install -e ".[dev]"
pytest
```

## License

MIT -- see [LICENSE](LICENSE).
