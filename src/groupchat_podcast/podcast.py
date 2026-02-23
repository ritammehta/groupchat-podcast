"""Podcast generation and audio stitching module."""

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydub import AudioSegment

from groupchat_podcast.imessage import Message, extract_messages
from groupchat_podcast.tts import TTSClient, preprocess_text_for_tts


def _smart_join(existing: str, new: str) -> str:
    """Join two texts with comma or space depending on trailing punctuation."""
    if not existing:
        return new
    if not new:
        return existing
    if existing[-1] in ".!?":
        return existing + " " + new
    return existing + ", " + new


def merge_consecutive_messages(
    messages: List[Message], max_gap_seconds: int = 300,
) -> List[Message]:
    """Merge consecutive same-sender messages within a time window.

    Messages from the same sender where each successive gap is within
    max_gap_seconds are combined into a single Message. Text is joined
    with smart separators (comma when no trailing punctuation, space
    when there is).

    Args:
        messages: List of messages in chronological order
        max_gap_seconds: Maximum seconds between messages to merge

    Returns:
        New list of messages with consecutive runs merged
    """
    if not messages:
        return []

    result: List[Message] = []
    current = messages[0]
    merged_text = current.text or ""
    has_any_attachment = current.has_attachment

    for i in range(1, len(messages)):
        msg = messages[i]
        gap = (msg.timestamp - messages[i - 1].timestamp).total_seconds()

        if msg.sender == current.sender and gap <= max_gap_seconds:
            merged_text = _smart_join(merged_text, msg.text or "")
            has_any_attachment = has_any_attachment or msg.has_attachment
        else:
            result.append(Message(
                sender=current.sender,
                text=merged_text,
                timestamp=current.timestamp,
                guid=current.guid,
                thread_originator_guid=current.thread_originator_guid,
                has_attachment=has_any_attachment,
                attachment_type=current.attachment_type,
            ))
            current = msg
            merged_text = msg.text or ""
            has_any_attachment = msg.has_attachment

    # Append the last run
    result.append(Message(
        sender=current.sender,
        text=merged_text,
        timestamp=current.timestamp,
        guid=current.guid,
        thread_originator_guid=current.thread_originator_guid,
        has_attachment=has_any_attachment,
        attachment_type=current.attachment_type,
    ))

    return result


def stitch_audio(
    segments: List[Path],
    output_path: Path,
    pause_ms: int = 500,
) -> None:
    """Stitch multiple audio segments into a single file with pauses.

    Args:
        segments: List of paths to audio files to concatenate
        output_path: Path to write the output file
        pause_ms: Milliseconds of silence between segments

    Raises:
        ValueError: If segments list is empty
    """
    if not segments:
        raise ValueError("Cannot stitch empty segment list")

    # Create silence segment for pauses
    silence = AudioSegment.silent(duration=pause_ms)

    # Load and concatenate all segments
    combined = AudioSegment.empty()

    for i, segment_path in enumerate(segments):
        audio = AudioSegment.from_mp3(segment_path)
        combined += audio

        # Add pause between segments (not after the last one)
        if i < len(segments) - 1 and pause_ms > 0:
            combined += silence

    # Export to output file
    combined.export(output_path, format="mp3")


class PodcastGenerator:
    """Orchestrates podcast generation from iMessage chats."""

    def __init__(self, tts_client: TTSClient, voice_map: Dict[str, str]):
        """Initialize the podcast generator.

        Args:
            tts_client: TTS client for generating audio
            voice_map: Mapping of sender IDs to voice IDs.
                       Use "_default" key for fallback voice.
        """
        self._tts = tts_client
        self._voice_map = voice_map

    def _get_voice_id(self, sender: str) -> str:
        """Get the voice ID for a sender."""
        if sender in self._voice_map:
            return self._voice_map[sender]
        return self._voice_map.get("_default", "")

    def generate(
        self,
        db_path: Path,
        chat_id: int,
        start_date: datetime,
        end_date: datetime,
        output_path: Path,
        pause_ms: int = 500,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> None:
        """Generate a podcast from chat messages.

        Args:
            db_path: Path to the iMessage database
            chat_id: ID of the chat to extract messages from
            start_date: Start of date range
            end_date: End of date range
            output_path: Path to write the output audio file
            pause_ms: Milliseconds of pause between messages
            on_progress: Optional callback(current, total, message_text)
        """
        # Extract messages
        messages = extract_messages(db_path, chat_id, start_date, end_date)

        # Filter out empty messages
        messages = [m for m in messages if m.text and m.text.strip()]

        if not messages:
            raise ValueError("No messages to generate podcast from")

        # Merge consecutive same-sender messages
        messages = merge_consecutive_messages(messages)

        total = len(messages)
        segment_paths: List[Path] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            for i, message in enumerate(messages):
                # Report progress
                if on_progress:
                    on_progress(i + 1, total, message.text[:50] if message.text else "")

                # Get voice for this sender
                voice_id = self._get_voice_id(message.sender)
                if not voice_id:
                    import warnings
                    warnings.warn(
                        f"No voice mapped for sender '{message.sender}' and no _default - skipping"
                    )
                    continue

                # Preprocess text for TTS
                text = preprocess_text_for_tts(message.text)

                # Generate audio
                audio_bytes = self._tts.generate(text, voice_id=voice_id)

                # Save to temp file
                segment_path = tmp_path / f"segment_{i:05d}.mp3"
                segment_path.write_bytes(audio_bytes)
                segment_paths.append(segment_path)

            # Stitch all segments together
            if not segment_paths:
                raise ValueError(
                    "No audio segments generated - check voice mappings"
                )
            stitch_audio(segment_paths, output_path, pause_ms)

    def estimate_cost(
        self,
        db_path: Path,
        chat_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Estimate the cost of generating a podcast.

        Args:
            db_path: Path to the iMessage database
            chat_id: ID of the chat
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dictionary with:
                - characters: Total character count
                - message_count: Number of messages
                - estimated_cost: Estimated cost in USD
        """
        messages = extract_messages(db_path, chat_id, start_date, end_date)
        messages = [m for m in messages if m.text and m.text.strip()]
        messages = merge_consecutive_messages(messages)

        total_chars = sum(
            len(preprocess_text_for_tts(m.text)) for m in messages if m.text
        )

        # ElevenLabs pricing: roughly $0.30 per 1000 characters on Creator plan
        cost_per_char = 0.30 / 1000

        return {
            "characters": total_chars,
            "message_count": len(messages),
            "estimated_cost": round(total_chars * cost_per_char, 2),
        }
