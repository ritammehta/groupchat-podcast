"""Tests for ElevenLabs TTS integration."""

import pytest

from groupchat_podcast.tts import TTSClient, Voice, preprocess_text_for_tts


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

    def test_generate_forwards_voice_settings(self, mocker):
        """Voice settings from constructor should be passed to API."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value
        mock_client.text_to_speech.convert.return_value = b"audio"

        settings = {"stability": 0.4, "similarity_boost": 0.5, "style": 0.0}
        client = TTSClient(api_key="test-key", voice_settings=settings)
        client.generate("Hello", voice_id="voice-id")

        call_kwargs = mock_client.text_to_speech.convert.call_args.kwargs
        assert call_kwargs["voice_settings"] == settings

    def test_generate_without_voice_settings(self, mocker):
        """Without voice settings, API call should not include them."""
        mock_elevenlabs = mocker.patch("groupchat_podcast.tts.ElevenLabs")
        mock_client = mock_elevenlabs.return_value
        mock_client.text_to_speech.convert.return_value = b"audio"

        client = TTSClient(api_key="test-key")
        client.generate("Hello", voice_id="voice-id")

        call_kwargs = mock_client.text_to_speech.convert.call_args.kwargs
        assert "voice_settings" not in call_kwargs


class TestPreprocessTextForTts:
    """Tests for chat text preprocessing before TTS."""

    def test_removes_emojis_preserving_text(self):
        """Emojis should be stripped while keeping surrounding words."""
        result = preprocess_text_for_tts("Hey 😊 how are you 🎉")
        assert "😊" not in result
        assert "🎉" not in result
        assert "Hey" in result
        assert "how are you" in result

    def test_expands_idk(self):
        """idk should expand to I don't know."""
        result = preprocess_text_for_tts("idk what to do")
        assert "I don't know" in result
        assert "idk" not in result.lower().split()

    def test_expands_multiple_abbreviations(self):
        """Multiple abbreviations in one message should all expand."""
        result = preprocess_text_for_tts("btw lmk if you can come")
        assert "by the way" in result
        assert "let me know" in result

    def test_expands_abbreviations_case_insensitive(self):
        """Abbreviations should expand regardless of case."""
        result = preprocess_text_for_tts("IDK man")
        assert "I don't know" in result

    def test_uppercases_tts_abbreviations(self):
        """Abbreviations that TTS mispronounces should be uppercased."""
        result = preprocess_text_for_tts("brb going to store")
        assert "BRB" in result

        result = preprocess_text_for_tts("that's funny lmao")
        assert "LMAO" in result

        result = preprocess_text_for_tts("imo it's overrated")
        assert "IMO" in result

        result = preprocess_text_for_tts("that's annoying af")
        assert "AF" in result

    def test_reduces_repeated_exclamation(self):
        """Multiple exclamation marks should reduce to one."""
        result = preprocess_text_for_tts("No way!!!")
        assert "!!!" not in result
        assert result.endswith("!")

    def test_reduces_repeated_question_marks(self):
        """Multiple question marks should reduce to one."""
        result = preprocess_text_for_tts("Really???")
        assert "???" not in result
        assert result.endswith("?")

    def test_preserves_ellipsis(self):
        """Ellipsis should be preserved as it creates useful TTS hesitation."""
        result = preprocess_text_for_tts("Well... I guess so")
        assert "..." in result

    def test_lowercases_excessive_caps(self):
        """Words 4+ chars in ALL CAPS should be lowercased."""
        result = preprocess_text_for_tts("WHAT THE HELL is going on")
        assert "what" in result
        assert "hell" in result

    def test_preserves_known_uppercase_abbreviations(self):
        """Known abbreviations should not be lowercased by caps normalizer."""
        result = preprocess_text_for_tts("LMAO that's hilarious")
        assert "LMAO" in result

    def test_clean_text_passes_through(self):
        """Normal text without special chat content should pass through."""
        text = "Hey how are you doing today"
        result = preprocess_text_for_tts(text)
        assert result == text

    def test_bc_expanded_as_because(self):
        """bc should expand to because in normal context."""
        result = preprocess_text_for_tts("I left bc it was boring")
        assert "because" in result

    def test_bc_not_expanded_after_number(self):
        """bc should not expand when preceded by a number (e.g. 300 bc)."""
        result = preprocess_text_for_tts("that was like 300 bc")
        assert "because" not in result
        assert "bc" in result

    def test_bc_not_expanded_after_century(self):
        """bc should not expand after 'century'."""
        result = preprocess_text_for_tts("the 3rd century bc was wild")
        assert "because" not in result
        assert "bc" in result

    def test_collapses_whitespace(self):
        """Multiple spaces should collapse to one, leading/trailing stripped."""
        result = preprocess_text_for_tts("  hey   how   are   you  ")
        assert result == "hey how are you"

    def test_pls_expanded_to_please(self):
        """pls and plz should expand to please."""
        assert "please" in preprocess_text_for_tts("pls help me")
        assert "please" in preprocess_text_for_tts("plz come over")

    def test_fr_does_not_expand_inside_words(self):
        """'fr' inside words like 'from' or 'friend' should not expand."""
        assert "from" in preprocess_text_for_tts("I'm coming from school")
        assert "friend" in preprocess_text_for_tts("She's my friend")
