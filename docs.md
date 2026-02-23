# Noridoc: groupchat-podcast

Path: @/

### Overview

- CLI tool that converts iMessage group chat conversations into podcast-style audio using ElevenLabs TTS
- Supports both fully interactive mode (wizard-style prompts) and non-interactive mode via CLI flags (`--db-path`, `--chat-id`, `--start-date`, `--end-date`, `-o`)
- macOS-only: reads the local iMessage SQLite database (default `~/Library/Messages/chat.db`, configurable via `--db-path`)

### How it fits into the larger codebase

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Terminal                          │
│                              │                                   │
│                    groupchat-podcast CLI                         │
└─────────────────────────────────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   iMessage DB   │  │  ElevenLabs API │  │   Local FS      │
│   (read-only)   │  │   (TTS)         │  │   (MP3 output)  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

- **Entry point**: `groupchat-podcast` CLI command (defined in `pyproject.toml` as `groupchat_podcast.cli:main`)
- **Data source**: Reads from macOS iMessage SQLite database (requires Full Disk Access permission)
- **External dependency**: ElevenLabs API for text-to-speech conversion
- **System dependency**: ffmpeg must be installed for audio processing via pydub

### Core Implementation

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Dual-mode interface: argparse flags for scripted use, beaupy interactive prompts as fallback. Handles chat selection (paginated `beaupy.select`), date range, voice assignment, progress display |
| `imessage.py` | SQLite extraction, timestamp conversion, thread reordering, attachment handling |
| `tts.py` | ElevenLabs SDK wrapper for TTS generation and voice search |
| `podcast.py` | Orchestration: extract -> TTS -> stitch; cost estimation |

### Things to Know

- **Mac timestamps**: iMessage uses nanoseconds since January 1, 2001 (not Unix epoch). See `convert_mac_timestamp()` in `imessage.py`
- **attributedBody parsing**: Newer macOS versions store message text in binary plist blobs. The parser splits on `NSString` marker, scans for a `+` byte pattern to locate the length and text, and falls back to older single/two-byte length prefix formats
- **Reaction filtering**: Messages with `associated_message_type != 0` are tapbacks/reactions and are excluded
- **Thread reordering**: Reply messages (those with `thread_originator_guid`) are repositioned to appear immediately after their parent message
- **Cost estimation**: Uses ElevenLabs pricing of approximately $0.30 per 1000 characters

### Project Structure

```
@/
├── pyproject.toml              # Dependencies, CLI entry point
├── src/groupchat_podcast/      # Main package
│   ├── cli.py                  # Interactive CLI
│   ├── imessage.py             # Database extraction
│   ├── tts.py                  # ElevenLabs wrapper
│   └── podcast.py              # Audio orchestration
├── tests/                      # Test suite with mock chat.db fixture
└── .env.example                # API key template
```

### System Requirements

- macOS (for iMessage database access)
- Full Disk Access permission for terminal app
- ffmpeg installed (for pydub audio processing)
- Python 3.9+
- ElevenLabs API key
- MIT licensed

Created and maintained by Nori.
