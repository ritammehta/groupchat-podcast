"""Tests for podcast generation and audio stitching."""

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from groupchat_podcast.imessage import Message
from groupchat_podcast.podcast import PodcastGenerator, stitch_audio

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
                Message(sender="+15551234567", text="Hello", timestamp=datetime.now(), guid="1"),
                Message(sender="+15551234567", text="", timestamp=datetime.now(), guid="2"),
                Message(sender="+15551234567", text=None, timestamp=datetime.now(), guid="3"),
                Message(sender="+15551234567", text="World", timestamp=datetime.now(), guid="4"),
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
