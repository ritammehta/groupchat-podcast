# groupchat-podcast

Turn any iMessage group chat into a podcast. Each person in the chat gets their own AI-generated voice, and the whole conversation is stitched together into a single MP3 you can listen to like a podcast episode.

## What You Need

- A **Mac** (this reads directly from iMessage on your computer)
- **Python 3.9 or newer** ([how to check](https://www.python.org/downloads/))
- **ffmpeg** (a free audio tool — installation instructions below)
- An **ElevenLabs account** for the text-to-speech voices ([sign up here](https://elevenlabs.io))

## Installation

Open the Terminal app on your Mac and run:

```bash
git clone https://github.com/ritammehta/groupchat-podcast.git
cd groupchat-podcast
pip install .
```

### Installing ffmpeg

ffmpeg is a free tool that handles audio processing behind the scenes. Install it with [Homebrew](https://brew.sh):

```bash
brew install ffmpeg
```

If you don't have Homebrew, install it first by following the instructions at [brew.sh](https://brew.sh).

### Getting Your ElevenLabs API Key

1. Create an account at [elevenlabs.io](https://elevenlabs.io)
2. Go to your profile and copy your API key
3. Create a file called `.env` in the folder where you'll run the tool, and paste this in:

```
ELEVENLABS_API_KEY=your-api-key-here
```

If you skip this step, the tool will ask you for the key each time you run it.

### Granting Full Disk Access

macOS doesn't let apps read your messages by default. You need to give your Terminal permission:

1. Open **System Settings** > **Privacy & Security** > **Full Disk Access**
2. Click the **+** button and add your terminal app (Terminal, iTerm2, etc.)
3. Restart your terminal

## Usage

Just run:

```bash
groupchat-podcast
```

The tool walks you through everything step by step:

1. **Checks your setup** — makes sure ffmpeg is installed, your terminal has permission to read messages, and your API key works. If anything is missing, it tells you exactly how to fix it.
2. **Picks a group chat** — shows you a list of your group chats to choose from.
3. **Picks a date range** — asks what time period you want to cover (defaults to the current month).
4. **Assigns voices** — for each person in the chat, you search for and pick an ElevenLabs voice. You can type a name like "Rachel" to search, or paste a specific voice ID.
5. **Shows a cost estimate** — tells you how many characters will be converted to speech and the estimated cost, then asks you to confirm before spending anything.
6. **Generates the podcast** — converts each message to audio with the assigned voices and combines everything into one MP3 file.

### Skipping the Interactive Prompts

If you already know what you want, you can pass flags to skip some or all of the prompts:

```bash
groupchat-podcast \
  --chat-id 42 \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  -o january-recap.mp3
```

Any flags you leave out will fall back to the interactive prompts.

| Flag | What it does |
|------|-------------|
| `--chat-id` | Skip the chat selection screen by passing a chat ID directly |
| `--start-date` | Start date in `YYYY-MM-DD` format |
| `--end-date` | End date in `YYYY-MM-DD` format |
| `-o` / `--output` | Where to save the MP3 (defaults to `podcast_YYYYMMDD_HHMMSS.mp3`) |
| `--db-path` | Path to the iMessage database (you almost certainly don't need this) |
| `--skip-checks` | Skip the automatic setup checks |
| `--version` | Print the version number |

## How It Works Under the Hood

1. Reads messages from your Mac's local iMessage database — the only thing sent to the internet is the text of each message, which goes to ElevenLabs to generate audio.
2. Looks up phone numbers in your Mac's contacts so you see real names instead of numbers.
3. Filters out tapback reactions (likes, dislikes, etc.) so the podcast sounds natural.
4. Groups rapid-fire messages from the same person together so they sound like one thought.
5. Cleans up text for speech — expands abbreviations (e.g., "idk" becomes "I don't know"), removes emoji, and replaces links with the page title so the voice reads something meaningful instead of a raw URL.
6. Converts each message to speech using the ElevenLabs voice you assigned to that person.
7. Stitches all the audio clips together with short pauses between messages into a single MP3.

## Cost

ElevenLabs charges based on how many characters are converted to speech. The tool shows you an estimate and asks for confirmation before generating anything, so you won't be surprised. Check [ElevenLabs pricing](https://elevenlabs.io/pricing) for current rates.

## Privacy

All message reading happens locally on your Mac. The only data sent over the internet is the text of each message to ElevenLabs for voice generation. No messages are stored anywhere besides your computer and the resulting MP3 file.

## License

MIT
