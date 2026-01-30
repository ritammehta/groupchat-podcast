# Noridoc: groupchat_podcast

Path: @/src/groupchat_podcast

### Overview

- Core Python package for iMessage-to-podcast conversion
- Four modules: CLI interaction, iMessage extraction, TTS generation, and audio stitching
- Designed as a pipeline: extract messages -> generate audio per message -> stitch into single MP3

### How it fits into the larger codebase

- **Invoked by**: CLI entry point (`groupchat-podcast` command) calls `cli.main()`
- **Reads from**: macOS iMessage database at `~/Library/Messages/chat.db`
- **Calls out to**: ElevenLabs API via the elevenlabs SDK
- **Writes to**: Local filesystem (MP3 output file)

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

1. **CLI (`cli.py`)**: Wizard collects user choices (chat, dates, voices, output path)
2. **Extraction (`imessage.py`)**: Queries SQLite, converts timestamps, parses attributedBody blobs, reorders threads
3. **TTS (`tts.py`)**: Converts each message text to MP3 bytes via ElevenLabs
4. **Stitching (`podcast.py`)**: Concatenates MP3 segments with configurable silence gaps

#### Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `GroupChat` | imessage.py | Dataclass for chat metadata (id, name, participants) |
| `Message` | imessage.py | Dataclass for extracted message (sender, text, timestamp, thread info) |
| `Voice` | tts.py | Dataclass for ElevenLabs voice metadata |
| `TTSClient` | tts.py | Wrapper around ElevenLabs SDK with `generate()`, `search_voices()`, `get_voice()` |
| `PodcastGenerator` | podcast.py | Orchestrates full pipeline with progress callbacks |

#### Key Functions

| Function | Module | Purpose |
|----------|--------|---------|
| `list_group_chats()` | imessage.py | Returns all group chats (>1 participant) from database |
| `extract_messages()` | imessage.py | Extracts messages for a chat within date range |
| `parse_attributed_body()` | imessage.py | Parses binary plist blob to extract text |
| `stitch_audio()` | podcast.py | Concatenates MP3 files with silence between |

### Things to Know

#### iMessage Database Quirks

- **Timestamp format**: Nanoseconds since January 1, 2001 (`MAC_EPOCH`). Use `convert_mac_timestamp()` and `datetime_to_mac_timestamp()` for conversion
- **attributedBody**: Modern macOS stores message text in binary plist format. The parser splits on `NSString` marker and handles both 1-byte and 2-byte length prefixes (0x81 prefix indicates 2-byte length)
- **Reactions**: Filtered by `associated_message_type = 0` (non-zero values are tapbacks/reactions)
- **Thread replies**: Messages with `thread_originator_guid` are replies. `_reorder_threads()` moves them to appear immediately after their parent

#### Audio Generation

- **TTS model**: Uses `eleven_multilingual_v2` model with `mp3_44100_128` output format
- **Voice mapping**: `PodcastGenerator` accepts a `voice_map` dict mapping sender identifiers to ElevenLabs voice IDs. Use `_default` key for fallback voice
- **Temporary files**: During generation, individual message MP3s are written to a temp directory, then stitched together

#### Message Text Processing

- **Attachment placeholders**: Messages with attachments but no text get placeholder text based on MIME type (e.g., "Look at this photo")
- **URL reformatting**: URL-only messages are prefixed with "Hey, check this out:" for more natural speech
- **Empty message filtering**: Messages without text are skipped during podcast generation

#### Cost Estimation

- `PodcastGenerator.estimate_cost()` returns character count, message count, and estimated USD cost
- Pricing assumption: $0.30 per 1000 characters (ElevenLabs Creator plan)

Created and maintained by Nori.
