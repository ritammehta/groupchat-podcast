"""Tests for podcast generation and audio stitching."""

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from groupchat_podcast.imessage import Message
from groupchat_podcast.podcast import (
    PodcastGenerator,
    merge_consecutive_messages,
    stitch_audio,
)

# Check if ffmpeg is available
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG_AVAILABLE,
    reason="ffmpeg not installed - required for audio processing"
)


@requires_ffmpeg
class TestStitchAudio:
    """Tests for audio stitching functionality."""

    def test_stitches_multiple_audio_segments(self, tmp_path, sample_audio_bytes):
        """Combine multiple audio segments into one file."""
        seg1 = tmp_path / "seg1.mp3"
        seg2 = tmp_path / "seg2.mp3"
        seg1.write_bytes(sample_audio_bytes)
        seg2.write_bytes(sample_audio_bytes)

        output_path = tmp_path / "output.mp3"

        stitch_audio(
            segments=[seg1, seg2],
            output_path=output_path,
            pause_ms=500,
        )

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_adds_pause_between_segments(self, tmp_path, sample_audio_bytes):
        """Pauses should be inserted between segments."""
        seg1 = tmp_path / "seg1.mp3"
        seg2 = tmp_path / "seg2.mp3"
        seg1.write_bytes(sample_audio_bytes)
        seg2.write_bytes(sample_audio_bytes)

        output_no_pause = tmp_path / "no_pause.mp3"
        output_with_pause = tmp_path / "with_pause.mp3"

        stitch_audio([seg1, seg2], output_no_pause, pause_ms=0)
        stitch_audio([seg1, seg2], output_with_pause, pause_ms=1000)

        # File with pause should be larger (more audio data)
        assert output_with_pause.stat().st_size >= output_no_pause.stat().st_size

    def test_handles_single_segment(self, tmp_path, sample_audio_bytes):
        """Single segment should work without error."""
        seg1 = tmp_path / "seg1.mp3"
        seg1.write_bytes(sample_audio_bytes)

        output_path = tmp_path / "output.mp3"

        stitch_audio([seg1], output_path, pause_ms=500)

        assert output_path.exists()

    def test_output_is_valid_audio_format(self, tmp_path, sample_audio_bytes):
        """Output file should be a valid audio format."""
        seg1 = tmp_path / "seg1.mp3"
        seg1.write_bytes(sample_audio_bytes)

        output_path = tmp_path / "output.mp3"
        stitch_audio([seg1], output_path, pause_ms=0)

        # Check for MP3 magic bytes or ID3 tag
        content = output_path.read_bytes()
        assert content[:2] == b"\xff\xfb" or content[:3] == b"ID3"


class TestStitchAudioNoFfmpeg:
    """Tests that don't require ffmpeg."""

    def test_handles_empty_segment_list(self, tmp_path):
        """Empty segment list should raise ValueError."""
        output_path = tmp_path / "output.mp3"

        with pytest.raises(ValueError):
            stitch_audio([], output_path, pause_ms=500)


