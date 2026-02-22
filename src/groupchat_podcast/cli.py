"""Interactive CLI for podcast generation."""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from groupchat_podcast import __version__
from groupchat_podcast.imessage import DEFAULT_DB_PATH, extract_messages, list_group_chats
from groupchat_podcast.podcast import PodcastGenerator
from groupchat_podcast.tts import TTSClient

console = Console()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="groupchat-podcast",
        description="Convert iMessage group chats into podcast-style audio using ElevenLabs TTS.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help=f"Path to iMessage chat.db (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        default=None,
        help="Group chat ID (skips interactive selection)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path (default: podcast_YYYYMMDD_HHMMSS.mp3)",
    )
    return parser


def get_api_key() -> str:
    """Get ElevenLabs API key from environment or prompt."""
    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        console.print(
            "[yellow]No ELEVENLABS_API_KEY found in environment.[/yellow]"
        )
        api_key = Prompt.ask("Enter your ElevenLabs API key", password=True)

    return api_key


def select_group_chat(db_path: Path, page_size: int = 10) -> int:
    """Interactive group chat selection with pagination."""
    console.print("\n[bold]Scanning for group chats...[/bold]")

    try:
        chats = list_group_chats(db_path)
    except Exception as e:
        console.print(f"[red]Error reading iMessage database: {e}[/red]")
        console.print(
            "\n[yellow]Make sure you've granted Full Disk Access to your terminal.[/yellow]"
        )
        console.print(
            "Go to System Preferences > Security & Privacy > Privacy > Full Disk Access"
        )
        sys.exit(1)

    if not chats:
        console.print("[red]No group chats found![/red]")
        sys.exit(1)

    total_pages = (len(chats) + page_size - 1) // page_size
    current_page = 0

    while True:
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(chats))
        page_chats = chats[start_idx:end_idx]

        table = Table(title=f"Your Group Chats (Page {current_page + 1}/{total_pages})")
        table.add_column("#", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Participants", justify="right")
        table.add_column("Last Message", style="dim")

        for i, chat in enumerate(page_chats, start_idx + 1):
            last_msg = ""
            if chat.last_message_date:
                last_msg = chat.last_message_date.strftime("%Y-%m-%d")
            table.add_row(str(i), chat.display_name, str(chat.participant_count), last_msg)

        console.print(table)

        # Build prompt with navigation hints
        nav_hints = []
        if current_page > 0:
            nav_hints.append("'p' for previous")
        if current_page < total_pages - 1:
            nav_hints.append("'n' for next")

        prompt_text = "\nSelect a group chat (1-{})".format(len(chats))
        if nav_hints:
            prompt_text += " or " + ", ".join(nav_hints)

        choice = Prompt.ask(prompt_text, default="1")

        if choice.lower() == "n" and current_page < total_pages - 1:
            current_page += 1
            continue
        elif choice.lower() == "p" and current_page > 0:
            current_page -= 1
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(chats):
                selected = chats[idx]
                console.print(f"\n[green]Selected: {selected.display_name}[/green]")
                return selected.chat_id
            else:
                console.print("[red]Invalid selection. Try again.[/red]")
        except ValueError:
            console.print("[red]Please enter a number or navigation command.[/red]")


def get_date_range() -> Tuple[datetime, datetime]:
    """Interactive date range selection with optional time."""
    console.print("\n[bold]Date Range[/bold]")
    console.print("[dim]Format: YYYY-MM-DD or YYYY-MM-DD HH:MM[/dim]")

    # Default to last 30 days
    default_end = datetime.now()
    default_start = datetime(default_end.year, default_end.month, 1)

    def parse_datetime(s: str, is_end: bool = False) -> datetime:
        """Parse date or datetime string."""
        s = s.strip()
        # Try datetime with time first
        for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        # Try date only
        dt = datetime.strptime(s, "%Y-%m-%d")
        if is_end:
            # End date defaults to end of day
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt

    while True:
        start_str = Prompt.ask(
            "Start date",
            default=default_start.strftime("%Y-%m-%d"),
        )
        try:
            start_date = parse_datetime(start_str, is_end=False)
            break
        except ValueError:
            console.print("[red]Invalid format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM[/red]")

    while True:
        end_str = Prompt.ask(
            "End date",
            default=default_end.strftime("%Y-%m-%d"),
        )
        try:
            end_date = parse_datetime(end_str, is_end=True)
            break
        except ValueError:
            console.print("[red]Invalid format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM[/red]")

    if end_date < start_date:
        console.print("[yellow]End date is before start date. Swapping.[/yellow]")
        start_date, end_date = end_date, start_date

    console.print(f"[dim]Range: {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}[/dim]")

    return start_date, end_date


def assign_voices(
    participants: List[str],
    tts_client: TTSClient,
) -> Dict[str, str]:
    """Interactive voice assignment for participants."""
    console.print("\n[bold]Voice Assignment[/bold]")
    console.print("Assign an ElevenLabs voice ID to each participant.")
    console.print("Enter 'list' to search for voices, or paste a voice ID directly.\n")

    voice_map: Dict[str, str] = {}

    for participant in participants:
        while True:
            display_name = participant if participant != "Me" else "You (Me)"
            voice_input = Prompt.ask(f"  Voice for [cyan]{display_name}[/cyan]")

            if voice_input.lower() == "list":
                # Search for voices
                query = Prompt.ask("    Search voices")
                try:
                    voices = tts_client.search_voices(query)
                    if not voices:
                        console.print("    [yellow]No voices found.[/yellow]")
                        continue

                    console.print()
                    for v in voices[:10]:  # Show max 10
                        labels_str = ", ".join(f"{k}: {v}" for k, v in v.labels.items()) if v.labels else ""
                        console.print(f"    [green]{v.name}[/green] - {labels_str}")
                        console.print(f"      ID: [dim]{v.voice_id}[/dim]")
                    console.print()
                except Exception as e:
                    console.print(f"    [red]Error searching voices: {e}[/red]")
                continue

            if voice_input.strip():
                # Validate voice ID
                try:
                    voice = tts_client.get_voice(voice_input.strip())
                    console.print(f"    [green]✓ Using voice: {voice.name}[/green]")
                    voice_map[participant] = voice_input.strip()
                    break
                except Exception:
                    console.print(
                        f"    [red]Could not find voice with ID: {voice_input}[/red]"
                    )
                    console.print("    [yellow]Enter 'list' to search for voices.[/yellow]")
            else:
                console.print("    [red]Please enter a voice ID.[/red]")

    return voice_map


def get_output_path() -> Path:
    """Get output file path from user."""
    default_name = f"podcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"

    path_str = Prompt.ask(
        "\nOutput file path",
        default=default_name,
    )

    path = Path(path_str)

    # Add .mp3 extension if missing
    if path.suffix != ".mp3":
        path = path.with_suffix(".mp3")

    return path


def show_cost_estimate(
    generator: PodcastGenerator,
    db_path: Path,
    chat_id: int,
    start_date: datetime,
    end_date: datetime,
) -> bool:
    """Show cost estimate and confirm generation."""
    estimate = generator.estimate_cost(db_path, chat_id, start_date, end_date)

    panel = Panel(
        f"[bold]Messages:[/bold] {estimate['message_count']}\n"
        f"[bold]Characters:[/bold] {estimate['characters']:,}\n"
        f"[bold]Estimated cost:[/bold] ${estimate['estimated_cost']:.2f}",
        title="Cost Estimate",
        border_style="blue",
    )
    console.print(panel)

    return Confirm.ask("\nProceed with generation?", default=True)


def run_generation(
    generator: PodcastGenerator,
    db_path: Path,
    chat_id: int,
    start_date: datetime,
    end_date: datetime,
    output_path: Path,
) -> None:
    """Run podcast generation with progress display."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating podcast...", total=None)

        def on_progress(current: int, total: int, text: str):
            progress.update(
                task,
                description=f"[{current}/{total}] {text[:40]}...",
            )

        try:
            generator.generate(
                db_path=db_path,
                chat_id=chat_id,
                start_date=start_date,
                end_date=end_date,
                output_path=output_path,
                pause_ms=500,
                on_progress=on_progress,
            )
            progress.update(task, description="[green]Done![/green]")
        except Exception as e:
            progress.update(task, description=f"[red]Error: {e}[/red]")
            raise


def main():
    """Main CLI entry point."""
    try:
        args = build_parser().parse_args()

        console.print(
            Panel(
                "[bold blue]iMessage Group Chat to Podcast[/bold blue]\n\n"
                "Convert your group chat conversations into podcast-style audio!",
                border_style="blue",
            )
        )

        # Check for ffmpeg
        import shutil
        if not shutil.which("ffmpeg"):
            console.print(
                "[red]⚠ ffmpeg not found![/red]\n"
                "Audio processing requires ffmpeg. Install it with:\n"
                "  [cyan]brew install ffmpeg[/cyan] (macOS)\n"
            )
            if not Confirm.ask("Continue anyway?", default=False):
                sys.exit(1)

        # Get API key
        api_key = get_api_key()
        tts_client = TTSClient(api_key=api_key)

        # Check API key works
        console.print("\n[dim]Validating API key...[/dim]")
        try:
            tts_client.search_voices("")
            console.print("[green]✓ API key valid[/green]")
        except Exception as e:
            console.print(f"[red]Invalid API key: {e}[/red]")
            sys.exit(1)

        # Database path
        if args.db_path is not None:
            db_path = Path(args.db_path).expanduser()
        else:
            db_path = DEFAULT_DB_PATH

        if not db_path.exists():
            console.print(f"[red]iMessage database not found at {db_path}[/red]")
            if args.db_path is not None:
                console.print("[yellow]Check that the --db-path you provided is correct.[/yellow]")
            else:
                console.print(
                    "\n[yellow]Make sure you've granted Full Disk Access to your terminal.[/yellow]"
                )
            sys.exit(1)

        # Select group chat
        if args.chat_id is not None:
            chat_id = args.chat_id
        else:
            chat_id = select_group_chat(db_path)

        # Get date range
        if args.start_date is not None and args.end_date is not None:
            try:
                start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
                end_date = datetime.strptime(args.end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59,
                )
            except ValueError:
                console.print("[red]Invalid date format. Use YYYY-MM-DD.[/red]")
                sys.exit(1)
        elif args.start_date is not None or args.end_date is not None:
            console.print("[red]Both --start-date and --end-date must be provided together.[/red]")
            sys.exit(1)
        else:
            start_date, end_date = get_date_range()

        # Get participants for the chat
        messages = extract_messages(db_path, chat_id, start_date, end_date)

        if not messages:
            console.print("[yellow]No messages found in that date range.[/yellow]")
            sys.exit(0)

        # Count messages with actual text content
        text_messages = [m for m in messages if m.text and m.text.strip()]
        console.print(f"\n[green]Found {len(messages)} messages ({len(text_messages)} with text content).[/green]")

        # Get unique senders
        senders = sorted(set(m.sender for m in messages if m.sender))
        console.print(f"Participants: {', '.join(senders)}")

        # Assign voices
        voice_map = assign_voices(senders, tts_client)

        # Get output path
        if args.output is not None:
            output_path = Path(args.output)
            if output_path.suffix != ".mp3":
                output_path = output_path.with_suffix(".mp3")
        else:
            output_path = get_output_path()

        # Create generator
        generator = PodcastGenerator(tts_client=tts_client, voice_map=voice_map)

        # Show estimate and confirm
        if not show_cost_estimate(generator, db_path, chat_id, start_date, end_date):
            console.print("[yellow]Cancelled.[/yellow]")
            sys.exit(0)

        # Generate!
        console.print()
        run_generation(generator, db_path, chat_id, start_date, end_date, output_path)

        console.print(
            Panel(
                f"[bold green]Podcast saved to:[/bold green]\n{output_path.absolute()}",
                border_style="green",
            )
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Exiting.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
