"""Tests for iMessage database extraction."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from groupchat_podcast.imessage import (
    GroupChat,
    Message,
    convert_mac_timestamp,
    datetime_to_mac_timestamp,
    extract_messages,
    list_group_chats,
    parse_attributed_body,
)

# Mac epoch in UTC — this is the ground truth for iMessage timestamps
MAC_EPOCH_UTC = datetime(2001, 1, 1, tzinfo=timezone.utc)


class TestMacTimestampConversion:
    """Tests for Mac timestamp conversion."""

    def test_converts_known_timestamp(self):
        """Convert a known UTC Mac timestamp to local datetime."""
        # Mac timestamp for 2024-01-15 15:00:00 UTC
        target_utc = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        expected_local = target_utc.astimezone().replace(tzinfo=None)
        mac_ts = _utc_to_mac_nanos(target_utc)

        result = convert_mac_timestamp(mac_ts)

        assert result.year == expected_local.year
        assert result.month == expected_local.month
        assert result.day == expected_local.day
        assert result.hour == expected_local.hour
        assert result.minute == expected_local.minute

    def test_handles_zero_timestamp(self):
        """Zero timestamp should return Mac epoch (2001-01-01) in local time."""
        expected = datetime(2001, 1, 1, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        result = convert_mac_timestamp(0)

        assert result == expected


def _make_typedstream_blob(text_bytes: bytes) -> bytes:
    """Build a synthetic typedstream blob matching iMessage's attributedBody format.

    Format: streamtyped preamble + NSString + \x01\x94\x84\x01\x2b + length + text + \x86
    Length encoding: 0-127 = single byte, 128+ = \x81 + 2-byte LE uint16.
    """
    preamble = b"streamtyped\x00"
    ns_string = b"NSString"
    marker = b"\x01\x94\x84\x01\x2b"  # ends with + (0x2b)
    length = len(text_bytes)
    if length < 128:
        length_field = bytes([length])
    else:
        length_field = b"\x81" + length.to_bytes(2, "little")
    return preamble + ns_string + marker + length_field + text_bytes + b"\x86"


class TestParseAttributedBody:
    """Tests for parsing attributedBody blob."""

    def test_returns_empty_for_none(self):
        """None input returns empty string."""
        result = parse_attributed_body(None)
        assert result == ""

    def test_returns_empty_for_empty_bytes(self):
        """Empty bytes returns empty string."""
        result = parse_attributed_body(b"")
        assert result == ""

    def test_extracts_text_from_attributed_body(self):
        """Extract text from attributedBody blob format."""
        text = b"Hello"
        blob = _make_typedstream_blob(text)

        result = parse_attributed_body(blob)

        assert result == "Hello"

    def test_parses_exactly_127_chars(self):
        """127 chars is the max single-byte length — boundary value."""
        text = "A" * 127
        blob = _make_typedstream_blob(text.encode("utf-8"))

        result = parse_attributed_body(blob)

        assert result == text
        assert len(result) == 127

    def test_parses_128_chars(self):
        """128 chars requires multi-byte (0x81) length encoding."""
        text = "B" * 128
        blob = _make_typedstream_blob(text.encode("utf-8"))

        result = parse_attributed_body(blob)

        assert result == text
        assert len(result) == 128

    def test_parses_200_chars(self):
        """Typical medium message with 0x81 encoding."""
        text = "C" * 200
        blob = _make_typedstream_blob(text.encode("utf-8"))

        result = parse_attributed_body(blob)

        assert result == text
        assert len(result) == 200

    def test_parses_500_chars(self):
        """Longer message, still 0x81 encoding (max 65535)."""
        text = "D" * 500
        blob = _make_typedstream_blob(text.encode("utf-8"))

        result = parse_attributed_body(blob)

        assert result == text
        assert len(result) == 500

    def test_parses_multibyte_utf8_over_127_chars(self):
        """Multi-byte UTF-8: byte length > 127 even if char count is smaller.

        The typedstream length field is the byte length, not the character count.
        """
        # 50 emoji (each 4 bytes) = 200 bytes, but only 50 characters
        text = "\U0001f600" * 50
        text_bytes = text.encode("utf-8")
        assert len(text_bytes) == 200  # sanity: byte length > 127
        blob = _make_typedstream_blob(text_bytes)

        result = parse_attributed_body(blob)

        assert result == text
        assert len(result) == 50


class TestListGroupChats:
    """Tests for listing group chats."""

    def test_lists_group_chats(self, mock_chat_db):
        """List all group chats with participant info."""
        chats = list_group_chats(mock_chat_db)

        assert len(chats) >= 1
        chat = chats[0]
        assert isinstance(chat, GroupChat)
        assert chat.chat_id == 1
        assert chat.display_name == "Test Group Chat"
        assert chat.participant_count == 3

    def test_returns_empty_for_no_group_chats(self, tmp_path):
        """Return empty list when no group chats exist."""
        db_path = tmp_path / "empty.db"
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT, service TEXT);
            CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, guid TEXT, chat_identifier TEXT, display_name TEXT, room_name TEXT);
            CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
        """)
        conn.close()

        chats = list_group_chats(db_path)

        assert chats == []


