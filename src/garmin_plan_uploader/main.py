"""CLI entry point for garmin-plan-uploader.

This module provides the command-line interface for uploading CSV training
plans to Garmin Connect.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

from . import __version__
from .auth_manager import AuthenticationError, GarminSession, MFARequiredError
from .csv_parser import ParserError, parse_training_plan
from .garmin_client import (
    GarminClientError,
    WorkoutScheduleError,
    WorkoutUploadError,
    delete_scheduled_workouts_in_range,
    get_scheduled_workouts_in_range,
    upload_and_schedule,
)

# Initialize Typer app
app = typer.Typer(
    name="garmin-plan-uploader",
    help="Upload CSV training plans to Garmin Connect calendar.",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with Rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def parse_date(date_str: str) -> date:
    """Parse a date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise typer.BadParameter(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"garmin-plan-uploader version {__version__}")
        raise typer.Exit()


@app.command()
def upload(
    csv_file: Annotated[
        Path,
        typer.Argument(
            help="Path to the CSV training plan file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    start_date: Annotated[
        str,
        typer.Option(
            "--start-date",
            "-s",
            help="Start date for Week 1, Monday (YYYY-MM-DD format)",
        ),
    ],
    username: Annotated[
        Optional[str],
        typer.Option(
            "--username",
            "-u",
            help="Garmin Connect email/username",
            envvar="GARMIN_USERNAME",
        ),
    ] = None,
    password: Annotated[
        Optional[str],
        typer.Option(
            "--password",
            "-p",
            help="Garmin Connect password",
            envvar="GARMIN_PASSWORD",
            hide_input=True,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Parse CSV and show what would be uploaded without actually uploading",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose logging",
        ),
    ] = False,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Upload a CSV training plan to Garmin Connect.

    The CSV file should have columns for each day of the week (Monday through Sunday)
    and optionally a WEEK column. Each cell contains workout definitions in the
    format:

        running: Workout Name
        - warmup: 15:00 @z2
        - repeat: 4
          - run: 2:00 @z4
          - recover: 1:30 @z1
        - cooldown: 10:00

    Example usage:

        garmin-plan-uploader training_plan.csv --start-date 2024-01-15

    You can set credentials via environment variables:

        export GARMIN_USERNAME="your@email.com"
        export GARMIN_PASSWORD="yourpassword"
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    # Parse start date
    try:
        plan_start_date = parse_date(start_date)
    except typer.BadParameter as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]Garmin Plan Uploader[/bold blue] v{__version__}\n")

    # Step 1: Parse the CSV file
    console.print(f"[cyan]Parsing training plan:[/cyan] {csv_file}")

    try:
        workouts = parse_training_plan(csv_file, plan_start_date)
    except (ParserError, FileNotFoundError) as e:
        console.print(f"[red]Error parsing CSV:[/red] {e}")
        raise typer.Exit(1)

    if not workouts:
        console.print("[yellow]No workouts found in CSV file.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Found {len(workouts)} workouts to upload.[/green]\n")

    # Show preview table
    table = Table(title="Workout Schedule")
    table.add_column("Date", style="cyan")
    table.add_column("Day", style="blue")
    table.add_column("Workout Name", style="green")
    table.add_column("Steps", style="yellow", justify="right")

    for workout_date, workout in workouts:
        day_name = workout_date.strftime("%A")
        step_count = len(workout.steps)
        table.add_row(
            workout_date.isoformat(),
            day_name,
            workout.name,
            str(step_count),
        )

    console.print(table)
    console.print()

    if dry_run:
        console.print("[yellow]Dry run mode - no workouts uploaded.[/yellow]")
        raise typer.Exit(0)

    # Step 2: Authenticate with Garmin Connect
    console.print("[cyan]Authenticating with Garmin Connect...[/cyan]")

    session = GarminSession()

    try:
        # Try cached tokens first, then prompt for credentials if needed
        session.login(email=username, password=password)
        console.print(f"[green]Logged in as:[/green] {session.get_display_name()}\n")

    except MFARequiredError as e:
        # Handle MFA
        console.print("[yellow]Multi-Factor Authentication required.[/yellow]")
        console.print("Please check your authenticator app or email for the MFA code.\n")

        mfa_code = typer.prompt("Enter MFA code")

        try:
            session.complete_mfa(e.garmin_client, e.mfa_context, mfa_code.strip())
            console.print(f"[green]MFA verified. Logged in as:[/green] {session.get_display_name()}\n")
        except AuthenticationError as mfa_err:
            console.print(f"[red]MFA verification failed:[/red] {mfa_err}")
            raise typer.Exit(1)

    except AuthenticationError as e:
        if "Email and password required" in str(e):
            # Prompt for credentials interactively
            console.print("[yellow]No cached tokens found. Please enter your Garmin credentials.[/yellow]\n")

            if not username:
                username = typer.prompt("Garmin Email")
            if not password:
                password = typer.prompt("Garmin Password", hide_input=True)

            try:
                session.login(email=username, password=password, force_new_login=True)
                console.print(f"[green]Logged in as:[/green] {session.get_display_name()}\n")
            except MFARequiredError as e:
                console.print("[yellow]Multi-Factor Authentication required.[/yellow]")
                mfa_code = typer.prompt("Enter MFA code")
                try:
                    session.complete_mfa(e.garmin_client, e.mfa_context, mfa_code.strip())
                    console.print(f"[green]Logged in as:[/green] {session.get_display_name()}\n")
                except AuthenticationError as mfa_err:
                    console.print(f"[red]MFA verification failed:[/red] {mfa_err}")
                    raise typer.Exit(1)
            except AuthenticationError as login_err:
                console.print(f"[red]Authentication failed:[/red] {login_err}")
                raise typer.Exit(1)
        else:
            console.print(f"[red]Authentication failed:[/red] {e}")
            raise typer.Exit(1)

    # Step 3: Upload workouts with progress bar
    console.print("[cyan]Uploading workouts to Garmin Connect...[/cyan]\n")

    success_count = 0
    error_count = 0
    errors: list[tuple[date, str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Uploading...", total=len(workouts))

        for workout_date, workout in workouts:
            progress.update(
                task,
                description=f"[cyan]{workout_date}[/cyan] - {workout.name[:30]}...",
            )

            try:
                workout_id = upload_and_schedule(session, workout, workout_date)
                success_count += 1
                logger.debug(f"Uploaded {workout.name} ({workout_id}) to {workout_date}")

            except (WorkoutUploadError, WorkoutScheduleError, GarminClientError) as e:
                error_count += 1
                error_msg = str(e)
                errors.append((workout_date, workout.name, error_msg))
                logger.error(f"Failed to upload {workout.name}: {e}")
                # Continue to next workout - don't crash the batch

            progress.advance(task)

    # Summary
    console.print()
    console.print("[bold]Upload Summary:[/bold]")
    console.print(f"  [green]✓ Successful:[/green] {success_count}")

    if error_count > 0:
        console.print(f"  [red]✗ Failed:[/red] {error_count}")
        console.print()
        console.print("[bold red]Errors:[/bold red]")
        for err_date, err_name, err_msg in errors:
            console.print(f"  • {err_date} - {err_name}: {err_msg}")

    if success_count > 0:
        console.print()
        console.print("[bold green]Training plan uploaded successfully![/bold green]")
        console.print("Check your Garmin Connect calendar to see the scheduled workouts.")


@app.command()
def logout() -> None:
    """Clear cached Garmin Connect tokens.

    Use this command if you want to log in with a different account
    or if you're experiencing authentication issues.
    """
    session = GarminSession()
    session.logout()
    console.print("[green]Logged out and cleared cached tokens.[/green]")


@app.command()
def validate(
    csv_file: Annotated[
        Path,
        typer.Argument(
            help="Path to the CSV training plan file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    start_date: Annotated[
        str,
        typer.Option(
            "--start-date",
            "-s",
            help="Start date for Week 1, Monday (YYYY-MM-DD format)",
        ),
    ] = "2024-01-01",
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed workout information",
        ),
    ] = False,
) -> None:
    """Validate a CSV training plan without uploading.

    This command parses the CSV file and shows the workout schedule
    that would be created, useful for checking the file format before
    uploading.
    """
    setup_logging(verbose)

    try:
        plan_start_date = parse_date(start_date)
    except typer.BadParameter as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]Validating training plan:[/bold blue] {csv_file}\n")

    try:
        workouts = parse_training_plan(csv_file, plan_start_date)
    except (ParserError, FileNotFoundError) as e:
        console.print(f"[red]Validation failed:[/red] {e}")
        raise typer.Exit(1)

    if not workouts:
        console.print("[yellow]No workouts found in CSV file.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]✓ Valid CSV with {len(workouts)} workouts[/green]\n")

    # Show detailed table
    table = Table(title="Workout Schedule Preview")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Date", style="cyan")
    table.add_column("Day", style="blue")
    table.add_column("Workout", style="green")
    table.add_column("Steps", style="yellow", justify="right")

    for i, (workout_date, workout) in enumerate(workouts, 1):
        day_name = workout_date.strftime("%A")
        table.add_row(
            str(i),
            workout_date.isoformat(),
            day_name,
            workout.name,
            str(len(workout.steps)),
        )

    console.print(table)

    if verbose:
        console.print("\n[bold]Workout Details:[/bold]\n")
        for workout_date, workout in workouts:
            console.print(f"[cyan]{workout_date}[/cyan] - [green]{workout.name}[/green]")
            for j, step in enumerate(workout.steps, 1):
                if hasattr(step, "iterations"):
                    # RepeatStep
                    console.print(f"  {j}. Repeat x{step.iterations}")  # type: ignore
                    for k, nested in enumerate(step.steps, 1):  # type: ignore
                        console.print(f"      {k}. {nested.step_type_keyword}")  # type: ignore
                else:
                    # ExecutableStep
                    console.print(f"  {j}. {step.step_type_keyword}")  # type: ignore
            console.print()


@app.command()
def delete_range(
    start_date: Annotated[
        str,
        typer.Argument(
            help="Start date for deletion range (YYYY-MM-DD format, inclusive)",
        ),
    ],
    end_date: Annotated[
        str,
        typer.Argument(
            help="End date for deletion range (YYYY-MM-DD format, inclusive)",
        ),
    ],
    username: Annotated[
        Optional[str],
        typer.Option(
            "--username",
            "-u",
            help="Garmin Connect email/username",
            envvar="GARMIN_USERNAME",
        ),
    ] = None,
    password: Annotated[
        Optional[str],
        typer.Option(
            "--password",
            "-p",
            help="Garmin Connect password",
            envvar="GARMIN_PASSWORD",
            hide_input=True,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be deleted without actually deleting",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmation prompt and delete immediately",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose logging",
        ),
    ] = False,
) -> None:
    """Delete all scheduled workouts within a date range.

    This removes scheduled workouts from your Garmin Connect calendar
    but does NOT delete the underlying workout definitions. This is useful
    for clearing a date range before re-uploading an updated training plan.

    Example usage:

        garmin-plan-uploader delete-range 2025-01-06 2025-03-31

    To preview what would be deleted without actually deleting:

        garmin-plan-uploader delete-range 2025-01-06 2025-03-31 --dry-run

    To skip the confirmation prompt:

        garmin-plan-uploader delete-range 2025-01-06 2025-03-31 --yes
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    # Parse dates
    try:
        range_start = parse_date(start_date)
        range_end = parse_date(end_date)
    except typer.BadParameter as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if range_end < range_start:
        console.print("[red]Error:[/red] End date must be on or after start date")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]Garmin Plan Uploader[/bold blue] v{__version__}\n")
    console.print(f"[cyan]Date range:[/cyan] {range_start} to {range_end}\n")

    # Authenticate
    console.print("[cyan]Authenticating with Garmin Connect...[/cyan]")

    session = GarminSession()

    try:
        session.login(email=username, password=password)
        console.print(f"[green]Logged in as:[/green] {session.get_display_name()}\n")

    except MFARequiredError as e:
        console.print("[yellow]Multi-Factor Authentication required.[/yellow]")
        mfa_code = typer.prompt("Enter MFA code")
        try:
            session.complete_mfa(e.garmin_client, e.mfa_context, mfa_code.strip())
            console.print(f"[green]MFA verified. Logged in as:[/green] {session.get_display_name()}\n")
        except AuthenticationError as mfa_err:
            console.print(f"[red]MFA verification failed:[/red] {mfa_err}")
            raise typer.Exit(1)

    except AuthenticationError as e:
        if "Email and password required" in str(e):
            console.print("[yellow]No cached tokens found. Please enter your Garmin credentials.[/yellow]\n")

            if not username:
                username = typer.prompt("Garmin Email")
            if not password:
                password = typer.prompt("Garmin Password", hide_input=True)

            try:
                session.login(email=username, password=password, force_new_login=True)
                console.print(f"[green]Logged in as:[/green] {session.get_display_name()}\n")
            except MFARequiredError as e:
                console.print("[yellow]Multi-Factor Authentication required.[/yellow]")
                mfa_code = typer.prompt("Enter MFA code")
                try:
                    session.complete_mfa(e.garmin_client, e.mfa_context, mfa_code.strip())
                    console.print(f"[green]Logged in as:[/green] {session.get_display_name()}\n")
                except AuthenticationError as mfa_err:
                    console.print(f"[red]MFA verification failed:[/red] {mfa_err}")
                    raise typer.Exit(1)
            except AuthenticationError as login_err:
                console.print(f"[red]Authentication failed:[/red] {login_err}")
                raise typer.Exit(1)
        else:
            console.print(f"[red]Authentication failed:[/red] {e}")
            raise typer.Exit(1)

    # Fetch scheduled workouts in the range
    console.print("[cyan]Fetching scheduled workouts...[/cyan]\n")

    try:
        workouts = get_scheduled_workouts_in_range(session, range_start, range_end)
    except GarminClientError as e:
        console.print(f"[red]Error fetching workouts:[/red] {e}")
        raise typer.Exit(1)

    if not workouts:
        console.print("[yellow]No scheduled workouts found in this date range.[/yellow]")
        raise typer.Exit(0)

    # Display workouts to be deleted
    console.print(f"[bold]Found {len(workouts)} scheduled workout(s):[/bold]\n")

    table = Table(title="Workouts to Delete")
    table.add_column("Date", style="cyan")
    table.add_column("Day", style="blue")
    table.add_column("Workout Name", style="green")
    table.add_column("Calendar ID", style="dim")

    for workout in sorted(workouts, key=lambda w: w.get("date", "")):
        workout_date_str = workout.get("date", "Unknown")
        title = workout.get("title", "Untitled")
        calendar_id = workout.get("id", "N/A")

        try:
            workout_date = date.fromisoformat(workout_date_str)
            day_name = workout_date.strftime("%A")
        except ValueError:
            day_name = "Unknown"

        table.add_row(workout_date_str, day_name, title, str(calendar_id))

    console.print(table)
    console.print()

    if dry_run:
        console.print("[yellow]Dry run mode - no workouts deleted.[/yellow]")
        raise typer.Exit(0)

    # Confirm deletion
    if not yes:
        confirm = typer.confirm(
            f"Delete {len(workouts)} scheduled workout(s)?",
            default=False,
        )
        if not confirm:
            console.print("[yellow]Deletion cancelled.[/yellow]")
            raise typer.Exit(0)

    # Delete workouts with progress
    console.print("\n[cyan]Deleting scheduled workouts...[/cyan]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Deleting...", total=len(workouts))
        deleted_count = 0
        error_count = 0

        for workout in sorted(workouts, key=lambda w: w.get("date", "")):
            calendar_id = workout.get("id")
            title = workout.get("title", "Untitled")
            workout_date_str = workout.get("date", "Unknown")

            progress.update(
                task,
                description=f"[cyan]{workout_date_str}[/cyan] - {title[:30]}...",
            )

            if calendar_id:
                try:
                    from .garmin_client import delete_scheduled_workout
                    delete_scheduled_workout(session, calendar_id)
                    deleted_count += 1
                    logger.debug(f"Deleted {title} ({workout_date_str})")
                except GarminClientError as e:
                    error_count += 1
                    logger.error(f"Failed to delete {title}: {e}")
            else:
                error_count += 1
                logger.warning(f"No calendar ID for {title}")

            progress.advance(task)

    # Summary
    console.print()
    console.print("[bold]Deletion Summary:[/bold]")
    console.print(f"  [green]✓ Deleted:[/green] {deleted_count}")

    if error_count > 0:
        console.print(f"  [red]✗ Failed:[/red] {error_count}")

    if deleted_count > 0:
        console.print()
        console.print("[bold green]Scheduled workouts deleted successfully![/bold green]")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
