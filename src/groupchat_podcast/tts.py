"""ElevenLabs TTS integration module."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from elevenlabs import ElevenLabs

# Abbreviations to expand to their spoken forms
_EXPAND_ABBREVIATIONS = {
    "idk": "I don't know",
    "btw": "by the way",
    "ngl": "not gonna lie",
    "lmk": "let me know",
    "nvm": "nevermind",
    "ikr": "I know right",
    "hmu": "hit me up",
    "wyd": "what you doing",
    "wya": "where you at",
    "ofc": "of course",
    "pls": "please",
    "plz": "please",
    "fr": "for real",
    "wdym": "what do you mean",
}

# Abbreviations that TTS mispronounces phonetically — force uppercase
_UPPERCASE_ABBREVIATIONS = {"af", "brb", "imo", "lmao"}

# Combined set of all known abbreviations (for caps normalizer exclusion)
_KNOWN_ABBREVIATIONS = _UPPERCASE_ABBREVIATIONS | {
    "lol", "omg", "tbh", "smh", "irl", "jk", "rn", "gtg",
}

# Emoji regex pattern — specific ranges that avoid stripping CJK text
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa00-\U0001fa6f"  # chess symbols
    "\U0001fa70-\U0001faff"  # symbols extended-A
    "\U00002702-\U000027b0"  # dingbats
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U0000200d"             # zero width joiner
    "\U00002600-\U000026ff"  # misc symbols (sun, cloud, etc.)
    "\U00002700-\U000027bf"  # dingbats
    "]+",
    flags=re.UNICODE,
)


def preprocess_text_for_tts(text: str) -> str:
    """Preprocess chat text for natural TTS output.

    Applies the following transformations:
    1. Strip emojis
    2. Expand abbreviations (idk -> I don't know)
    3. Uppercase abbreviations that TTS mispronounces (brb -> BRB)
    4. Normalize repeated punctuation (!!! -> !, ??? -> ?)
    5. Lowercase excessive all-caps words (4+ chars), preserving known abbreviations
    6. Collapse whitespace
    """
    # 1. Strip emojis
    text = _EMOJI_PATTERN.sub("", text)

    # 2. Expand abbreviations (case-insensitive, whole-word)
    for abbrev, expansion in _EXPAND_ABBREVIATIONS.items():
        text = re.sub(rf"\b{abbrev}\b", expansion, text, flags=re.IGNORECASE)

    # Handle "bc" conditionally — don't expand after numbers or "century"
    text = re.sub(
        r"(?<!\d\s)(?<!century\s)\bbc\b",
        "because",
        text,
        flags=re.IGNORECASE,
    )

    # 3. Uppercase abbreviations that TTS mispronounces phonetically
    for abbrev in _UPPERCASE_ABBREVIATIONS:
        text = re.sub(
            rf"\b{abbrev}\b", abbrev.upper(), text, flags=re.IGNORECASE
        )

    # 4. Normalize repeated punctuation (preserve ellipsis)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)

    # 5. Lowercase excessive all-caps words (4+ chars), skip known abbreviations
    def _lowercase_caps(match: re.Match) -> str:
        word = match.group(0)
        if word.lower() in _KNOWN_ABBREVIATIONS:
            return word
        return word.lower()

    text = re.sub(r"\b[A-Z]{4,}\b", _lowercase_caps, text)

    # 6. Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


@dataclass
class Voice:
    """Represents an ElevenLabs voice."""

    voice_id: str
    name: str
    labels: Dict[str, str]


class TTSClient:
    """Client wrapper for ElevenLabs TTS API."""

    def __init__(self, api_key: str, voice_settings: Optional[Dict[str, Any]] = None):
        """Initialize the TTS client.

        Args:
            api_key: ElevenLabs API key
            voice_settings: Optional voice settings dict with keys like
                stability, similarity_boost, style, use_speaker_boost
        """
        self._client = ElevenLabs(api_key=api_key)
        self._voice_settings = voice_settings

    def generate(self, text: str, voice_id: str) -> bytes:
        """Generate audio from text using the specified voice.

        Args:
            text: The text to convert to speech
            voice_id: The ElevenLabs voice ID to use

        Returns:
            Audio data as bytes (MP3 format)
        """
        kwargs: Dict[str, Any] = {
            "text": text,
            "voice_id": voice_id,
            "model_id": "eleven_multilingual_v2",
            "output_format": "mp3_44100_128",
        }
        if self._voice_settings is not None:
            kwargs["voice_settings"] = self._voice_settings

        audio = self._client.text_to_speech.convert(**kwargs)

        # The API returns a generator, collect all bytes
        if isinstance(audio, bytes):
            return audio
        return b"".join(audio)

    def search_voices(self, query: str = "") -> List[Voice]:
        """Search for available voices.

        Args:
            query: Optional search query to filter voices by name

        Returns:
            List of Voice objects matching the query
        """
        response = self._client.voices.search(search=query if query else None)

        voices = []
        for voice in response.voices:
            voices.append(
                Voice(
                    voice_id=voice.voice_id,
                    name=voice.name,
                    labels=dict(voice.labels) if voice.labels else {},
                )
            )

        return voices

    def get_voice(self, voice_id: str) -> Voice:
        """Get a specific voice by ID.

        Args:
            voice_id: The ElevenLabs voice ID

        Returns:
            Voice object with the voice details
        """
        voice = self._client.voices.get(voice_id)

        return Voice(
            voice_id=voice.voice_id,
            name=voice.name,
            labels=dict(voice.labels) if voice.labels else {},
        )
