"""macOS Contacts resolution for iMessage handles."""

import re
import sqlite3
from pathlib import Path
from typing import Dict, List

CONTACTS_DIR = Path.home() / "Library" / "Application Support" / "AddressBook" / "Sources"


def find_contact_dbs(sources_dir: Path = CONTACTS_DIR) -> List[Path]:
    """Find all AddressBook source databases.

    macOS stores contacts in per-account source databases under
    ~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb
    """
    if not sources_dir.is_dir():
        return []
    return sorted(sources_dir.glob("*/AddressBook-v22.abcddb"))


def normalize_phone(number: str) -> str:
    """Normalize a phone number to digits only.

    Strips iMessage handle suffixes like (smsft), then removes all non-digit characters.
    """
    # Strip parenthetical suffixes from iMessage handles
    number = re.sub(r'\([^)]*\)$', '', number)
    # Keep only digits
    return re.sub(r'\D', '', number)


def _build_display_name(first_name, last_name, organization) -> str:
    """Build a display name from contact record fields."""
    parts = [p for p in (first_name, last_name) if p]
    name = " ".join(parts).strip()
    if name:
        return name
    if organization:
        return organization.strip()
    return ""


def build_contact_lookup(db_paths: List[Path]) -> Dict[str, str]:
    """Build a lookup from normalized phone numbers and emails to contact names.

    Reads all provided AddressBook databases and merges results.
    """
    lookup: Dict[str, str] = {}

    for db_path in db_paths:
        try:
            conn = sqlite3.connect(str(db_path))
        except (sqlite3.OperationalError, OSError):
            continue

        try:
            # Phone numbers
            rows = conn.execute("""
                SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, p.ZFULLNUMBER
                FROM ZABCDRECORD r
                JOIN ZABCDPHONENUMBER p ON r.Z_PK = p.ZOWNER
                WHERE p.ZFULLNUMBER IS NOT NULL
            """).fetchall()

            for first_name, last_name, organization, phone in rows:
                name = _build_display_name(first_name, last_name, organization)
                if name:
                    normalized = normalize_phone(phone)
                    if normalized:
                        lookup[normalized] = name

            # Email addresses
            rows = conn.execute("""
                SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, e.ZADDRESSNORMALIZED
                FROM ZABCDRECORD r
                JOIN ZABCDEMAILADDRESS e ON r.Z_PK = e.ZOWNER
                WHERE e.ZADDRESSNORMALIZED IS NOT NULL
            """).fetchall()

            for first_name, last_name, organization, email in rows:
                name = _build_display_name(first_name, last_name, organization)
                if name:
                    lookup[email.lower()] = name

        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    return lookup


def resolve_participants(
    participants: List[str], contact_lookup: Dict[str, str]
) -> Dict[str, str]:
    """Resolve raw iMessage handles to display names.

    Returns a dict mapping each raw handle to either a contact name or itself.
    """
    result: Dict[str, str] = {}

    for handle in participants:
        if handle == "Me":
            result[handle] = "Me"
            continue

        # Try phone lookup: starts with + or is digits (after stripping suffix)
        normalized = normalize_phone(handle)
        if normalized and normalized.isdigit():
            name = contact_lookup.get(normalized)
            if name:
                result[handle] = name
                continue

        # Try email lookup (case-insensitive)
        name = contact_lookup.get(handle.lower())
        if name:
            result[handle] = name
            continue

        # No match — fall back to raw handle
        result[handle] = handle

    return result
