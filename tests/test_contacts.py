"""Tests for macOS contacts resolution."""

import sqlite3
from pathlib import Path

import pytest

from groupchat_podcast.contacts import (
    build_contact_lookup,
    find_contact_dbs,
    normalize_phone,
    resolve_participants,
)


def _create_mock_addressbook(db_path: Path, contacts):
    """Create a mock AddressBook database with the given contacts.

    contacts: list of dicts with keys:
        first_name, last_name, organization, phones (list), emails (list)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE ZABCDRECORD (
            Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
            ZFIRSTNAME VARCHAR,
            ZLASTNAME VARCHAR,
            ZORGANIZATION VARCHAR
        );
        CREATE TABLE ZABCDPHONENUMBER (
            Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
            ZOWNER INTEGER,
            ZFULLNUMBER VARCHAR,
            FOREIGN KEY (ZOWNER) REFERENCES ZABCDRECORD(Z_PK)
        );
        CREATE TABLE ZABCDEMAILADDRESS (
            Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
            ZOWNER INTEGER,
            ZADDRESS VARCHAR,
            ZADDRESSNORMALIZED VARCHAR,
            FOREIGN KEY (ZOWNER) REFERENCES ZABCDRECORD(Z_PK)
        );
    """)

    for contact in contacts:
        cursor.execute(
            "INSERT INTO ZABCDRECORD (ZFIRSTNAME, ZLASTNAME, ZORGANIZATION) VALUES (?, ?, ?)",
            (contact.get("first_name"), contact.get("last_name"), contact.get("organization")),
        )
        record_pk = cursor.lastrowid

        for phone in contact.get("phones", []):
            cursor.execute(
                "INSERT INTO ZABCDPHONENUMBER (ZOWNER, ZFULLNUMBER) VALUES (?, ?)",
                (record_pk, phone),
            )

        for email in contact.get("emails", []):
            cursor.execute(
                "INSERT INTO ZABCDEMAILADDRESS (ZOWNER, ZADDRESS, ZADDRESSNORMALIZED) VALUES (?, ?, ?)",
                (record_pk, email, email.lower()),
            )

    conn.commit()
    conn.close()


@pytest.fixture
def contacts_dir(tmp_path):
    """Create a mock AddressBook Sources directory with one source DB."""
    sources_dir = tmp_path / "Sources"
    source_dir = sources_dir / "ABC-123-DEF"
    source_dir.mkdir(parents=True)
    db_path = source_dir / "AddressBook-v22.abcddb"

    _create_mock_addressbook(db_path, [
        {
            "first_name": "Alice",
            "last_name": "Johnson",
            "phones": ["+1 (555) 123-4567"],
            "emails": ["alice@example.com"],
        },
        {
            "first_name": "Bob",
            "last_name": "Smith",
            "phones": ["+15559876543"],
            "emails": ["Bob.Smith@Work.com"],
        },
    ])

    return sources_dir


class TestFindContactDbs:
    """Tests for discovering AddressBook source databases."""

    def test_finds_databases_in_sources_subdirectories(self, contacts_dir):
        """Finds AddressBook-v22.abcddb files inside Sources/*/."""
        dbs = find_contact_dbs(contacts_dir)
        assert len(dbs) == 1
        assert dbs[0].name == "AddressBook-v22.abcddb"

    def test_returns_empty_list_when_directory_missing(self, tmp_path):
        """Returns empty list when Sources directory doesn't exist."""
        dbs = find_contact_dbs(tmp_path / "nonexistent")
        assert dbs == []

    def test_finds_multiple_source_databases(self, tmp_path):
        """Finds databases from multiple account sources (iCloud, Google, etc.)."""
        sources_dir = tmp_path / "Sources"
        for source_id in ["icloud-source", "google-source"]:
            source_dir = sources_dir / source_id
            source_dir.mkdir(parents=True)
            _create_mock_addressbook(
                source_dir / "AddressBook-v22.abcddb",
                [{"first_name": source_id, "last_name": "Contact"}],
            )

        dbs = find_contact_dbs(sources_dir)
        assert len(dbs) == 2


