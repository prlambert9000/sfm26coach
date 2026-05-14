# Strava Activity Sidecars

One JSON file per Strava activity. Immutable: once a sidecar is written, it isn't modified.
The bot (`scripts/pull_strava.py`) creates these; the coach reads them when authoring entries
in `WORKOUT_LOG.md`.

## File naming

`strava/activities/<activity_id>.json` where `<activity_id>` is Strava's integer activity ID.
Skipping by filename means re-running the puller is always safe.

## Schema

```jsonc
{
  "activity_id": 12345678901,
  "name": "Morning Run",
  "type": "Run",                     // Run / Walk / Hike (others are skipped)
  "start_local": "2026-05-14T06:23:00",
  "date": "2026-05-14",              // YYYY-MM-DD (for queries)
  "date_heading": "May 14, 2026",    // matches the WORKOUT_LOG.md "## " heading
  "distance_mi": 6.83,
  "moving_time_s": 3366,
  "elapsed_time_s": 3500,
  "avg_pace": "8:15/mi",
  "elevation_gain_ft": 282.0,
  "avg_hr": 152.3,
  "max_hr": 168.0,
  "avg_cadence_spm": 168,            // already doubled from Strava's per-foot value
  "avg_power_w": 229,
  "calories": 612,
  "suffer_score": 95,
  "description": "",
  "strava_url": "https://www.strava.com/activities/12345678901",
  "splits": [
    {
      "mile": 1,
      "distance_mi": 1.0,
      "moving_time_s": 483,
      "pace": "8:03",
      "avg_hr": 136.0,
      "elev_diff_ft": -131.0
    }
    // ...
  ],
  "hr_zones": [
    {"min": 0, "max": 122, "time_s": 60},
    {"min": 122, "max": 145, "time_s": 480}
    // Z1..Z5; min/max are BPM thresholds
  ],
  "fetched_at": "2026-05-14T15:30:00Z"
}
```

Fields may be `null` if Strava didn't supply them (e.g., no HR strap → `avg_hr` is null).

## How the coach uses these

When writing or updating a `WORKOUT_LOG.md` entry:

1. Find the sidecar(s) for that date: `ls strava/activities/ | xargs grep -l '"date": "2026-05-14"'`
   (or just open files modified recently).
2. Read the JSON to pull objective values into the narrative entry: avg HR, max HR, cadence,
   HR zones, exact total time, etc.
3. Write your analysis. Do not modify the JSON — it's the immutable source of truth.

## How the bot uses these

`scripts/pull_strava.py`:

- Pulls Strava activities from the last N days (default 3, configurable for backfill).
- For each runnable activity (`Run`/`Walk`/`Hike`): if a sidecar already exists for that ID,
  skip. Otherwise fetch the full detail + HR zones and write `<id>.json`.
- After sidecar writes: for any *date* not already present as a `## <Date>` heading in
  `WORKOUT_LOG.md`, append a minimal stub entry. If the date is already in the log, leave
  the markdown alone — the JSON is captured for the coach to fold in later.

## Backfill

Trigger via `workflow_dispatch` on the **Pull Strava Data** workflow with a `days` input,
e.g. `90` or `180`. Sidecars are immutable, so re-running is safe and idempotent.
