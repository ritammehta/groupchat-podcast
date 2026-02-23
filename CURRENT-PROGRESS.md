# Current Progress

## Completed Features

1. **Core iMessage extraction** — Reads chat.db, handles Mac timestamps, attributedBody parsing, reaction filtering, thread reordering, attachment placeholders
2. **ElevenLabs TTS integration** — Voice search, voice selection, audio generation with multilingual_v2 model
3. **Text preprocessing for TTS** — Emoji stripping, abbreviation expansion, caps normalization, punctuation cleanup
4. **URL-to-title resolution** — Replaces raw URLs with page titles for natural speech
5. **Message merging** — Consecutive same-sender messages within 5 min merged for natural flow
6. **Audio stitching** — pydub-based concatenation with configurable pauses
7. **Interactive CLI** — beaupy-based wizard: chat selection (paginated), date range, voice assignment, cost estimate confirmation
8. **CLI flags** — `--db-path`, `--chat-id`, `--start-date`, `--end-date`, `-o`/`--output`, `--version`
9. **macOS Contacts resolution** — Resolves phone/email handles to real names from AddressBook databases
10. **Cost estimation** — Character count and dollar estimate shown before generation
11. **Preflight prerequisite checks** — Checks macOS platform, ffmpeg (PATH + Homebrew paths), Full Disk Access (file probe on chat.db), and ElevenLabs API key. Reports ALL failures at once with Rich table and step-by-step fix instructions.
12. **Friendly error handling** — Top-level exception handler in main() catches PermissionError and generic exceptions, showing Rich Panel messages instead of Python tracebacks. Users never see stack traces.
13. **Search-first voice assignment** — Voice prompt treats input as a search query by default, presenting results in a beaupy.select picker. Only tries as voice ID if input is 20+ alphanumeric characters.
14. **Improved "no messages" UX** — When no messages found in date range, suggests trying a wider range.

## Test Coverage

- 136 passing tests across cli, contacts, imessage, podcast, tts, preflight modules
- Mock chat.db fixture with representative data

## What's Next

- Consider integrating preflight checks into the main() flow (currently a standalone module, not yet called from main)
- README improvements for non-technical users (installation walkthrough with screenshots)
- Consider a `--setup` flag that walks through prerequisite installation
