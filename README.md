# Garmin Plan Uploader

A Python CLI tool to upload CSV training plans to Garmin Connect. This tool parses training plans in a human-readable CSV format and uploads them as structured workouts to your Garmin Connect calendar.

## Features

### Upload & Manage Training Plans
- 📅 **CSV-based training plans** - Define workouts in an easy-to-read spreadsheet format
- 🔐 **Secure authentication** - Token caching prevents rate limiting; supports MFA
- 🏃 **Running workout support** - Full support for warmup, cooldown, intervals, repeats
- 🎯 **Targets** - Heart rate zones (z1-z5) and pace ranges
- ⏱️ **Flexible durations** - Time-based (mm:ss), distance-based (km/mi/m), or lap-button
- 🔄 **Nested repeats** - Support for complex interval structures
- 📝 **Step notes** - Add notes to any step that appear in Garmin Connect
- 📋 **List workouts** - View scheduled workouts from your Garmin calendar
- 🗑️ **Bulk delete** - Clear scheduled workouts from a date range before re-uploading
- 📊 **Progress tracking** - Rich CLI with progress bars and colored output

### Download & Export
- 📥 **Download activities** - Export completed activities with JSON metadata, FIT files, and GPX tracks
- 🏷️ **Activity filtering** - Filter downloads by activity type (running, cycling, etc.)
- 📂 **Organized exports** - Activities saved to date-named folders with consistent naming

### Template Management
- 📚 **List templates** - View all workout templates in your Garmin library
- 🧹 **Bulk cleanup** - Safely delete unused workout templates (protects scheduled ones)
- 🔍 **Smart filtering** - Filter templates by name for targeted cleanup

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/tylerelias/garmin-connect-workout.git
cd garmin-connect-workout

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode
pip install -e .
```

### Dependencies

- Python 3.11+
- garminconnect (Garmin Connect API client)
- pydantic (Data validation)
- pandas (CSV parsing)
- typer (CLI framework)
- rich (Terminal formatting)

## Usage

### Basic Upload

```bash
garmin-plan-uploader upload training_plan.csv --start-date 2024-01-15
```

### With Credentials

```bash
garmin-plan-uploader upload plan.csv --start-date 2024-01-15 -u your@email.com -p yourpassword
```

### Using Environment Variables

```bash
export GARMIN_USERNAME="your@email.com"
export GARMIN_PASSWORD="yourpassword"
garmin-plan-uploader upload plan.csv --start-date 2024-01-15
```

### Dry Run (Validate Only)

```bash
garmin-plan-uploader upload plan.csv --start-date 2024-01-15 --dry-run
```

### Validate CSV Format

```bash
garmin-plan-uploader validate plan.csv --verbose
```

### Clear Cached Tokens

```bash
garmin-plan-uploader logout
```

### Delete Scheduled Workouts

Clear all scheduled workouts from a date range before re-uploading an updated plan:

```bash
# Preview what would be deleted (dry-run)
garmin-plan-uploader delete-range 2025-01-06 2025-03-31 --dry-run

# Delete with confirmation prompt
garmin-plan-uploader delete-range 2025-01-06 2025-03-31

# Delete without confirmation
garmin-plan-uploader delete-range 2025-01-06 2025-03-31 --yes
```

This removes workouts from your calendar but does **not** delete the underlying workout definitions.

### List Scheduled Workouts

View all scheduled workouts in a date range:

```bash
# List all workouts in a date range
garmin-plan-uploader list 2026-03-01 2026-07-31

# Group workouts by week for easier viewing
garmin-plan-uploader list 2026-03-01 2026-07-31 --by-week
```

This is useful for reviewing your training plan without making any changes.

### Download Activities

Export completed activities with full metadata, original FIT files, and GPX tracks:

```bash
# Download all running activities from a date range
garmin-plan-uploader download --start-date 2025-11-01 --end-date 2025-12-01 --activity-type running

# Download all activity types
garmin-plan-uploader download --start-date 2025-11-01 --end-date 2025-12-01

