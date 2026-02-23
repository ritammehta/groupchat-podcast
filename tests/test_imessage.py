"""Tests for iMessage database extraction."""

from datetime import datetime

import pytest

from groupchat_podcast.imessage import (
    GroupChat,
    Message,
    convert_mac_timestamp,
    extract_messages,
    list_group_chats,
    parse_attributed_body,
)


class TestMacTimestampConversion:
    """Tests for Mac timestamp conversion."""

    def test_converts_known_timestamp(self):
        """Convert a known Mac timestamp to datetime."""
        # Calculate the correct value:
        # From 2001-01-01 to 2024-01-15 10:00:00
        from datetime import datetime
        target = datetime(2024, 1, 15, 10, 0, 0)
        mac_epoch = datetime(2001, 1, 1)
        delta = target - mac_epoch
        mac_ts = int(delta.total_seconds() * 1_000_000_000)

        result = convert_mac_timestamp(mac_ts)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 0

    def test_handles_zero_timestamp(self):
        """Zero timestamp should return Mac epoch (2001-01-01)."""
        result = convert_mac_timestamp(0)

        assert result == datetime(2001, 1, 1, 0, 0, 0)


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
        # Build a blob that matches the NSString format the parser expects
        # Format: ...NSString<length_byte><text>...
        text = b"Hello"
        # The parser looks for NSString marker, then reads length byte + text
        blob = b"streamtyped\x00NSString" + bytes([len(text)]) + text

        result = parse_attributed_body(blob)

        assert result == "Hello"


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