class TestExtractMessages:
    """Tests for extracting messages from a group chat."""

    def test_extracts_messages_in_date_range(self, mock_chat_db):
        """Extract messages within the specified date range."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # Should include January messages but not February
        # Should exclude reactions (associated_message_type != 0)
        assert len(messages) >= 5  # msg1-6, msg8, minus reaction
        assert all(isinstance(m, Message) for m in messages)

    def test_filters_out_reactions(self, mock_chat_db):
        """Reactions (tapbacks) should not be included."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # No message should have associated_message_type != 0
        texts = [m.text for m in messages]
        assert not any("Loved" in (t or "") for t in texts)

    def test_attributes_sender_correctly(self, mock_chat_db):
        """Messages should have correct sender attribution."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # Find the "Hello everyone!" message
        hello_msg = next((m for m in messages if m.text == "Hello everyone!"), None)
        assert hello_msg is not None
        assert hello_msg.sender == "+15551234567"

        # Find the is_from_me message
        my_msg = next((m for m in messages if m.text == "I sent this!"), None)
        assert my_msg is not None
        assert my_msg.sender == "Me"

    def test_replaces_attachment_only_with_placeholder(self, mock_chat_db):
        """Messages with only attachments get placeholder text."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # Find the attachment-only message (msg5)
        # It should have placeholder text like "Look at this photo"
        attachment_msg = next(
            (m for m in messages if "photo" in (m.text or "").lower() or "image" in (m.text or "").lower()),
            None,
        )
        assert attachment_msg is not None

    def test_replaces_url_with_page_title_in_speech(self, mock_chat_db, mocker):
        """URLs in messages are replaced with the page title for natural speech."""
        mocker.patch(
            "groupchat_podcast.imessage._fetch_url_title",


            return_value="Cool Thing - Example Site",
        )
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # msg3: "Check out this link https://example.com/cool-thing"
        # Should become: "Check out this link: Cool Thing - Example Site"
        url_msg = next((m for m in messages if "Cool Thing" in (m.text or "")), None)
        assert url_msg is not None
        assert "https://" not in url_msg.text
        assert "Cool Thing - Example Site" in url_msg.text

    def test_url_only_message_gets_title(self, mock_chat_db, mocker):
        """A message that is just a URL becomes 'Check out this link: {title}'."""
        def mock_fetch(url):
            if "github.com" in url:
                return "some/repo: A cool project"
            return "Other Page"

        mocker.patch(
            "groupchat_podcast.imessage._fetch_url_title",


            side_effect=mock_fetch,
        )
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # msg10: "https://github.com/some/repo" - URL-only message
        url_msg = next((m for m in messages if "cool project" in (m.text or "").lower()), None)
        assert url_msg is not None
        assert "https://" not in url_msg.text
        assert "Check out this link:" in url_msg.text

    def test_falls_back_to_domain_when_title_fetch_fails(self, mock_chat_db, mocker):
        """When page title can't be fetched, falls back to the domain name."""
        mocker.patch(
            "groupchat_podcast.imessage._fetch_url_title",


            return_value=None,
        )
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # msg10: "https://github.com/some/repo" - should fall back to domain
        url_msg = next((m for m in messages if "github.com" in (m.text or "")), None)
        assert url_msg is not None
        assert "https://" not in url_msg.text
        assert "this link: github.com" in url_msg.text

    def test_orders_threads_after_parent(self, mock_chat_db):
        """Thread replies should appear immediately after their parent message."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # Find the parent message (msg1: "Hello everyone!")
        parent_idx = next(
            (i for i, m in enumerate(messages) if m.text == "Hello everyone!"),
            None,
        )
        assert parent_idx is not None

        # Find the reply (msg8: "This is a reply to the first message")
        reply_idx = next(
            (i for i, m in enumerate(messages) if "reply" in (m.text or "").lower()),
            None,
        )
        assert reply_idx is not None

        # Reply should come immediately after parent, not at its chronological position
        assert reply_idx == parent_idx + 1

    def test_excludes_messages_outside_date_range(self, mock_chat_db):
        """Messages outside the date range should not be included."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        # February message should not be included
        texts = [m.text for m in messages]
        assert not any("February" in (t or "") for t in texts)

    def test_keeps_short_messages(self, mock_chat_db):
        """Short messages like 'lol' should be kept."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        messages = extract_messages(mock_chat_db, chat_id=1, start_date=start, end_date=end)

        texts = [m.text for m in messages]
        assert "lol" in texts


def _utc_to_mac_nanos(dt_utc: datetime) -> int:
    """Convert a UTC datetime to Mac nanosecond timestamp (ground truth)."""
    delta = dt_utc - MAC_EPOCH_UTC
    return int(delta.total_seconds() * 1_000_000_000)


def _make_utc_chat_db(tmp_path, messages_utc):
    """Create a mock chat.db with messages at known UTC timestamps.

    messages_utc: list of (guid, text, utc_datetime) tuples
    """
    db_path = tmp_path / "tz_chat.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, service TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, guid TEXT UNIQUE NOT NULL,
            chat_identifier TEXT, display_name TEXT, room_name TEXT);
        CREATE TABLE message (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, guid TEXT UNIQUE NOT NULL,
            text TEXT, attributedBody BLOB, handle_id INTEGER, date INTEGER, is_from_me INTEGER DEFAULT 0,
            cache_has_attachments INTEGER DEFAULT 0, associated_message_type INTEGER DEFAULT 0,
            associated_message_guid TEXT, thread_originator_guid TEXT);
        CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
        CREATE TABLE attachment (ROWID INTEGER PRIMARY KEY AUTOINCREMENT, guid TEXT,
            filename TEXT, mime_type TEXT, transfer_name TEXT);
        CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
    """)
    cur.execute("INSERT INTO handle (id, service) VALUES (?, ?)", ("+15550001111", "iMessage"))
    cur.execute("INSERT INTO chat (guid, chat_identifier, display_name) VALUES (?, ?, ?)",
                ("tz_chat", "tz_chat", "TZ Test Chat"))
    cur.execute("INSERT INTO chat_handle_join (chat_id, handle_id) VALUES (1, 1)")

    for i, (guid, text, utc_dt) in enumerate(messages_utc, start=1):
        mac_ts = _utc_to_mac_nanos(utc_dt)
        cur.execute(
            "INSERT INTO message (guid, text, handle_id, date, associated_message_type) VALUES (?, ?, 1, ?, 0)",
            (guid, text, mac_ts),
        )
        cur.execute("INSERT INTO chat_message_join (chat_id, message_id) VALUES (1, ?)", (i,))

    conn.commit()
    conn.close()
    return db_path


