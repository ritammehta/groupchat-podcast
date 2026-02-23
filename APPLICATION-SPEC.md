# groupchat-podcast — Application Specification

## What It Does

Converts iMessage group chat conversations into podcast-style audio files (MP3). Each participant gets a unique ElevenLabs TTS voice, messages are read chronologically, and the result is a single stitched MP3.

## Target User

Non-technical Mac user who has iMessage group chats and wants to listen to them as audio. They may have never used a terminal before.

## Platform Constraints

- **macOS only** — reads directly from `~/Library/Messages/chat.db`
- Requires **Full Disk Access** granted to the terminal app
- Requires **ffmpeg** installed (typically via Homebrew)
- Requires an **ElevenLabs API key** (paid service, ~$0.30/1000 chars)
- **Python 3.9+**

## Architecture

```
CLI (cli.py) — entry point, interactive prompts + argparse flags
    ├── preflight.py — prerequisite checks (macOS, ffmpeg, FDA, API key)
    ├── imessage.py — SQLite extraction from chat.db
    │     ├── Mac timestamp conversion (nanoseconds since 2001-01-01)
    │     ├── attributedBody binary plist parsing
    │     ├── Reaction/tapback filtering
    │     ├── Thread reordering (replies after parent)
    │     ├── Attachment placeholder text
    │     └── URL-to-title resolution (HTTP fetches)
    ├── contacts.py — macOS AddressBook DB → name resolution
    ├── tts.py — ElevenLabs SDK wrapper
    │     ├── Text preprocessing (emoji strip, abbreviation expand, caps normalize)
    │     └── Voice search/get/generate
    └── podcast.py — orchestration
          ├── Consecutive message merging (same sender, within 5 min)
          ├── Audio generation per message
          ├── Audio stitching with pauses (pydub/ffmpeg)
          └── Cost estimation
```

## Modes of Operation

### Interactive mode (default)
```bash
groupchat-podcast
```
Walks through: API key → chat selection (paginated) → date range → voice assignment → cost estimate → generate.

### Non-interactive mode (CLI flags)
```bash
groupchat-podcast --db-path ~/Library/Messages/chat.db --chat-id 42 \
  --start-date 2024-01-01 --end-date 2024-01-31 -o output.mp3
```
Any omitted flags fall back to interactive prompts.

## CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--db-path` | str | `~/Library/Messages/chat.db` | Path to iMessage database |
| `--chat-id` | int | Interactive | Group chat ROWID |
| `--start-date` | str | Interactive | `YYYY-MM-DD` format |
| `--end-date` | str | Interactive | `YYYY-MM-DD` format |
| `-o` / `--output` | str | `podcast_YYYYMMDD_HHMMSS.mp3` | Output file path |
| `--version` | flag | — | Print version and exit |

## Key Technical Details

- **Mac timestamps**: Nanoseconds since 2001-01-01 (not Unix epoch)
- **attributedBody**: Binary plist containing NSAttributedString; parsed by scanning for `NSString` marker + `+` byte pattern
- **Reactions excluded**: `associated_message_type != 0`
- **Thread reordering**: Messages with `thread_originator_guid` moved after parent
- **URL reformatting**: URLs replaced with `og:title` or `<title>` from the page (HTTP fetch, 5s timeout, LRU cached)
- **Message merging**: Consecutive same-sender messages within 5 minutes joined with smart punctuation
- **TTS preprocessing**: Emoji removal, abbreviation expansion (idk→I don't know), caps normalization, repeated punctuation cleanup
- **Cost model**: ~$0.30 per 1000 characters (ElevenLabs Creator plan)
- **Preflight checks**: Verifies macOS platform, ffmpeg (PATH + Homebrew fallback), Full Disk Access (file probe), API key before starting
- **Error handling**: Top-level handler catches all exceptions; users never see Python tracebacks
- **Voice assignment**: Search-first flow — input treated as search query unless it looks like a voice ID (20+ alphanumeric chars)

## Dependencies

### Python packages
- `beaupy` — interactive terminal prompts (select, confirm, prompt)
- `elevenlabs` — TTS API client
- `pydub` — audio manipulation (requires ffmpeg)
- `python-dotenv` — .env file loading
- `rich` — terminal formatting (panels, progress bars, tables)

### System
- `ffmpeg` — audio encoding/decoding (pydub backend)

### Dev
- `pytest` + `pytest-mock`

## Test Suite

136 tests across 7 files:
- `test_cli.py` — argument parsing, main() flow, interactive prompts, friendly errors, voice assignment
- `test_contacts.py` — phone/email normalization, contact DB reading, CLI contact display
- `test_imessage.py` — message extraction, timestamp conversion, thread reordering
- `test_podcast.py` — message merging, audio stitching, cost estimation
- `test_tts.py` — text preprocessing, TTS client behavior
- `test_preflight.py` — platform, ffmpeg, disk access, API key checks

Fixture: `mock_chat_db` creates an in-memory iMessage SQLite database with representative test data.