class TestNormalizePhone:
    """Tests for phone number normalization."""

    def test_strips_formatting_characters(self):
        """Removes parentheses, spaces, dashes from phone numbers."""
        assert normalize_phone("+1 (555) 123-4567") == "15551234567"

    def test_strips_imessage_handle_suffix(self):
        """Removes (smsft), (smsft_or), (smsfp) suffixes from iMessage handles."""
        assert normalize_phone("+12014623963(smsft)") == "12014623963"
        assert normalize_phone("+12014623963(smsft_or)") == "12014623963"

    def test_handles_plain_e164_number(self):
        """E.164 format numbers pass through with just the + stripped."""
        assert normalize_phone("+15551234567") == "15551234567"

    def test_handles_international_numbers(self):
        """International numbers preserve all digits."""
        assert normalize_phone("+49 177 1789322") == "491771789322"


class TestBuildContactLookup:
    """Tests for building the phone/email to name lookup."""

    def test_resolves_phone_number_to_contact_name(self, contacts_dir):
        """Phone numbers in the DB map to 'FirstName LastName'."""
        dbs = find_contact_dbs(contacts_dir)
        lookup = build_contact_lookup(dbs)
        # Contacts DB has "+1 (555) 123-4567" which normalizes to "15551234567"
        assert lookup["15551234567"] == "Alice Johnson"

    def test_resolves_email_to_contact_name(self, contacts_dir):
        """Email addresses map to contact names (case-insensitive)."""
        dbs = find_contact_dbs(contacts_dir)
        lookup = build_contact_lookup(dbs)
        assert lookup["bob.smith@work.com"] == "Bob Smith"

    def test_merges_contacts_from_multiple_sources(self, tmp_path):
        """Contacts from multiple source databases are all included."""
        sources_dir = tmp_path / "Sources"

        source1 = sources_dir / "source-1"
        source1.mkdir(parents=True)
        _create_mock_addressbook(source1 / "AddressBook-v22.abcddb", [
            {"first_name": "Charlie", "last_name": "Day", "phones": ["+15550001111"]},
        ])

        source2 = sources_dir / "source-2"
        source2.mkdir(parents=True)
        _create_mock_addressbook(source2 / "AddressBook-v22.abcddb", [
            {"first_name": "Dee", "last_name": "Reynolds", "emails": ["dee@paddy.com"]},
        ])

        dbs = find_contact_dbs(sources_dir)
        lookup = build_contact_lookup(dbs)
        assert lookup["15550001111"] == "Charlie Day"
        assert lookup["dee@paddy.com"] == "Dee Reynolds"

    def test_handles_contact_with_only_first_name(self, tmp_path):
        """Contacts with no last name display just the first name."""
        sources_dir = tmp_path / "Sources" / "src"
        sources_dir.mkdir(parents=True)
        _create_mock_addressbook(sources_dir / "AddressBook-v22.abcddb", [
            {"first_name": "Madonna", "phones": ["+15550009999"]},
        ])

        dbs = find_contact_dbs(sources_dir.parent)
        lookup = build_contact_lookup(dbs)
        assert lookup["15550009999"] == "Madonna"

    def test_handles_contact_with_only_organization(self, tmp_path):
        """Contacts with no name fall back to organization."""
        sources_dir = tmp_path / "Sources" / "src"
        sources_dir.mkdir(parents=True)
        _create_mock_addressbook(sources_dir / "AddressBook-v22.abcddb", [
            {"organization": "PagerDuty", "phones": ["+18001234567"]},
        ])

        dbs = find_contact_dbs(sources_dir.parent)
        lookup = build_contact_lookup(dbs)
        assert lookup["18001234567"] == "PagerDuty"

    def test_returns_empty_lookup_for_empty_db_list(self):
        """No databases means empty lookup."""
        lookup = build_contact_lookup([])
        assert lookup == {}

    def test_skips_unreadable_database(self, tmp_path):
        """Gracefully skips databases that can't be opened."""
        dbs = [tmp_path / "nonexistent.abcddb"]
        lookup = build_contact_lookup(dbs)
        assert lookup == {}


