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
       ┌───────────┬───────────┼───────────────────┐
       ▼           ▼           ▼                   ▼
┌───────────┐ ┌──────────┐ ┌─────────────────┐ ┌─────────────┐
│ iMessage  │ │ Contacts │ │  ElevenLabs API │ │  Local FS   │
│ DB (r/o)  │ │ DB (r/o) │ │   (TTS)         │ │ (MP3 output)│
└───────────┘ └──────────┘ └─────────────────┘ └─────────────┘
```

- **Entry point**: `groupchat-podcast` CLI command (defined in `pyproject.toml` as `groupchat_podcast.cli:main`)
- **Data source**: Reads from macOS iMessage SQLite database (requires Full Disk Access permission)
- **Contacts resolution**: Optionally reads macOS AddressBook databases to resolve handle IDs to contact names (display-layer only)
- **External dependency**: ElevenLabs API for text-to-speech conversion
- **System dependency**: ffmpeg must be installed for audio processing via pydub

### Core Implementation

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Dual-mode interface: argparse flags for scripted use, beaupy interactive prompts as fallback. Calls `run_preflight()` before any interactive prompts to validate prerequisites (bypassed with `--skip-checks`). Handles chat selection, date range, voice assignment (search-first), contact resolution, progress display. Top-level error handler catches all exceptions and presents Rich Panel messages instead of Python tracebacks |
| `contacts.py` | Resolves iMessage handle IDs (phone numbers, emails) to macOS contact names via AddressBook SQLite databases |
| `imessage.py` | SQLite extraction, timestamp conversion, thread reordering, attachment handling, URL-to-title resolution (makes HTTP requests during extraction) |
| `tts.py` | ElevenLabs SDK wrapper for TTS generation and voice search; text preprocessing (emoji stripping, abbreviation expansion, caps normalization) for natural chat-to-speech |
| `podcast.py` | Orchestration: extract -> merge consecutive messages -> preprocess text -> TTS -> stitch; cost estimation |
| `preflight.py` | Prerequisite checker called automatically from `main()` at startup: validates macOS platform, ffmpeg installation, Full Disk Access, and ElevenLabs API key. Reports all failures at once via a Rich table with fix instructions |

### Things to Know

- **User-friendly error surface**: The CLI is designed so non-technical users never see a Python traceback. `main()` runs preflight checks automatically before any interactive prompts, so users see all prerequisite problems at once. The top-level exception handler catches `PermissionError` and generic `Exception` and renders Rich Panel messages with step-by-step fix instructions. Power users can bypass preflight with `--skip-checks`
- **Mac timestamps**: iMessage stores timestamps as nanoseconds since January 1, 2001 **in UTC** (not Unix epoch). The conversion layer in `imessage.py` translates between UTC Mac timestamps and naive local datetimes: `convert_mac_timestamp()` returns local time, and `datetime_to_mac_timestamp()` treats naive inputs as local time and converts to UTC before computing the Mac timestamp
- **attributedBody parsing**: Newer macOS versions store message text in binary plist blobs. The parser in `parse_attributed_body()` splits on the `NSString` marker, locates the `+` (0x2B) byte, then reads a variable-width integer length (Apple typedstream encoding: single byte for 0-127, 0x81 + 2-byte LE uint16 for 128-65535) and extracts that many bytes of UTF-8 text
- **Reaction filtering**: Messages with `associated_message_type != 0` are tapbacks/reactions and are excluded
- **Thread reordering**: Reply messages (those with `thread_originator_guid`) are repositioned to appear immediately after their parent message
- **Cost estimation**: Uses ElevenLabs pricing of approximately $0.30 per 1000 characters

### Project Structure

```
@/
├── pyproject.toml              # Dependencies, CLI entry point
├── src/groupchat_podcast/      # Main package
│   ├── cli.py                  # Interactive CLI
│   ├── contacts.py             # macOS Contacts resolution
│   ├── imessage.py             # Database extraction
│   ├── preflight.py            # Prerequisite checks
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
