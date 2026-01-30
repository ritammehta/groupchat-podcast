"""ElevenLabs TTS integration module."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from elevenlabs import ElevenLabs


@dataclass
class Voice:
    """Represents an ElevenLabs voice."""

    voice_id: str
    name: str
    labels: Dict[str, str]


class TTSClient:
    """Client wrapper for ElevenLabs TTS API."""

    def __init__(self, api_key: str):
        """Initialize the TTS client."""
        self._client = ElevenLabs(api_key=api_key)

    def generate(self, text: str, voice_id: str) -> bytes:
        """Generate audio from text using the specified voice.

        Args:
            text: The text to convert to speech
            voice_id: The ElevenLabs voice ID to use

        Returns:
            Audio data as bytes (MP3 format)
        """
        audio = self._client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )

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
