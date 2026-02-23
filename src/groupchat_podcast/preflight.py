"""Preflight prerequisite checks for groupchat-podcast."""

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    passed: bool
    message: str
    fix_instruction: Optional[str] = None


def check_platform() -> CheckResult:
    """Verify we're running on macOS."""
    if sys.platform == "darwin":
        return CheckResult(
            name="macOS",
            passed=True,
            message="Running on macOS",
        )
    return CheckResult(
        name="macOS",
        passed=False,
        message="This tool only works on macOS (it reads the iMessage database).",
        fix_instruction="Run this tool on a Mac with iMessage set up.",
    )


def check_ffmpeg() -> CheckResult:
    """Check if ffmpeg is installed and reachable."""
    # Check PATH first
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return CheckResult(
            name="ffmpeg",
            passed=True,
            message=f"Found at {ffmpeg_path}",
        )

    # Check common Homebrew locations (may not be on PATH for new terminal users)
    for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return CheckResult(
                name="ffmpeg",
                passed=True,
                message=f"Found at {candidate}",
            )

    # Not found anywhere
    has_brew = shutil.which("brew") is not None

    if has_brew:
        fix = (
            "Run this command in your terminal:\n"
            "\n"
            "    brew install ffmpeg\n"
            "\n"
            "Then restart your terminal and try again."
        )
    else:
        fix = (
            "First, install Homebrew (a package manager for macOS) by pasting this into your terminal:\n"
            "\n"
            '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n'
            "\n"
            "Then install ffmpeg:\n"
            "\n"
            "    brew install ffmpeg\n"
            "\n"
            "Then restart your terminal and try again."
        )

    return CheckResult(
        name="ffmpeg",
        passed=False,
        message="ffmpeg is not installed. It's needed to combine audio clips into a podcast.",
        fix_instruction=fix,
    )


def check_disk_access(db_path: Path) -> CheckResult:
    """Check if the iMessage database is accessible."""
    try:
        with open(db_path, "rb") as f:
            f.read(1)
        return CheckResult(
            name="iMessage Access",
            passed=True,
            message="Can read iMessage database",
        )
    except PermissionError as e:
        if "Operation not permitted" in str(e):
            return CheckResult(
                name="iMessage Access",
                passed=False,
                message="Your terminal doesn't have permission to read iMessage data.",
                fix_instruction=(
                    "You need to grant Full Disk Access to your terminal app:\n"
                    "\n"
                    "1. Open System Settings (click the Apple menu > System Settings)\n"
                    "2. Go to Privacy & Security > Full Disk Access\n"
                    "3. Toggle ON the switch for your terminal app (e.g., Terminal, iTerm2)\n"
                    "4. Restart your terminal and try again"
                ),
            )
        return CheckResult(
            name="iMessage Access",
            passed=False,
            message=f"Permission error: {e}",
            fix_instruction="Check file permissions on the iMessage database.",
        )
    except (FileNotFoundError, OSError):
        return CheckResult(
            name="iMessage Access",
            passed=False,
            message="iMessage database not found. Is Messages set up on this Mac?",
            fix_instruction=(
                "Open the Messages app and sign in with your Apple ID.\n"
                "Once you've sent or received at least one message, try again."
            ),
        )


def check_api_key() -> CheckResult:
    """Check if the ElevenLabs API key is available."""
    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")

    if api_key:
        return CheckResult(
            name="ElevenLabs API Key",
            passed=True,
            message="API key found",
        )

    return CheckResult(
        name="ElevenLabs API Key",
        passed=False,
        message="No ElevenLabs API key found.",
        fix_instruction=(
            "You need an ElevenLabs account to generate voice audio.\n"
            "\n"
            "1. Sign up at https://elevenlabs.io (free tier available)\n"
            "2. Go to your profile settings and copy your API key\n"
            "3. Create a file called .env in this folder with this line:\n"
            "\n"
            "    ELEVENLABS_API_KEY=your-key-here\n"
            "\n"
            "Or set it in your terminal:\n"
            "\n"
            "    export ELEVENLABS_API_KEY=your-key-here"
        ),
    )


def run_preflight(db_path: Path, console: Optional[Console] = None) -> bool:
    """Run all preflight checks and display results.

    Returns True if all checks pass, False otherwise.
    """
    if console is None:
        console = Console()

    results = [
        check_platform(),
        check_ffmpeg(),
        check_disk_access(db_path),
        check_api_key(),
    ]

    all_passed = all(r.passed for r in results)

    if all_passed:
        console.print("[green]All prerequisites met.[/green]\n")
        return True

    # Show a table of results with fix instructions for failures
    table = Table(title="Setup Checklist", show_lines=True, title_style="bold")
    table.add_column("Check", style="bold", width=20)
    table.add_column("Status", width=6)
    table.add_column("Details")

    for r in results:
        status = "[green]OK[/green]" if r.passed else "[red]FAIL[/red]"
        detail = r.message
        if not r.passed and r.fix_instruction:
            detail += f"\n\n[yellow]How to fix:[/yellow]\n{r.fix_instruction}"
        table.add_row(r.name, status, detail)

    console.print(Panel(table, border_style="red", title="[red]Setup Incomplete[/red]"))
    console.print(
        "\n[yellow]Fix the issues above and try again.[/yellow]\n"
        "[dim]Tip: You can skip these checks by providing --db-path if your "
        "database is in a non-standard location.[/dim]\n"
    )

    return False
