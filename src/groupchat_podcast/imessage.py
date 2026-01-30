"""iMessage database extraction module."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Mac epoch: January 1, 2001
MAC_EPOCH = datetime(2001, 1, 1)

# Default database path
DEFAULT_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"


@dataclass
class GroupChat:
    """Represents an iMessage group chat."""

    chat_id: int
    display_name: str
    participant_count: int
    participants: List[str]


@dataclass
class Message:
    """Represents an iMessage message."""

    sender: str
    text: Optional[str]
    timestamp: datetime
    guid: str
    thread_originator_guid: Optional[str] = None
    has_attachment: bool = False
    attachment_type: Optional[str] = None


def convert_mac_timestamp(mac_timestamp: int) -> datetime:
    """Convert Mac nanosecond timestamp to Python datetime."""
    if mac_timestamp == 0:
        return MAC_EPOCH
    seconds = mac_timestamp / 1_000_000_000
    return MAC_EPOCH + timedelta(seconds=seconds)


def datetime_to_mac_timestamp(dt: datetime) -> int:
    """Convert Python datetime to Mac nanosecond timestamp."""
    delta = dt - MAC_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


def parse_attributed_body(blob: Optional[bytes]) -> str:
    """Parse attributedBody blob to extract text.

    The attributedBody is a binary plist containing NSAttributedString data.
    The text content follows the 'NSString' marker in the blob.
    """
    if not blob:
        return ""

    try:
        # Find NSString marker and extract text
        parts = blob.split(b"NSString")
        if len(parts) <= 1:
            return ""

        content = parts[1]
        if len(content) < 2:
            return ""

        # Skip initial bytes and find the length
        # The format varies, but typically has a length prefix
        start = 5
        if len(content) <= start:
            return ""

        # Check if length is stored as 2 bytes (0x81 prefix) or 1 byte
        if content[0] == 0x81:  # 129 - two byte length
            if len(content) < 3:
                return ""
            length = int.from_bytes(content[1:3], "little")
            start = 3
        else:
            length = content[0]
            start = 1

        if len(content) < start + length:
            return ""

        return content[start : start + length].decode("utf-8", errors="ignore")
    except (IndexError, ValueError):
        return ""


def _get_attachment_placeholder(mime_type: Optional[str]) -> str:
    """Get placeholder text for an attachment based on its MIME type."""
    if not mime_type:
        return "Look at this file"

    if mime_type.startswith("image/"):
        return "Look at this photo"
    elif mime_type.startswith("video/"):
        return "Look at this video"
    elif mime_type.startswith("audio/"):
        return "Listen to this audio"
    else:
        return "Look at this file"


def _reformat_url_message(text: str) -> str:
    """Reformat message containing URLs for speech.

    If the message is primarily a URL, prefix with "Hey, check this out:"
    """
    # URL pattern
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)

    if not urls:
        return text

    # Check if the message is primarily just URLs
    text_without_urls = re.sub(url_pattern, '', text).strip()

    if not text_without_urls:
        # Message is only URLs
        return "Hey, check this out: " + " ".join(urls)
    elif text_without_urls in ["Check out", "check out", "Look at this", "look at this"]:
        # Already has a prefix, just ensure URL is included
        return text
    else:
        # Has other text with URL embedded - keep as is but could enhance
        return text


def list_group_chats(db_path: Path) -> List[GroupChat]:
    """List all group chats in the iMessage database."""
    query = """
        SELECT
            c.ROWID as chat_id,
            COALESCE(c.display_name, 'Unnamed Group') as display_name,
            GROUP_CONCAT(h.id, '; ') as participants,
            COUNT(DISTINCT h.ROWID) as participant_count
        FROM chat c
        JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
        JOIN handle h ON h.ROWID = chj.handle_id
        GROUP BY c.ROWID
        HAVING COUNT(DISTINCT h.ROWID) > 1
        ORDER BY c.display_name
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

    chats = []
    for row in rows:
        chat_id, display_name, participants_str, participant_count = row
        participants = participants_str.split("; ") if participants_str else []
        chats.append(
            GroupChat(
                chat_id=chat_id,
                display_name=display_name,
                participant_count=participant_count,
                participants=participants,
            )
        )

    return chats


