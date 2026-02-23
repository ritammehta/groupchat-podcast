"""Tests for CLI argument parsing and behavior."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from groupchat_podcast.cli import (
    build_parser,
    get_api_key,
    get_date_range,
    get_output_path,
    main,
    select_group_chat,
    show_cost_estimate,
)
from groupchat_podcast.imessage import GroupChat


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_parses_db_path(self):
        """--db-path flag is parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(["--db-path", "/custom/path/chat.db"])
        assert args.db_path == "/custom/path/chat.db"

    def test_parses_chat_id(self):
        """--chat-id flag is parsed as integer."""
        parser = build_parser()
        args = parser.parse_args(["--chat-id", "42"])
        assert args.chat_id == 42

    def test_parses_start_date(self):
        """--start-date flag is parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(["--start-date", "2024-01-15"])
        assert args.start_date == "2024-01-15"

    def test_parses_end_date(self):
        """--end-date flag is parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(["--end-date", "2024-01-31"])
        assert args.end_date == "2024-01-31"

    def test_parses_output_short_flag(self):
        """-o short flag works for output path."""
        parser = build_parser()
        args = parser.parse_args(["-o", "my_podcast.mp3"])
        assert args.output == "my_podcast.mp3"

    def test_parses_output_long_flag(self):
        """--output long flag works for output path."""
        parser = build_parser()
        args = parser.parse_args(["--output", "my_podcast.mp3"])
        assert args.output == "my_podcast.mp3"

    def test_all_flags_default_to_none(self):
        """All optional flags default to None when not provided."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.db_path is None
        assert args.chat_id is None
        assert args.start_date is None
        assert args.end_date is None
        assert args.output is None

    def test_version_flag_prints_version(self):
        """--version prints the version and exits."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0


class TestMainDbPath:
    """Tests for --db-path flag behavior in main()."""

    def test_uses_custom_db_path_to_find_chats(self, mock_chat_db, mocker, tmp_path):
        """main() reads from the custom --db-path database, not the default."""
        mocker.patch("sys.argv", [
            "groupchat-podcast", "--db-path", str(mock_chat_db),
            "-o", str(tmp_path / "out.mp3"),
        ])
        mocker.patch("groupchat_podcast.cli.get_api_key", return_value="test-key")
        mock_tts = mocker.Mock()
        mock_tts.search_voices.return_value = []
        mocker.patch("groupchat_podcast.cli.TTSClient", return_value=mock_tts)
        mocker.patch("groupchat_podcast.cli.select_group_chat", return_value=1)
        mocker.patch("groupchat_podcast.cli.get_date_range",
                     return_value=(datetime(2024, 1, 1), datetime(2024, 1, 31)))
        mocker.patch("groupchat_podcast.cli.assign_voices", return_value={"_default": "v1"})
        mocker.patch("groupchat_podcast.cli.show_cost_estimate", return_value=False)

        # The fact that main() doesn't crash with "database not found" proves
        # it used our mock_chat_db (which exists) instead of DEFAULT_DB_PATH
        # (which doesn't exist in test environments)
        with pytest.raises(SystemExit) as exc_info:
            main()
        # Exit 0 = cancelled at cost estimate, not exit 1 = db not found
        assert exc_info.value.code == 0

    def test_exits_with_error_for_nonexistent_custom_db_path(self, mocker):
        """main() exits with code 1 when --db-path points to nonexistent file."""
        mocker.patch("sys.argv", ["groupchat-podcast", "--db-path", "/nonexistent/chat.db"])
        mocker.patch("groupchat_podcast.cli.get_api_key", return_value="test-key")
        mock_tts = mocker.Mock()
        mock_tts.search_voices.return_value = []
        mocker.patch("groupchat_podcast.cli.TTSClient", return_value=mock_tts)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


class TestMainChatId:
    """Tests for --chat-id flag behavior in main()."""

    def test_proceeds_without_prompting_when_chat_id_provided(self, mock_chat_db, mocker, tmp_path):
        """When --chat-id is given, main() proceeds to date range without prompting for chat selection."""
        mocker.patch("sys.argv", [
            "groupchat-podcast",
            "--db-path", str(mock_chat_db),
            "--chat-id", "1",
            "--start-date", "2024-01-01",
            "--end-date", "2024-01-31",
            "-o", str(tmp_path / "out.mp3"),
        ])
        mocker.patch("groupchat_podcast.cli.get_api_key", return_value="test-key")
        mock_tts = mocker.Mock()
        mock_tts.search_voices.return_value = []
        mocker.patch("groupchat_podcast.cli.TTSClient", return_value=mock_tts)
        mocker.patch("groupchat_podcast.cli.assign_voices", return_value={"_default": "v1"})
        mocker.patch("groupchat_podcast.cli.show_cost_estimate", return_value=False)

        # If this reaches cost estimate and exits 0 (cancelled), it means
        # it successfully used chat_id=1 and dates without any interactive prompts
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