# Also include scheduled (planned) workouts
garmin-plan-uploader download --start-date 2025-11-01 --end-date 2025-12-01 --include-planned
```

Downloads are saved to `workouts/{start}_{end}/activities/` with files named:
- `{date}_{name}.json` - Full activity metadata
- `{date}_{name}.zip` - Original FIT file  
- `{date}_{name}.gpx` - GPS track (if available)

### Manage Workout Templates

Over time, your Garmin workout library can accumulate hundreds of unused templates. These tools help you audit and clean them up:

```bash
# List all workout templates in your library
garmin-plan-uploader list-templates

# Filter templates by name
garmin-plan-uploader list-templates --name-contains "10K"

# Preview unused templates that would be deleted (safe - excludes scheduled ones)
garmin-plan-uploader delete-templates --all --dry-run

# Delete all unused templates (safe - won't affect your training plan)
garmin-plan-uploader delete-templates --all --yes

# Delete only templates containing specific text
garmin-plan-uploader delete-templates --name-contains "Old Plan" --yes

# DANGEROUS: Include templates scheduled for future workouts
garmin-plan-uploader delete-templates --all --include-scheduled --yes
```

**Safety features:**
- By default, only deletes templates with no future scheduled workouts
- Always use `--dry-run` first to preview what would be deleted
- Use `--include-scheduled` only if you want to also delete scheduled templates (orphans calendar entries)

## Common Workflows

### Update an Existing Training Plan

When you've made changes to your CSV and need to re-upload:

```bash
# 1. Delete the existing scheduled workouts
garmin-plan-uploader delete-range 2026-01-01 2026-07-31 --yes

# 2. Upload the updated plan
garmin-plan-uploader upload updated_plan.csv --start-date 2026-01-05
```

### Review Your Schedule Before Race Day

```bash
# See what's scheduled for race week and taper
garmin-plan-uploader list 2026-07-13 2026-07-25 --by-week
```

### Backup Your Training Data

Download all your completed runs for analysis or backup:

```bash
# Download a full training block
garmin-plan-uploader download \
  --start-date 2025-01-01 \
  --end-date 2025-06-30 \
  --activity-type running
```

This creates a folder with JSON metadata (for analysis in Python/R), FIT files (for upload to other platforms), and GPX tracks (for mapping).

### Clean Up Your Workout Library

After uploading many training plans, you may have hundreds of unused workout templates:

```bash
# See how many templates you have
garmin-plan-uploader list-templates

# Preview what can be safely deleted
garmin-plan-uploader delete-templates --all --dry-run

# Clean up unused templates (safe - keeps scheduled ones)
garmin-plan-uploader delete-templates --all --yes
```

### Add Individual Workouts

You can upload a small CSV with just a few workouts to add to your existing schedule without deleting anything.

## CSV Format

The CSV file should have the following structure:

| WEEK | Monday | Tuesday | Wednesday | Thursday | Friday | Saturday | Sunday |
|------|--------|---------|-----------|----------|--------|----------|--------|
| 1    | workout | workout | | workout | | workout | |
| 2    | workout | workout | | workout | | workout | |

### Workout Syntax

Each cell contains a workout definition:

```
<type>: <workout name>
- <step>: <duration> @<target>; <optional notes>
- note: Additional notes for the previous step
- repeat: <count>
  - <step>: <duration> @<target>
  - <step>: <duration> @<target>
- <step>: <duration>
```

### Workout Types

Currently supported:
- `running` - Running workouts

### Step Types

| Keyword | Description |
|---------|-------------|
| `warmup` | Warmup step |
| `cooldown` | Cooldown step |
| `run` | Running interval |
| `interval` | Same as run |
| `recover` | Recovery step |
| `rest` | Rest step |
| `repeat` | Repeat group (contains nested steps) |
| `other` | Cross-training (mapped to interval with note) |
| `stair` | Stair machine (mapped to interval with note) |
| `note` | Add notes to the previous step (see below) |

### Duration Formats

| Format | Example | Description |
|--------|---------|-------------|
| `mm:ss` | `15:00` | Time in minutes:seconds |
| `mmm:ss` | `225:00` | Extended time format (e.g., 3hr 45min) |
| `<n>km` | `5km` | Distance in kilometers |
| `<n>mi` | `3mi` | Distance in miles |
| `<n>m` | `1600m` | Distance in meters |
| `lap-button` | `lap-button` | Manual lap (user ends step) |

**Note:** You can also use distance for the entire workout (e.g., `- run: 46km`) for race simulations or ultra-distance training.

### Target Formats

| Format | Example | Description |
|--------|---------|-------------|
| `@z1` - `@z5` | `@z3` | Heart rate zone |
| `@mm:ss-mm:ss` | `@4:30-5:00` | Pace range (min/km) |
| `@mm:ss-mm:ssmpm` | `@7:00-7:30mpm` | Pace range (min/mile) |

### Step Notes

You can add notes to any step that will appear in the Garmin Connect app. There are two ways to add notes:

**Inline notes** (using semicolon):
```
- run: 5:00 @z4; Focus on cadence 180+
```

**Multi-line notes** (using `- note:`):
```
- run: 800m @z4
- note: Focus on form and quick turnover
- note: Keep shoulders relaxed
```

Notes are appended to the previous step's description field.

### Example Workout

```
running: 10K Intervals
- warmup: 15:00 @z2; Easy pace, loosen up
- repeat: 5
  - run: 3:00 @z4
  - note: Strong but controlled effort
  - recover: 2:00 @z1
