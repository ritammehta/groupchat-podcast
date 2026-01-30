"""Tests for ElevenLabs TTS integration."""

import pytest

from groupchat_podcast.tts import TTSClient, Voice


class TestTTSClient:
    """Tests for the TTS client wrapper."""

    def test_generate_returns_audio_bytes(self, mocker):
        """Generate audio from text returns bytes."""
        # Mock the ElevenLabs client
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value
        mock_client.text_to_speech.convert.return_value = b"fake audio bytes"

        client = TTSClient(api_key="test-key")
        result = client.generate("Hello world", voice_id="test-voice-id")

        assert isinstance(result, bytes)
        assert len(result) > 0
        mock_client.text_to_speech.convert.assert_called_once()

    def test_generate_uses_correct_voice_id(self, mocker):
        """Generate should use the specified voice ID."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value
        mock_client.text_to_speech.convert.return_value = b"audio"

        client = TTSClient(api_key="test-key")
        client.generate("Hello", voice_id="specific-voice-123")

        call_kwargs = mock_client.text_to_speech.convert.call_args
        assert call_kwargs.kwargs["voice_id"] == "specific-voice-123"

    def test_generate_uses_correct_model(self, mocker):
        """Generate should use multilingual v2 model."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value
        mock_client.text_to_speech.convert.return_value = b"audio"

        client = TTSClient(api_key="test-key")
        client.generate("Hello", voice_id="voice-id")

        call_kwargs = mock_client.text_to_speech.convert.call_args
        assert call_kwargs.kwargs["model_id"] == "eleven_multilingual_v2"

    def test_search_voices_returns_voice_list(self, mocker):
        """Search voices returns list of Voice objects."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value

        # Create mock voice objects
        mock_voice = mocker.Mock()
        mock_voice.voice_id = "voice-123"
        mock_voice.name = "Rachel"
        mock_voice.labels = {"accent": "american", "gender": "female"}

        mock_response = mocker.Mock()
        mock_response.voices = [mock_voice]
        mock_client.voices.search.return_value = mock_response

        client = TTSClient(api_key="test-key")
        voices = client.search_voices("rachel")

        assert len(voices) == 1
        assert isinstance(voices[0], Voice)
        assert voices[0].voice_id == "voice-123"
        assert voices[0].name == "Rachel"

    def test_search_voices_with_empty_query_passes_none(self, mocker):
        """Empty search query should pass None to API (returns all voices)."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value

        mock_response = mocker.Mock()
        mock_response.voices = []
        mock_client.voices.search.return_value = mock_response

        client = TTSClient(api_key="test-key")
        client.search_voices("")

        # Verify the API was called with search=None (not empty string)
        mock_client.voices.search.assert_called_once_with(search=None)

    def test_get_voice_by_id(self, mocker):
        """Get a specific voice by ID."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value

        mock_voice = mocker.Mock()
        mock_voice.voice_id = "specific-id"
        mock_voice.name = "Custom Voice"
        mock_voice.labels = {}
        mock_client.voices.get.return_value = mock_voice

        client = TTSClient(api_key="test-key")
        voice = client.get_voice("specific-id")

        assert voice.voice_id == "specific-id"
        assert voice.name == "Custom Voice"
        mock_client.voices.get.assert_called_once_with("specific-id")

    def test_handles_api_error_gracefully(self, mocker):
        """API errors should propagate with their original message."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value
        mock_client.text_to_speech.convert.side_effect = Exception("Rate limit exceeded")

        client = TTSClient(api_key="test-key")

        with pytest.raises(Exception) as exc_info:
            client.generate("Hello", voice_id="voice-id")

        # Verify the original error message is preserved
        assert "Rate limit exceeded" in str(exc_info.value)

    def test_client_uses_provided_api_key(self, mocker):
        """Client should initialize with the provided API key."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")

        TTSClient(api_key="my-secret-key")

        mock_elevenlabs.assert_called_once_with(api_key="my-secret-key")