class TestMainDateFlags:
    """Tests for --start-date and --end-date flag behavior."""

    def test_uses_provided_dates_for_message_extraction(self, mock_chat_db, mocker, tmp_path):
        """When --start-date and --end-date are given, messages are extracted from that range."""
        mocker.patch("sys.argv", [
            "groupchat-podcast",
            "--db-path", str(mock_chat_db),
            "--chat-id", "1",
            "--start-date", "2024-02-01",
            "--end-date", "2024-02-28",
            "-o", str(tmp_path / "out.mp3"),
        ])
        mocker.patch("groupchat_podcast.cli.get_api_key", return_value="test-key")
        mock_tts = mocker.Mock()
        mock_tts.search_voices.return_value = []
        mocker.patch("groupchat_podcast.cli.TTSClient", return_value=mock_tts)

        # With Feb dates, the mock DB has only 1 message ("This is from February")
        # whereas Jan has many. If the dates are being used, we should see the Feb message
        # extracted. We can verify by checking it doesn't exit with "no messages" for Feb,
        # since there IS a Feb message in mock_chat_db
        mocker.patch("groupchat_podcast.cli.assign_voices", return_value={"_default": "v1"})
        mocker.patch("groupchat_podcast.cli.show_cost_estimate", return_value=False)

        with pytest.raises(SystemExit) as exc_info:
            main()
        # Exit 0 = reached cost estimate and cancelled, meaning messages were found
        assert exc_info.value.code == 0

    def test_exits_with_error_when_only_start_date_provided(self, mock_chat_db, mocker):
        """main() exits with error when --start-date is given without --end-date."""
        mocker.patch("sys.argv", [
            "groupchat-podcast",
            "--db-path", str(mock_chat_db),
            "--chat-id", "1",
            "--start-date", "2024-01-01",
        ])
        mocker.patch("groupchat_podcast.cli.get_api_key", return_value="test-key")
        mock_tts = mocker.Mock()
        mock_tts.search_voices.return_value = []
        mocker.patch("groupchat_podcast.cli.TTSClient", return_value=mock_tts)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_exits_with_error_for_invalid_date_format(self, mock_chat_db, mocker):
        """main() exits with error for malformed date strings."""
        mocker.patch("sys.argv", [
            "groupchat-podcast",
            "--db-path", str(mock_chat_db),
            "--chat-id", "1",
            "--start-date", "not-a-date",
            "--end-date", "2024-01-31",
        ])
        mocker.patch("groupchat_podcast.cli.get_api_key", return_value="test-key")
        mock_tts = mocker.Mock()
        mock_tts.search_voices.return_value = []
        mocker.patch("groupchat_podcast.cli.TTSClient", return_value=mock_tts)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


class TestMainOutputFlag:
    """Tests for --output flag behavior."""

    def test_writes_output_to_specified_path(self, mock_chat_db, mocker, tmp_path, sample_audio_bytes):
        """main() writes the podcast to the --output path."""
        output_file = tmp_path / "custom_output.mp3"
        mocker.patch("sys.argv", [
            "groupchat-podcast",
            "--db-path", str(mock_chat_db),
            "--chat-id", "1",
            "--start-date", "2024-01-01",
            "--end-date", "2024-01-31",
            "-o", str(output_file),
        ])
        mocker.patch("groupchat_podcast.cli.get_api_key", return_value="test-key")
        mock_tts = mocker.Mock()
        mock_tts.search_voices.return_value = []
        mock_tts.generate.return_value = sample_audio_bytes
        mocker.patch("groupchat_podcast.cli.TTSClient", return_value=mock_tts)
        mocker.patch("groupchat_podcast.cli.assign_voices", return_value={"_default": "voice-1"})
        mocker.patch("groupchat_podcast.cli.show_cost_estimate", return_value=True)

        main()

        assert output_file.exists()
        assert output_file.stat().st_size > 0


class TestKeyboardInterrupt:
    """Tests for graceful interrupt handling."""

    def test_exits_with_code_130_on_keyboard_interrupt(self, mocker):
        """main() exits with code 130 (SIGINT convention) on Ctrl+C."""
        mocker.patch("sys.argv", ["groupchat-podcast"])
        mocker.patch("groupchat_podcast.cli.get_api_key", side_effect=KeyboardInterrupt)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 130

    def test_no_traceback_on_keyboard_interrupt(self, mocker, capsys):
        """KeyboardInterrupt should produce a clean message, not a traceback."""
        mocker.patch("sys.argv", ["groupchat-podcast"])
        mocker.patch("groupchat_podcast.cli.get_api_key", side_effect=KeyboardInterrupt)

        with pytest.raises(SystemExit):
            main()

        captured = capsys.readouterr()
        assert "Traceback" not in captured.err