class TestTimezoneHandling:
    """Tests that local-time date ranges correctly query UTC-stored Mac timestamps."""

    def test_local_date_range_includes_messages_stored_as_utc(self, tmp_path):
        """A message at 2024-01-15 15:00 UTC should be found when querying
        with local time that corresponds to that UTC time.

        For example, in UTC-5, 15:00 UTC = 10:00 local. A query for
        local 09:00-11:00 should include it.
        """
        # Store a message at a known UTC time
        msg_utc = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        db_path = _make_utc_chat_db(tmp_path, [
            ("msg_tz1", "timezone test message", msg_utc),
        ])

        # Query using the LOCAL time equivalent
        # msg_utc in local time:
        msg_local = msg_utc.astimezone().replace(tzinfo=None)
        start_local = msg_local - timedelta(hours=1)
        end_local = msg_local + timedelta(hours=1)

        messages = extract_messages(db_path, chat_id=1, start_date=start_local, end_date=end_local)

        assert len(messages) == 1
        assert messages[0].text == "timezone test message"

    def test_message_timestamp_is_local_time(self, tmp_path):
        """convert_mac_timestamp should return local time, not UTC."""
        msg_utc = datetime(2024, 7, 4, 20, 0, 0, tzinfo=timezone.utc)
        expected_local = msg_utc.astimezone().replace(tzinfo=None)

        mac_ts = _utc_to_mac_nanos(msg_utc)
        result = convert_mac_timestamp(mac_ts)

        assert result.hour == expected_local.hour
        assert result.day == expected_local.day

    def test_datetime_to_mac_timestamp_accounts_for_utc_offset(self):
        """datetime_to_mac_timestamp should treat input as local time and
        produce the correct UTC-based Mac timestamp.

        Local midnight != UTC midnight (unless you're in UTC).
        """
        local_midnight = datetime(2024, 1, 15, 0, 0, 0)

        # What UTC time does local midnight correspond to?
        local_aware = local_midnight.astimezone()
        utc_equivalent = local_aware.astimezone(timezone.utc)
        expected_mac_ts = _utc_to_mac_nanos(utc_equivalent)

        actual_mac_ts = datetime_to_mac_timestamp(local_midnight)

        assert actual_mac_ts == expected_mac_ts

    def test_cross_midnight_utc_messages_not_lost(self, tmp_path):
        """Messages near midnight UTC should not be dropped when the local
        timezone causes the UTC boundary to fall inside the query range.

        Scenario: user in UTC-5 queries 2024-01-15 22:00 to 2024-01-16 02:00 local.
        That's 2024-01-16 03:00 to 07:00 UTC. A message at 05:00 UTC (midnight local)
        should be included.
        """
        # Message at 2024-01-16 05:00 UTC (= midnight local in UTC-5)
        msg_utc = datetime(2024, 1, 16, 5, 0, 0, tzinfo=timezone.utc)
        msg_local = msg_utc.astimezone().replace(tzinfo=None)

        db_path = _make_utc_chat_db(tmp_path, [
            ("msg_midnight", "midnight message", msg_utc),
        ])

        # Query: 2 hours before to 2 hours after in local time
        start_local = msg_local - timedelta(hours=2)
        end_local = msg_local + timedelta(hours=2)

        messages = extract_messages(db_path, chat_id=1, start_date=start_local, end_date=end_local)

        assert len(messages) == 1
        assert messages[0].text == "midnight message"
