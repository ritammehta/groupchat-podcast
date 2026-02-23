"""Tests for preflight prerequisite checks."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from groupchat_podcast.preflight import (
    CheckResult,
    check_api_key,
    check_disk_access,
    check_ffmpeg,
    run_preflight,
)


class TestCheckFfmpeg:
    """Tests for ffmpeg detection."""

    def test_finds_ffmpeg_in_homebrew_path_when_not_on_PATH(self):
        """check_ffmpeg finds ffmpeg at /opt/homebrew/bin even if not on PATH."""
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", side_effect=lambda p: p == "/opt/homebrew/bin/ffmpeg"), \
             patch("os.access", return_value=True):
            result = check_ffmpeg()
        assert result.passed is True


class TestCheckDiskAccess:
    """Tests for Full Disk Access detection via file probing."""

    def test_passes_when_db_readable(self, tmp_path):
        """check_disk_access passes when the database file can be opened."""
        db_file = tmp_path / "chat.db"
        db_file.write_bytes(b"fake-db-content")
        result = check_disk_access(db_file)
        assert result.passed is True

    def test_fails_with_fda_instructions_on_operation_not_permitted(self, tmp_path):
        """check_disk_access fails with Full Disk Access instructions on PermissionError."""
        db_file = tmp_path / "chat.db"
        with patch("builtins.open", side_effect=PermissionError("Operation not permitted")):
            result = check_disk_access(db_file)
        assert result.passed is False
        assert "Full Disk Access" in result.fix_instruction
        assert "System Settings" in result.fix_instruction

    def test_fails_when_db_not_found(self, tmp_path):
        """check_disk_access fails with iMessage setup instructions when file missing."""
        db_file = tmp_path / "nonexistent" / "chat.db"
        result = check_disk_access(db_file)
        assert result.passed is False
        assert "iMessage" in result.message or "Messages" in result.message


class TestCheckApiKey:
    """Tests for ElevenLabs API key detection."""

    def test_passes_when_key_in_environment(self):
        """check_api_key passes when ELEVENLABS_API_KEY is set."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "sk-test-123"}):
            result = check_api_key()
        assert result.passed is True

    def test_fails_when_key_missing(self):
        """check_api_key fails with setup instructions when no key is found."""
        with patch.dict(os.environ, {}, clear=True), \
             patch("groupchat_podcast.preflight.load_dotenv"):
            result = check_api_key()
        assert result.passed is False
        assert result.fix_instruction is not None
        assert "elevenlabs.io" in result.fix_instruction.lower() or "ElevenLabs" in result.fix_instruction


class TestRunPreflight:
    """Tests for the aggregate preflight runner."""

    def test_returns_true_when_all_checks_pass(self, tmp_path, capsys):
        """run_preflight returns True when every check passes."""
        db_file = tmp_path / "chat.db"
        db_file.write_bytes(b"fake")

        with patch("groupchat_podcast.preflight.sys") as mock_sys, \
             patch("shutil.which", return_value="/usr/local/bin/ffmpeg"), \
             patch.dict(os.environ, {"ELEVENLABS_API_KEY": "sk-test"}):
            mock_sys.platform = "darwin"
            result = run_preflight(db_file)
        assert result is True

    def test_returns_false_when_any_check_fails(self, tmp_path):
        """run_preflight returns False and displays failures when a check fails."""
        db_file = tmp_path / "chat.db"
        db_file.write_bytes(b"fake")

        with patch("groupchat_podcast.preflight.sys") as mock_sys, \
             patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False), \
             patch.dict(os.environ, {"ELEVENLABS_API_KEY": "sk-test"}):
            mock_sys.platform = "darwin"
            result = run_preflight(db_file)
        assert result is False