- cooldown: 10:00 @z2
```

## Example Training Plan

See [`examples/training_plan.csv`](examples/training_plan.csv) for a complete 4-week training plan.

## Authentication

### First-Time Setup

On first run, you'll be prompted for your Garmin Connect credentials. Tokens are cached to `~/.garminconnect` for subsequent runs.

### Multi-Factor Authentication (MFA)

If your account has MFA enabled, you'll be prompted to enter the code from your authenticator app or email.

### Token Cache

Tokens are stored in `~/.garminconnect/` and are valid for approximately 1 year. Use `garmin-plan-uploader logout` to clear cached tokens.

## Error Handling

- **Individual workout failures** are logged but don't stop the batch upload
- **Rate limiting** is handled with automatic delays between API calls
- **Invalid CSV rows** are skipped with warnings

## Troubleshooting

### "Token expired" or authentication errors
```bash
garmin-plan-uploader logout
# Then run your command again - you'll be prompted for credentials
```

### Workouts not appearing in Garmin Connect
- Check that your `--start-date` is a Monday (the tool expects weeks to start on Monday)
- Verify the date format is `YYYY-MM-DD`
- Use `--dry-run` first to see what would be uploaded

### Rate limiting / Too many requests
The tool automatically adds delays between API calls. If you're still hitting limits, wait a few minutes and try again.

### MFA issues
If you have Multi-Factor Authentication enabled, you'll be prompted for a code. Make sure to enter it quickly as codes expire.

## Using as a Python Library

You can also use the tool programmatically:

```python
from datetime import date
from garmin_plan_uploader.auth_manager import GarminSession
from garmin_plan_uploader.garmin_client import (
    get_scheduled_workouts_in_range,
    upload_and_schedule,
)
from garmin_plan_uploader.csv_parser import parse_workout_text

# Authenticate
session = GarminSession()
session.login()

# List scheduled workouts
workouts = get_scheduled_workouts_in_range(
    session, 
    date(2026, 3, 1), 
    date(2026, 7, 31)
)
for w in workouts:
    print(f"{w['date']}: {w['title']}")

# Download activities
from garmin_plan_uploader.garmin_client import download_activities_to_folder

download_activities_to_folder(
    session,
    date(2025, 11, 1),
    date(2025, 12, 1),
    "exports/november_runs",
    activity_type="running"
)

# Create and upload a single workout
workout_text = """running: Easy Recovery
- run: 30:00 @z1
- note: Keep it easy!"""

workout = parse_workout_text(workout_text)
workout_id = upload_and_schedule(session, workout, date(2026, 3, 15))
print(f"Uploaded workout ID: {workout_id}")
```

## Development

### Setup Development Environment

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

### Code Formatting

```bash
black src/
ruff check src/
```

## Architecture

```
src/garmin_plan_uploader/
├── __init__.py          # Package metadata
├── main.py              # CLI entry point (typer)
├── auth_manager.py      # Garmin authentication with token caching
├── csv_parser.py        # CSV and workout text parsing
├── garmin_client.py     # Garmin API operations
└── domain_models.py     # Pydantic models for workouts
```

## Credits

Inspired by [Raistlfiren/garmin-csv-plan](https://github.com/Raistlfiren/garmin-csv-plan), reimplemented in Python using the modern [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) library.

## License

MIT License - see [LICENSE](LICENSE) for details.
