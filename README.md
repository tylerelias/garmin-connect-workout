# Garmin Plan Uploader

A Python CLI tool to upload CSV training plans to Garmin Connect. This tool parses training plans in a human-readable CSV format and uploads them as structured workouts to your Garmin Connect calendar.

## Features

- 📅 **CSV-based training plans** - Define workouts in an easy-to-read spreadsheet format
- 🔐 **Secure authentication** - Token caching prevents rate limiting; supports MFA
- 🏃 **Running workout support** - Full support for warmup, cooldown, intervals, repeats
- 🎯 **Targets** - Heart rate zones (z1-z5) and pace ranges
- ⏱️ **Flexible durations** - Time-based (mm:ss), distance-based (km/mi), or lap-button
- 🔄 **Nested repeats** - Support for complex interval structures
- 📝 **Step notes** - Add notes to any step that appear in Garmin Connect
- 🗑️ **Bulk delete** - Clear scheduled workouts from a date range before re-uploading
- 📊 **Progress tracking** - Rich CLI with progress bars and colored output

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
| `mmm:ss` | `225:00` | Extended time format |
| `<n>km` | `5km` | Distance in kilometers |
| `<n>mi` | `3mi` | Distance in miles |
| `<n>m` | `1600m` | Distance in meters |
| `lap-button` | `lap-button` | Manual lap (user ends step) |

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
