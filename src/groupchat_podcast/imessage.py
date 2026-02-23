"""iMessage database extraction module."""

import functools
import re
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Mac epoch: January 1, 2001 UTC
MAC_EPOCH_UTC = datetime(2001, 1, 1, tzinfo=timezone.utc)

# Default database path
DEFAULT_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"


@dataclass
class GroupChat:
    """Represents an iMessage group chat."""

    chat_id: int
    display_name: str
    participant_count: int
    participants: List[str]
    last_message_date: Optional[datetime] = None


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
    """Convert Mac nanosecond timestamp (UTC) to local datetime."""
    if mac_timestamp == 0:
        return MAC_EPOCH_UTC.astimezone().replace(tzinfo=None)
    seconds = mac_timestamp / 1_000_000_000
    utc_dt = MAC_EPOCH_UTC + timedelta(seconds=seconds)
    return utc_dt.astimezone().replace(tzinfo=None)


def datetime_to_mac_timestamp(dt: datetime) -> int:
    """Convert local datetime to Mac nanosecond timestamp (UTC).

    Treats naive datetimes as local time.
    """
    if dt.tzinfo is None:
        dt = dt.astimezone()
    utc_dt = dt.astimezone(timezone.utc)
    delta = utc_dt - MAC_EPOCH_UTC
    return int(delta.total_seconds() * 1_000_000_000)


def parse_attributed_body(blob: Optional[bytes]) -> str:
    """Parse attributedBody blob to extract text.

    The attributedBody is a binary plist containing NSAttributedString data.
    The text content follows the 'NSString' marker in the blob, using Apple's
    typedstream variable-width integer encoding for the length field.
    """
    if not blob:
        return ""

    try:
        parts = blob.split(b"NSString")
        if len(parts) <= 1:
            return ""

        content = parts[1]

        # Find the + marker (0x2B) that precedes the length field
        plus_pos = content.find(b"\x2b")
        if plus_pos < 0:
            return ""

        length_start = plus_pos + 1
        if length_start >= len(content):
            return ""

        # Variable-width integer: 0-127 = single byte,
        # 0x81 = next 2 bytes LE (max 65535, covers all iMessage texts)
        marker = content[length_start]
        if marker == 0x81:
            if length_start + 3 > len(content):
                return ""
            length = int.from_bytes(content[length_start + 1 : length_start + 3], "little")
            text_start = length_start + 3
        elif marker < 128:
            length = marker
            text_start = length_start + 1
        else:
            return ""

        if length == 0 or text_start + length > len(content):
            return ""

        return content[text_start : text_start + length].decode("utf-8", errors="ignore")
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


@functools.lru_cache(maxsize=256)
def _fetch_url_title(url: str) -> Optional[str]:
    """Fetch the page title for a URL (og:title preferred, then <title>).

    Returns None on any failure (timeout, DNS, parse error, etc.).
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read(65536).decode("utf-8", errors="ignore")

        # Try og:title first (what iMessage link previews use)
        og_match = re.search(
            r'<meta\s[^>]*property=["\']og:title["\']\s[^>]*content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        if not og_match:
            og_match = re.search(
                r'<meta\s[^>]*content=["\']([^"\']+)["\']\s[^>]*property=["\']og:title["\']',
                html,
                re.IGNORECASE,
            )
        if og_match:
            return og_match.group(1).strip()

        # Fall back to <title> tag
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()

    except Exception:
        pass

    return None


def _reformat_url_message(text: str) -> str:
    """Replace URLs in a message with human-readable link titles for speech."""
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)

    if not urls:
        return text

    text_without_urls = re.sub(url_pattern, '', text).strip()

    # Resolve each URL to a readable name
    readable_parts = []
    for url in urls:
        title = _fetch_url_title(url)
        if not title:
            # Fall back to domain name
            domain = urllib.parse.urlparse(url).netloc
            if domain.startswith("www."):
                domain = domain[4:]
            title = domain
        readable_parts.append(title)

    if not text_without_urls:
        # Message was only URL(s)
        return "Check out this link: " + ", ".join(readable_parts)
    else:
        # Replace each URL inline with "this link: {title}"
        result = text
        for url, title in zip(urls, readable_parts):
            result = result.replace(url, "this link: " + title)
        return result


def list_group_chats(db_path: Path) -> List[GroupChat]:
    """List all group chats in the iMessage database, sorted by most recent message."""
    # Get basic chat info with participants
    chat_query = """
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
    """

    # Get last message date per chat
    last_msg_query = """
        SELECT cmj.chat_id, MAX(m.date) as last_date
        FROM chat_message_join cmj
        JOIN message m ON m.ROWID = cmj.message_id
        GROUP BY cmj.chat_id
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Get chat info
        cursor.execute(chat_query)
        chat_rows = cursor.fetchall()

        # Get last message dates (may fail if table doesn't exist in test DBs)
        last_msg_dates = {}  # type: Dict[int, int]
        try:
            cursor.execute(last_msg_query)
            for chat_id, last_date in cursor.fetchall():
                last_msg_dates[chat_id] = last_date
        except sqlite3.OperationalError:
            pass  # Table doesn't exist, no dates available

    chats = []
    for row in chat_rows:
        chat_id, display_name, participants_str, participant_count = row
        participants = participants_str.split("; ") if participants_str else []

        # Convert Mac timestamp to local datetime
        last_message_dt = None
        last_msg_date = last_msg_dates.get(chat_id)
        if last_msg_date:
            last_message_dt = convert_mac_timestamp(last_msg_date)

        chats.append(
            GroupChat(
                chat_id=chat_id,
                display_name=display_name,
                participant_count=participant_count,
                participants=participants,
                last_message_date=last_message_dt,
            )
        )

    # Sort by last message date (most recent first), None values last
    chats.sort(
        key=lambda c: (
            c.last_message_date is None,
            -(c.last_message_date.timestamp() if c.last_message_date else 0),
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