def extract_messages(
    db_path: Path,
    chat_id: int,
    start_date: datetime,
    end_date: datetime,
) -> List[Message]:
    """Extract messages from a group chat within a date range.

    Handles:
    - Date range filtering
    - Reaction filtering (excludes tapbacks)
    - Attachment placeholder text
    - URL reformatting
    - Thread reordering (replies appear after parent)
    """
    start_ts = datetime_to_mac_timestamp(start_date)
    end_ts = datetime_to_mac_timestamp(end_date)

    # Query messages with sender info and attachment info
    query = """
        SELECT
            m.ROWID as message_id,
            m.guid,
            m.text,
            m.attributedBody,
            m.date,
            m.is_from_me,
            m.cache_has_attachments,
            m.thread_originator_guid,
            CASE
                WHEN m.is_from_me = 1 THEN 'Me'
                ELSE COALESCE(h.id, 'Unknown')
            END as sender,
            (SELECT a.mime_type
             FROM attachment a
             JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID
             WHERE maj.message_id = m.ROWID
             LIMIT 1) as attachment_mime_type
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE cmj.chat_id = ?
          AND m.associated_message_type = 0
          AND m.date >= ?
          AND m.date < ?
        ORDER BY m.date ASC
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (chat_id, start_ts, end_ts))
        rows = cursor.fetchall()

    # Parse messages
    messages_by_guid: Dict[str, Message] = {}
    messages: List[Message] = []

    for row in rows:
        (
            message_id,
            guid,
            text,
            attributed_body,
            date,
            is_from_me,
            has_attachments,
            thread_originator_guid,
            sender,
            attachment_mime_type,
        ) = row

        # Get text from text field or attributedBody
        message_text = text
        if not message_text and attributed_body:
            message_text = parse_attributed_body(attributed_body)

        # Handle attachment-only messages
        if has_attachments and not message_text:
            message_text = _get_attachment_placeholder(attachment_mime_type)
        elif has_attachments and message_text:
            # Has both text and attachment
            placeholder = _get_attachment_placeholder(attachment_mime_type)
            message_text = f"{message_text}... and here's a {placeholder.split()[-1]}"

        # Reformat URLs
        if message_text:
            message_text = _reformat_url_message(message_text)

        msg = Message(
            sender=sender,
            text=message_text,
            timestamp=convert_mac_timestamp(date),
            guid=guid,
            thread_originator_guid=thread_originator_guid,
            has_attachment=bool(has_attachments),
            attachment_type=attachment_mime_type,
        )

        messages_by_guid[guid] = msg
        messages.append(msg)

    # Reorder to place thread replies after their parent
    result = _reorder_threads(messages, messages_by_guid)

    return result


def _reorder_threads(
    messages: List[Message], messages_by_guid: Dict[str, Message]
) -> List[Message]:
    """Reorder messages so thread replies appear immediately after their parent."""
    # Group replies by their parent guid
    replies_by_parent: Dict[str, List[Message]] = {}
    main_messages: List[Message] = []
    reply_guids: set = set()

    for msg in messages:
        if msg.thread_originator_guid and msg.thread_originator_guid in messages_by_guid:
            parent_guid = msg.thread_originator_guid
            if parent_guid not in replies_by_parent:
                replies_by_parent[parent_guid] = []
            replies_by_parent[parent_guid].append(msg)
            reply_guids.add(msg.guid)
        else:
            main_messages.append(msg)

    # Sort replies by timestamp within each thread
    for parent_guid in replies_by_parent:
        replies_by_parent[parent_guid].sort(key=lambda m: m.timestamp)

    # Build result: for each main message, insert its replies right after
    result: List[Message] = []
    for msg in main_messages:
        result.append(msg)
        if msg.guid in replies_by_parent:
            result.extend(replies_by_parent[msg.guid])

    return result