class TestSelectGroupChat:
    """Tests for interactive group chat selection via beaupy."""

    def test_returns_chat_id_of_selected_chat(self, mocker, tmp_path):
        """select_group_chat returns the chat_id of the chat the user picked."""
        chats = [
            GroupChat(chat_id=10, display_name="Family", participant_count=4, participants=["a", "b", "c", "d"]),
            GroupChat(chat_id=20, display_name="Work", participant_count=3, participants=["x", "y", "z"]),
        ]
        mocker.patch("groupchat_podcast.cli.list_group_chats", return_value=chats)
        mocker.patch("beaupy.select", return_value=chats[1])

        result = select_group_chat(tmp_path / "chat.db")

        assert result == 20

    def test_raises_keyboard_interrupt_on_escape(self, mocker, tmp_path):
        """select_group_chat raises KeyboardInterrupt when user presses Escape."""
        chats = [
            GroupChat(chat_id=10, display_name="Family", participant_count=4, participants=["a", "b", "c", "d"]),
        ]
        mocker.patch("groupchat_podcast.cli.list_group_chats", return_value=chats)
        mocker.patch("beaupy.select", return_value=None)

        with pytest.raises(KeyboardInterrupt):
            select_group_chat(tmp_path / "chat.db")


class TestGetApiKey:
    """Tests for API key retrieval via beaupy."""

    def test_prompts_securely_when_no_env_var(self, mocker):
        """get_api_key uses a secure prompt when ELEVENLABS_API_KEY is not set."""
        mocker.patch("groupchat_podcast.cli.load_dotenv")
        mocker.patch.dict("os.environ", {}, clear=True)
        mocker.patch("beaupy.prompt", return_value="sk-test-key-123")

        result = get_api_key()

        assert result == "sk-test-key-123"

    def test_raises_keyboard_interrupt_on_escape(self, mocker):
        """get_api_key raises KeyboardInterrupt when user presses Escape at prompt."""
        mocker.patch("groupchat_podcast.cli.load_dotenv")
        mocker.patch.dict("os.environ", {}, clear=True)
        mocker.patch("beaupy.prompt", return_value=None)

        with pytest.raises(KeyboardInterrupt):
            get_api_key()


class TestGetDateRange:
    """Tests for interactive date range selection via beaupy."""

    def test_returns_parsed_datetimes(self, mocker):
        """get_date_range parses user-provided date strings into datetimes."""
        mocker.patch("beaupy.prompt", side_effect=["2024-03-01", "2024-03-15"])

        start, end = get_date_range()

        assert start == datetime(2024, 3, 1)
        assert end == datetime(2024, 3, 15, 23, 59, 59)

    def test_raises_keyboard_interrupt_on_escape(self, mocker):
        """get_date_range raises KeyboardInterrupt when user presses Escape."""
        mocker.patch("beaupy.prompt", return_value=None)

        with pytest.raises(KeyboardInterrupt):
            get_date_range()


class TestGetOutputPath:
    """Tests for output path selection via beaupy."""

    def test_returns_path_from_user_input(self, mocker):
        """get_output_path returns a Path from what the user typed."""
        mocker.patch("beaupy.prompt", return_value="my_podcast.mp3")

        result = get_output_path()

        assert result == Path("my_podcast.mp3")

    def test_adds_mp3_extension_if_missing(self, mocker):
        """get_output_path appends .mp3 when user omits it."""
        mocker.patch("beaupy.prompt", return_value="my_podcast")

        result = get_output_path()

        assert result.suffix == ".mp3"

    def test_raises_keyboard_interrupt_on_escape(self, mocker):
        """get_output_path raises KeyboardInterrupt when user presses Escape."""
        mocker.patch("beaupy.prompt", return_value=None)

        with pytest.raises(KeyboardInterrupt):
            get_output_path()


class TestShowCostEstimate:
    """Tests for cost estimate confirmation via beaupy."""

    def test_returns_true_when_user_confirms(self, mocker):
        """show_cost_estimate returns True when user confirms generation."""
        mock_generator = mocker.Mock()
        mock_generator.estimate_cost.return_value = {
            "message_count": 10,
            "characters": 500,
            "estimated_cost": 0.05,
        }
        mocker.patch("beaupy.confirm", return_value=True)

        result = show_cost_estimate(
            mock_generator, Path("/fake/db"), 1,
            datetime(2024, 1, 1), datetime(2024, 1, 31),
        )

        assert result is True

    def test_returns_false_when_user_declines(self, mocker):
        """show_cost_estimate returns False when user declines generation."""
        mock_generator = mocker.Mock()
        mock_generator.estimate_cost.return_value = {
            "message_count": 10,
            "characters": 500,
            "estimated_cost": 0.05,
        }
        mocker.patch("beaupy.confirm", return_value=False)

        result = show_cost_estimate(
            mock_generator, Path("/fake/db"), 1,
            datetime(2024, 1, 1), datetime(2024, 1, 31),
        )

        assert result is False

    def test_raises_keyboard_interrupt_on_escape(self, mocker):
        """show_cost_estimate raises KeyboardInterrupt when user presses Escape."""
        mock_generator = mocker.Mock()
        mock_generator.estimate_cost.return_value = {
            "message_count": 10,
            "characters": 500,
            "estimated_cost": 0.05,
        }
        mocker.patch("beaupy.confirm", return_value=None)

        with pytest.raises(KeyboardInterrupt):
            show_cost_estimate(
                mock_generator, Path("/fake/db"), 1,
                datetime(2024, 1, 1), datetime(2024, 1, 31),
            )
