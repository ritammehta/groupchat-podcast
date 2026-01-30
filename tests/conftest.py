"""Test fixtures for groupchat-podcast."""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


# Mac epoch: January 1, 2001
MAC_EPOCH = datetime(2001, 1, 1)


def datetime_to_mac_timestamp(dt: datetime) -> int:
    """Convert Python datetime to Mac nanosecond timestamp."""
    delta = dt - MAC_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


@pytest.fixture
def mock_chat_db(tmp_path):
    """Create a mock iMessage database with test data."""
    db_path = tmp_path / "chat.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables matching iMessage schema
    cursor.executescript("""
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT,
            service TEXT
        );

        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            chat_identifier TEXT,
            display_name TEXT,
            room_name TEXT
        );

        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            text TEXT,
            attributedBody BLOB,
            handle_id INTEGER,
            date INTEGER,
            is_from_me INTEGER DEFAULT 0,
            cache_has_attachments INTEGER DEFAULT 0,
            associated_message_type INTEGER DEFAULT 0,
            associated_message_guid TEXT,
            thread_originator_guid TEXT,
            FOREIGN KEY (handle_id) REFERENCES handle(ROWID)
        );

        CREATE TABLE chat_handle_join (
            chat_id INTEGER,
            handle_id INTEGER,
            FOREIGN KEY (chat_id) REFERENCES chat(ROWID),
            FOREIGN KEY (handle_id) REFERENCES handle(ROWID)
        );

        CREATE TABLE chat_message_join (
            chat_id INTEGER,
            message_id INTEGER,
            FOREIGN KEY (chat_id) REFERENCES chat(ROWID),
            FOREIGN KEY (message_id) REFERENCES message(ROWID)
        );

        CREATE TABLE attachment (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT,
            filename TEXT,
            mime_type TEXT,
            transfer_name TEXT
        );

        CREATE TABLE message_attachment_join (
            message_id INTEGER,
            attachment_id INTEGER,
            FOREIGN KEY (message_id) REFERENCES message(ROWID),
            FOREIGN KEY (attachment_id) REFERENCES attachment(ROWID)
        );
    """)

    # Insert test handles (participants)
    cursor.executemany(
        "INSERT INTO handle (id, service) VALUES (?, ?)",
        [
            ("+15551234567", "iMessage"),
            ("+15559876543", "iMessage"),
            ("friend@email.com", "iMessage"),
        ],
    )

    # Insert test chat (group chat)
    cursor.execute(
        "INSERT INTO chat (guid, chat_identifier, display_name, room_name) VALUES (?, ?, ?, ?)",
        ("chat123", "chat123456", "Test Group Chat", "room123"),
    )

    # Link handles to chat
    cursor.executemany(
        "INSERT INTO chat_handle_join (chat_id, handle_id) VALUES (?, ?)",
        [(1, 1), (1, 2), (1, 3)],
    )

    # Insert test messages
    messages = [
        # Regular messages
        ("msg1", "Hello everyone!", None, 1, datetime(2024, 1, 15, 10, 0, 0), 0, 0, 0, None, None),
        ("msg2", "Hey! How's it going?", None, 2, datetime(2024, 1, 15, 10, 1, 0), 0, 0, 0, None, None),
        ("msg3", "Check out this link https://example.com/cool-thing", None, 3, datetime(2024, 1, 15, 10, 2, 0), 0, 0, 0, None, None),
        ("msg4", "lol", None, 1, datetime(2024, 1, 15, 10, 3, 0), 0, 0, 0, None, None),
        ("msg5", None, None, 2, datetime(2024, 1, 15, 10, 4, 0), 0, 1, 0, None, None),  # Attachment only
        ("msg6", "I sent this!", None, None, datetime(2024, 1, 15, 10, 5, 0), 1, 0, 0, None, None),  # is_from_me
        # Reaction (should be filtered out)
        ("msg7", 'Loved "Hello everyone!"', None, 2, datetime(2024, 1, 15, 10, 6, 0), 0, 0, 2000, "msg1", None),
        # Thread reply
        ("msg8", "This is a reply to the first message", None, 3, datetime(2024, 1, 16, 12, 0, 0), 0, 0, 0, None, "msg1"),
        # Message outside date range
        ("msg9", "This is from February", None, 1, datetime(2024, 2, 15, 10, 0, 0), 0, 0, 0, None, None),
    ]

    for msg in messages:
        guid, text, attr_body, handle_id, dt, is_from_me, has_attach, assoc_type, assoc_guid, thread_guid = msg
        mac_ts = datetime_to_mac_timestamp(dt)
        cursor.execute(
            """INSERT INTO message
               (guid, text, attributedBody, handle_id, date, is_from_me,
                cache_has_attachments, associated_message_type, associated_message_guid, thread_originator_guid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (guid, text, attr_body, handle_id, mac_ts, is_from_me, has_attach, assoc_type, assoc_guid, thread_guid),
        )

    # Link messages to chat
    cursor.executemany(
        "INSERT INTO chat_message_join (chat_id, message_id) VALUES (?, ?)",
        [(1, i) for i in range(1, 10)],
    )

    # Add attachment for msg5
    cursor.execute(
        "INSERT INTO attachment (guid, filename, mime_type, transfer_name) VALUES (?, ?, ?, ?)",
        ("attach1", "photo.jpg", "image/jpeg", "photo.jpg"),
    )
    cursor.execute(
        "INSERT INTO message_attachment_join (message_id, attachment_id) VALUES (?, ?)",
        (5, 1),
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def sample_audio_bytes():
    """Return valid MP3 bytes for testing using pydub."""
    import io
    import shutil

    # Skip if ffmpeg not available
    if not shutil.which("ffmpeg"):
        return b""

    from pydub import AudioSegment

    # Create a short silent audio segment (100ms)
    silent = AudioSegment.silent(duration=100)

    # Export to bytes
    buffer = io.BytesIO()
    silent.export(buffer, format="mp3")
    return buffer.getvalue()