class TestResolveParticipants:
    """Tests for resolving raw iMessage handles to display names."""

    def test_resolves_phone_handle_to_contact_name(self):
        """Phone number handle resolves to the matching contact name."""
        lookup = {"15551234567": "Alice Johnson"}
        result = resolve_participants(["+15551234567"], lookup)
        assert result["+15551234567"] == "Alice Johnson"

    def test_resolves_email_handle_to_contact_name(self):
        """Email handle resolves to the matching contact name."""
        lookup = {"alice@example.com": "Alice Johnson"}
        result = resolve_participants(["alice@example.com"], lookup)
        assert result["alice@example.com"] == "Alice Johnson"

    def test_falls_back_to_raw_handle_when_no_match(self):
        """Unrecognized handles return the raw identifier."""
        lookup = {}
        result = resolve_participants(["+15550000000"], lookup)
        assert result["+15550000000"] == "+15550000000"

    def test_me_passes_through_unchanged(self):
        """'Me' is never looked up and always returns 'Me'."""
        lookup = {"me": "Some Contact Named Me"}
        result = resolve_participants(["Me"], lookup)
        assert result["Me"] == "Me"

    def test_strips_imessage_suffix_before_lookup(self):
        """Handles with (smsft) suffixes are normalized before lookup."""
        lookup = {"12014623963": "Frank Reynolds"}
        result = resolve_participants(["+12014623963(smsft)"], lookup)
        assert result["+12014623963(smsft)"] == "Frank Reynolds"

    def test_email_lookup_is_case_insensitive(self):
        """Email matching ignores case."""
        lookup = {"alice@example.com": "Alice Johnson"}
        result = resolve_participants(["Alice@Example.COM"], lookup)
        assert result["Alice@Example.COM"] == "Alice Johnson"


class TestCLIDisplaysContactNames:
    """Tests for CLI showing resolved contact names during voice assignment."""

    def test_assign_voices_shows_contact_name_with_raw_id(self, mocker):
        """Voice assignment prompt shows 'Contact Name (raw_id)' when contact is resolved."""
        from groupchat_podcast.tts import Voice
        mock_tts = mocker.Mock()
        test_voice = Voice(voice_id="abc123", name="Adam", labels={})
        mock_tts.search_voices.return_value = [test_voice]

        mocker.patch("beaupy.prompt", return_value="Adam")
        mocker.patch("beaupy.select", return_value=test_voice)

        from groupchat_podcast.cli import assign_voices

        display_names = {"+15551234567": "Alice Johnson"}
        result = assign_voices(
            ["+15551234567"],
            mock_tts,
            display_names=display_names,
        )

        # Verify the prompt was called with the contact name
        import beaupy
        prompt_call = beaupy.prompt.call_args
        assert "Alice Johnson" in prompt_call[0][0]
        assert "+15551234567" in prompt_call[0][0]

        # Verify the voice map key is still the raw handle
        assert "+15551234567" in result

    def test_assign_voices_works_without_display_names(self, mocker):
        """Voice assignment works when display_names is not provided (backwards compat)."""
        from groupchat_podcast.tts import Voice
        mock_tts = mocker.Mock()
        test_voice = Voice(voice_id="abc123", name="Adam", labels={})
        mock_tts.search_voices.return_value = [test_voice]

        mocker.patch("beaupy.prompt", return_value="Adam")
        mocker.patch("beaupy.select", return_value=test_voice)

        from groupchat_podcast.cli import assign_voices

        result = assign_voices(["+15551234567"], mock_tts)

        assert "+15551234567" in result