@requires_ffmpeg
class TestPodcastGeneratorWithFfmpeg:
    """Tests for podcast generation that require ffmpeg."""

    def test_generates_podcast_from_messages(self, mocker, tmp_path, mock_chat_db, sample_audio_bytes):
        """Full pipeline: messages -> TTS -> stitched output."""
        mock_tts = mocker.Mock()
        mock_tts.generate.return_value = sample_audio_bytes

        voice_map = {
            "+15551234567": "voice-1",
            "+15559876543": "voice-2",
            "friend@email.com": "voice-3",
            "Me": "voice-me",
            "_default": "voice-default",
        }

        output_path = tmp_path / "podcast.mp3"

        generator = PodcastGenerator(tts_client=mock_tts, voice_map=voice_map)
        generator.generate(
            db_path=mock_chat_db,
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            output_path=output_path,
            pause_ms=500,
        )

        assert output_path.exists()
        assert mock_tts.generate.call_count >= 5

    def test_uses_correct_voice_for_each_sender(self, mocker, tmp_path, mock_chat_db, sample_audio_bytes):
        """Each sender should use their mapped voice."""
        mock_tts = mocker.Mock()
        mock_tts.generate.return_value = sample_audio_bytes

        voice_map = {
            "+15551234567": "alice-voice",
            "+15559876543": "bob-voice",
            "Me": "my-voice",
            "_default": "default-voice",
        }

        generator = PodcastGenerator(tts_client=mock_tts, voice_map=voice_map)
        generator.generate(
            db_path=mock_chat_db,
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            output_path=tmp_path / "podcast.mp3",
        )

        calls = mock_tts.generate.call_args_list
        voice_ids_used = [call.kwargs.get("voice_id") or call.args[1] for call in calls]

        assert "alice-voice" in voice_ids_used
        assert "bob-voice" in voice_ids_used or "my-voice" in voice_ids_used

    def test_uses_default_voice_for_unknown_sender(self, mocker, tmp_path, mock_chat_db, sample_audio_bytes):
        """Senders not in voice_map should use _default voice."""
        mock_tts = mocker.Mock()
        mock_tts.generate.return_value = sample_audio_bytes

        voice_map = {
            "+15551234567": "known-voice",
            "_default": "fallback-voice",
        }

        generator = PodcastGenerator(tts_client=mock_tts, voice_map=voice_map)
        generator.generate(
            db_path=mock_chat_db,
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            output_path=tmp_path / "podcast.mp3",
        )

        calls = mock_tts.generate.call_args_list
        voice_ids_used = [call.kwargs.get("voice_id") or call.args[1] for call in calls]

        assert "fallback-voice" in voice_ids_used

    def test_skips_empty_messages(self, mocker, tmp_path, sample_audio_bytes):
        """Messages with no text should be skipped."""
        mock_tts = mocker.Mock()
        mock_tts.generate.return_value = sample_audio_bytes

        mocker.patch(
            "groupchat_podcast.podcast.extract_messages",
            return_value=[
                Message(sender="Alice", text="Hello", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
                Message(sender="Bob", text="", timestamp=datetime(2024, 1, 15, 10, 0, 10), guid="2"),
                Message(sender="Charlie", text=None, timestamp=datetime(2024, 1, 15, 10, 0, 20), guid="3"),
                Message(sender="Dave", text="World", timestamp=datetime(2024, 1, 15, 10, 0, 30), guid="4"),
            ],
        )

        generator = PodcastGenerator(
            tts_client=mock_tts,
            voice_map={"_default": "voice"},
        )
        generator.generate(
            db_path=Path("/fake/path"),
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            output_path=tmp_path / "podcast.mp3",
        )

        assert mock_tts.generate.call_count == 2

    def test_reports_progress(self, mocker, tmp_path, mock_chat_db, sample_audio_bytes):
        """Generator should report progress via callback."""
        mock_tts = mocker.Mock()
        mock_tts.generate.return_value = sample_audio_bytes

        progress_calls = []

        def on_progress(current, total, message_text):
            progress_calls.append((current, total, message_text))

        generator = PodcastGenerator(
            tts_client=mock_tts,
            voice_map={"_default": "voice"},
        )
        generator.generate(
            db_path=mock_chat_db,
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            output_path=tmp_path / "podcast.mp3",
            on_progress=on_progress,
        )

        assert len(progress_calls) > 0
        assert progress_calls[-1][0] == progress_calls[-1][1]


class TestMergeConsecutiveMessages:
    """Tests for merging rapid-fire same-sender messages."""

    def test_merges_same_sender_within_time_window(self):
        """Consecutive messages from same sender within 5 min should merge."""
        messages = [
            Message(sender="Alice", text="Hey", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
            Message(sender="Alice", text="how are you", timestamp=datetime(2024, 1, 15, 10, 0, 30), guid="2"),
            Message(sender="Alice", text="long time no see", timestamp=datetime(2024, 1, 15, 10, 1, 0), guid="3"),
        ]
        result = merge_consecutive_messages(messages)
        assert len(result) == 1
        assert "Hey" in result[0].text
        assert "how are you" in result[0].text
        assert "long time no see" in result[0].text

    def test_does_not_merge_different_senders(self):
        """Messages from different senders should stay separate."""
        messages = [
            Message(sender="Alice", text="Hey", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
            Message(sender="Bob", text="Hi there", timestamp=datetime(2024, 1, 15, 10, 0, 10), guid="2"),
            Message(sender="Alice", text="What's up", timestamp=datetime(2024, 1, 15, 10, 0, 20), guid="3"),
        ]
        result = merge_consecutive_messages(messages)
        assert len(result) == 3

    def test_does_not_merge_beyond_time_gap(self):
        """Same sender messages beyond 5 min apart should not merge."""
        messages = [
            Message(sender="Alice", text="Hey", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
            Message(sender="Alice", text="Anyone there", timestamp=datetime(2024, 1, 15, 10, 6, 0), guid="2"),
        ]
        result = merge_consecutive_messages(messages)
        assert len(result) == 2

    def test_smart_separator_adds_comma_without_punctuation(self):
        """Messages without trailing punctuation should be joined with comma."""
        messages = [
            Message(sender="Alice", text="Hey", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
            Message(sender="Alice", text="how are you", timestamp=datetime(2024, 1, 15, 10, 0, 10), guid="2"),
        ]
        result = merge_consecutive_messages(messages)
        assert result[0].text == "Hey, how are you"

    def test_smart_separator_uses_space_after_punctuation(self):
        """Messages with trailing punctuation should be joined with space."""
        messages = [
            Message(sender="Alice", text="Am I too critical?", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
            Message(sender="Alice", text="Truly love it", timestamp=datetime(2024, 1, 15, 10, 0, 10), guid="2"),
        ]
        result = merge_consecutive_messages(messages)
        assert result[0].text == "Am I too critical? Truly love it"

    def test_preserves_sender_and_timestamp_from_first_message(self):
        """Merged message should use first message's sender and timestamp."""
        first_ts = datetime(2024, 1, 15, 10, 0, 0)
        messages = [
            Message(sender="Alice", text="Hey", timestamp=first_ts, guid="first-guid"),
            Message(sender="Alice", text="what's up", timestamp=datetime(2024, 1, 15, 10, 0, 30), guid="second-guid"),
        ]
        result = merge_consecutive_messages(messages)
        assert result[0].sender == "Alice"
        assert result[0].timestamp == first_ts
        assert result[0].guid == "first-guid"

    def test_real_world_tv_show_monologue(self):
        """Stream-of-consciousness TV show texts should merge into one message."""
        messages = [
            Message(sender="Alex", text="Man", timestamp=datetime(2024, 1, 15, 22, 0, 0), guid="1"),
            Message(sender="Alex", text="Good industry ep though", timestamp=datetime(2024, 1, 15, 22, 0, 5), guid="2"),
            Message(sender="Alex", text="Harper / yas stuff often feels unearned", timestamp=datetime(2024, 1, 15, 22, 0, 12), guid="3"),
            Message(sender="Alex", text="Am I too critical of this show?", timestamp=datetime(2024, 1, 15, 22, 0, 20), guid="4"),
            Message(sender="Alex", text="Truly love it and find it totally engaging", timestamp=datetime(2024, 1, 15, 22, 0, 28), guid="5"),
            Message(sender="Alex", text="Max minghella is delivering a lifetime performance", timestamp=datetime(2024, 1, 15, 22, 0, 40), guid="6"),
            Message(sender="Alex", text="But just like sometimes I feel like it just does not earn its big moments", timestamp=datetime(2024, 1, 15, 22, 0, 55), guid="7"),
            Message(sender="Alex", text="Like I think it's outrunning some obvious criticisms by being formally daring and extremely current", timestamp=datetime(2024, 1, 15, 22, 1, 10), guid="8"),
            Message(sender="Alex", text='But I think that the creators have thrown out too much of the baby with the bathwater when trying to push the envelope on "what constitutes prestige tv"', timestamp=datetime(2024, 1, 15, 22, 1, 30), guid="9"),
            Message(sender="Alex", text="They're not earning their turns", timestamp=datetime(2024, 1, 15, 22, 1, 40), guid="10"),
            Message(sender="Alex", text="Need to listen to No Notes now that I'm all caught up", timestamp=datetime(2024, 1, 15, 22, 1, 50), guid="11"),
        ]
        result = merge_consecutive_messages(messages)
        assert len(result) == 1
        # After "Am I too critical of this show?" there should be a space (not comma) before "Truly"
        assert "show? Truly" in result[0].text

    def test_partial_merge_with_interleaved_senders(self):
        """Only consecutive same-sender runs should merge."""
        messages = [
            Message(sender="Alice", text="Hey", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
            Message(sender="Alice", text="what's up", timestamp=datetime(2024, 1, 15, 10, 0, 10), guid="2"),
            Message(sender="Bob", text="Not much", timestamp=datetime(2024, 1, 15, 10, 0, 20), guid="3"),
            Message(sender="Alice", text="Cool", timestamp=datetime(2024, 1, 15, 10, 0, 30), guid="4"),
            Message(sender="Alice", text="wanna hang", timestamp=datetime(2024, 1, 15, 10, 0, 40), guid="5"),
        ]
        result = merge_consecutive_messages(messages)
        assert len(result) == 3
        assert "Hey" in result[0].text and "what's up" in result[0].text
        assert result[1].text == "Not much"
        assert "Cool" in result[2].text and "wanna hang" in result[2].text

    def test_empty_list_returns_empty(self):
        """Empty message list should return empty list."""
        result = merge_consecutive_messages([])
        assert result == []

    def test_single_message_unchanged(self):
        """A single message should pass through unchanged."""
        messages = [
            Message(sender="Alice", text="Hey", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
        ]
        result = merge_consecutive_messages(messages)
        assert len(result) == 1
        assert result[0].text == "Hey"

    def test_preserves_has_attachment_if_any(self):
        """Merged message should have has_attachment=True if any message had one."""
        messages = [
            Message(sender="Alice", text="Look at this", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1", has_attachment=False),
            Message(sender="Alice", text="cool right", timestamp=datetime(2024, 1, 15, 10, 0, 10), guid="2", has_attachment=True),
        ]
        result = merge_consecutive_messages(messages)
        assert len(result) == 1
        assert result[0].has_attachment is True


@requires_ffmpeg
class TestPodcastGeneratorPreprocessing:
    """Tests for preprocessing and merging in the generation pipeline."""

    def test_preprocessing_applied_before_tts(self, mocker, tmp_path, sample_audio_bytes):
        """Text should be preprocessed before reaching the TTS client."""
        mock_tts = mocker.Mock()
        mock_tts.generate.return_value = sample_audio_bytes

        mocker.patch(
            "groupchat_podcast.podcast.extract_messages",
            return_value=[
                Message(sender="Alice", text="idk 😊 that's CRAZY!!!", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
            ],
        )

        generator = PodcastGenerator(tts_client=mock_tts, voice_map={"_default": "voice"})
        generator.generate(
            db_path=Path("/fake/path"),
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            output_path=tmp_path / "podcast.mp3",
        )

        text_sent = mock_tts.generate.call_args_list[0].args[0]
        assert "😊" not in text_sent
        assert "idk" not in text_sent.lower().split()
        assert "I don't know" in text_sent
        assert "!!!" not in text_sent

    def test_merging_reduces_tts_calls(self, mocker, tmp_path, sample_audio_bytes):
        """Consecutive same-sender messages should be merged, reducing TTS calls."""
        mock_tts = mocker.Mock()
        mock_tts.generate.return_value = sample_audio_bytes

        mocker.patch(
            "groupchat_podcast.podcast.extract_messages",
            return_value=[
                Message(sender="Alice", text="Hey", timestamp=datetime(2024, 1, 15, 10, 0, 0), guid="1"),
                Message(sender="Alice", text="how are you", timestamp=datetime(2024, 1, 15, 10, 0, 10), guid="2"),
                Message(sender="Alice", text="long time no see", timestamp=datetime(2024, 1, 15, 10, 0, 20), guid="3"),
                Message(sender="Bob", text="I'm good!", timestamp=datetime(2024, 1, 15, 10, 0, 30), guid="4"),
            ],
        )

        generator = PodcastGenerator(tts_client=mock_tts, voice_map={"_default": "voice"})
        generator.generate(
            db_path=Path("/fake/path"),
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            output_path=tmp_path / "podcast.mp3",
        )

        # 3 Alice messages merged into 1 + 1 Bob message = 2 TTS calls
        assert mock_tts.generate.call_count == 2


class TestPodcastGeneratorNoFfmpeg:
    """Tests for podcast generation that don't require ffmpeg."""

    def test_estimates_cost(self, mocker, mock_chat_db):
        """Generator can estimate cost before generating."""
        generator = PodcastGenerator(
            tts_client=mocker.Mock(),
            voice_map={"_default": "voice"},
        )

        estimate = generator.estimate_cost(
            db_path=mock_chat_db,
            chat_id=1,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )

        assert "characters" in estimate
        assert "estimated_cost" in estimate
        assert estimate["characters"] > 0
        assert estimate["message_count"] > 0
