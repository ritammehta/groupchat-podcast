# Noridoc: groupchat_podcast

Path: @/src/groupchat_podcast

### Overview

- Core Python package for iMessage-to-podcast conversion
- Four modules: CLI interaction, iMessage extraction, TTS generation, and audio stitching
- Designed as a pipeline: extract messages -> generate audio per message -> stitch into single MP3

### How it fits into the larger codebase

- **Invoked by**: CLI entry point (`groupchat-podcast` command) calls `cli.main()`
- **Reads from**: macOS iMessage database (default `~/Library/Messages/chat.db`, overridable with `--db-path`)
- **Calls out to**: ElevenLabs API via the elevenlabs SDK
- **Writes to**: Local filesystem (MP3 output file)
- **Dual invocation modes**: Every step in `main()` checks for a CLI flag first and falls back to interactive prompts when the flag is absent

```
cli.py
   │
   ├──► imessage.py ──► SQLite (chat.db)
   │
   ├──► tts.py ──► ElevenLabs API
   │
   └──► podcast.py
           │
           ├──► imessage.extract_messages()
           ├──► tts.TTSClient.generate()
           └──► pydub (audio stitching)
```

### Core Implementation

#### Data Flow

1. **CLI (`cli.py`)**: `build_parser()` defines argparse flags; `main()` checks each flag and falls back to interactive prompts when absent. The entire `main()` body is wrapped in a `try/except KeyboardInterrupt` that exits with code 130
2. **Extraction (`imessage.py`)**: Queries SQLite, converts timestamps, parses attributedBody blobs, reorders threads. `list_group_chats()` now returns chats sorted by most recent message date
3. **TTS (`tts.py`)**: Converts each message text to MP3 bytes via ElevenLabs
4. **Stitching (`podcast.py`)**: Concatenates MP3 segments with configurable silence gaps

#### Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `GroupChat` | imessage.py | Dataclass for chat metadata (id, name, participants, `last_message_date`) |
| `Message` | imessage.py | Dataclass for extracted message (sender, text, timestamp, thread info) |
| `Voice` | tts.py | Dataclass for ElevenLabs voice metadata |
| `TTSClient` | tts.py | Wrapper around ElevenLabs SDK with `generate()`, `search_voices()`, `get_voice()` |
| `PodcastGenerator` | podcast.py | Orchestrates full pipeline with progress callbacks |

#### Key Functions

| Function | Module | Purpose |
|----------|--------|---------|
| `build_parser()` | cli.py | Constructs `argparse.ArgumentParser` with all CLI flags; all flags default to `None` |
| `list_group_chats()` | imessage.py | Returns all group chats (>1 participant) from database, sorted by most recent message |
| `extract_messages()` | imessage.py | Extracts messages for a chat within date range |
| `parse_attributed_body()` | imessage.py | Parses binary plist blob to extract text |
| `stitch_audio()` | podcast.py | Concatenates MP3 files with silence between |

### Things to Know

#### CLI Dual-Mode Pattern

- `main()` parses CLI args first via `build_parser().parse_args()`. For each step (db path, chat selection, date range, output path), it checks whether a flag was provided (`args.X is not None`) and only falls to the interactive prompt when the flag is absent
- `--db-path` uses `Path.expanduser()` so `~` paths work. Error messages differ depending on whether the path was user-provided or the default
- `--start-date` and `--end-date` must both be provided together; if either is absent, the interactive `get_date_range()` prompt is used instead
- `KeyboardInterrupt` is caught at the top level of `main()`, producing a clean exit with code 130 (Unix SIGINT convention)

#### beaupy Interactive Prompts

- All interactive prompts use the `beaupy` library (`beaupy.select`, `beaupy.prompt`, `beaupy.confirm`) instead of `rich.prompt.Prompt`/`rich.prompt.Confirm`. Rich is still used for display output (panels, progress bars, styled text)
- **None-check invariant**: beaupy returns `None` when the user presses Escape or Ctrl+C, rather than raising an exception. Every beaupy call site in `cli.py` checks `if result is None: raise KeyboardInterrupt` to preserve the centralized interrupt handling in `main()`
- `select_group_chat()` uses `beaupy.select()` with a `preprocessor` function that formats `GroupChat` objects into display strings, and `pagination=True` with a configurable `page_size` (default 10)
- `get_api_key()` uses `beaupy.prompt(secure=True)` for masked password input
- `get_date_range()` and `get_output_path()` use `beaupy.prompt(initial_value=...)` to pre-fill editable defaults (replaces `Prompt.ask(default=...)`)
- `show_cost_estimate()` and the ffmpeg check in `main()` use `beaupy.confirm(default_is_yes=...)` for yes/no confirmation

#### iMessage Database Quirks

- **Timestamp format**: Nanoseconds since January 1, 2001 (`MAC_EPOCH`). Use `convert_mac_timestamp()` and `datetime_to_mac_timestamp()` for conversion
- **attributedBody**: Modern macOS stores message text in binary plist format. The parser splits on `NSString` marker. The primary strategy scans for a `+` byte and reads the next byte as a length to extract text. If that fails, it falls back to older formats: 0x81 prefix for two-byte length, or a single byte < 128 for one-byte length
- **Reactions**: Filtered by `associated_message_type = 0` (non-zero values are tapbacks/reactions)
- **Thread replies**: Messages with `thread_originator_guid` are replies. `_reorder_threads()` moves them to appear immediately after their parent
- **Last message date**: `list_group_chats()` runs a separate query against `chat_message_join`/`message` to find `MAX(m.date)` per chat. This query is wrapped in `try/except sqlite3.OperationalError` because test databases may lack these tables

#### Audio Generation

- **TTS model**: Uses `eleven_multilingual_v2` model with `mp3_44100_128` output format
- **Voice mapping**: `PodcastGenerator` accepts a `voice_map` dict mapping sender identifiers to ElevenLabs voice IDs. Use `_default` key for fallback voice
- **Temporary files**: During generation, individual message MP3s are written to a temp directory, then stitched together

#### Message Text Processing

- **Attachment placeholders**: Messages with attachments but no text get placeholder text based on MIME type (e.g., "Look at this photo")
- **URL title resolution**: `_reformat_url_message()` replaces raw URLs with human-readable page titles so TTS reads naturally. `_fetch_url_title()` makes an HTTP request per URL (5-second timeout, first 64KB of HTML) and extracts `og:title` first (matching iMessage's link preview behavior), then falls back to `<title>` tag. If the fetch fails entirely, the domain name is used (stripped of `www.` prefix)
- **URL formatting by message type**: URL-only messages become `"Check out this link: {title}"`. Messages with mixed text and URLs replace each URL inline with `"this link: {title}"`
- **Network I/O during extraction**: Because `_reformat_url_message()` is called from `extract_messages()`, message extraction is no longer a purely offline operation. The CLI displays "Extracting messages and resolving link previews..." to indicate this
- **Empty message filtering**: Messages without text are skipped during podcast generation

#### Cost Estimation

- `PodcastGenerator.estimate_cost()` returns character count, message count, and estimated USD cost
- Pricing assumption: $0.30 per 1000 characters (ElevenLabs Creator plan)

Created and maintained by Nori.
