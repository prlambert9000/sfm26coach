#!/usr/bin/env python3
"""Pull Strava activities into per-activity JSON sidecars at strava/activities/<id>.json.

Architecture (locked May 14, 2026):
- Each Strava activity is captured as one immutable JSON file at strava/activities/<activity_id>.json.
  The file is the structured source of truth for objective workout data.
- WORKOUT_LOG.md remains the human-readable narrative log. The coach (or athlete) writes prose
  there, folding in numbers from the JSON sidecar when useful.
- This script only appends a minimal stub to WORKOUT_LOG.md for a date when no entry exists for
  that date yet. If an entry already exists, the script leaves the markdown alone — the JSON
  is captured for the coach to read on the next pass.

Run modes:
- Default: pull activities from the last 3 days (normal polling cadence).
- Backfill: pass --days N to pull a longer window. JSON files are immutable; re-running is safe.
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

WORKOUT_LOG = Path("WORKOUT_LOG.md")
ACTIVITIES_DIR = Path("strava/activities")
STRAVA_API = "https://www.strava.com/api/v3"


def get_access_token():
    """Exchange refresh token for a fresh access token."""
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": os.environ["STRAVA_CLIENT_ID"],
        "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
        "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def logged_dates():
    """Return the set of '## <Date>' headings already present in WORKOUT_LOG.md."""
    dates = set()
    if not WORKOUT_LOG.exists():
        return dates
    with WORKOUT_LOG.open() as f:
        for line in f:
            m = re.match(r"^## ([A-Z][a-z]+ \d{1,2}, \d{4})\b", line.strip())
            if m:
                dates.add(m.group(1).strip())
    return dates


def format_pace(moving_time_s, distance_m):
    if distance_m <= 0:
        return None
    pace_s = moving_time_s / (distance_m / 1609.344)
    return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/mi"


def format_time(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_date_heading(dt):
    return dt.strftime("%B %-d, %Y")


def extract_splits(detail):
    """Return per-mile splits with pace, time, HR, and elevation diff (feet)."""
    out = []
    for i, s in enumerate(detail.get("splits_standard", []) or [], start=1):
        dist_m = s.get("distance", 0)
        time_s = s.get("moving_time", 0)
        pace = None
        if dist_m > 0:
            pace_s = time_s / (dist_m / 1609.344)
            pace = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}"
        out.append({
            "mile": i,
            "distance_mi": round(dist_m / 1609.344, 3),
            "moving_time_s": time_s,
            "pace": pace,
            "avg_hr": s.get("average_heartrate"),
            "elev_diff_ft": round((s.get("elevation_difference") or 0) * 3.28084, 1),
        })
    return out


def fetch_hr_zones(activity_id, token):
    resp = requests.get(
        f"{STRAVA_API}/activities/{activity_id}/zones",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        return None
    for z in resp.json():
        if z.get("type") == "heartrate":
            return [
                {"min": b.get("min"), "max": b.get("max"), "time_s": b.get("time")}
                for b in z.get("distribution_buckets", [])
            ]
    return None


def fetch_laps(activity_id, token):
    """Return per-lap data (watch lap-button or auto-lap segments).

    Strava's per-mile splits live in the activity detail; these are the *lap* segments,
    which are what matter for track workouts (each interval and recovery is its own lap).
    Returns None if Strava has no lap data for the activity.
    """
    resp = requests.get(
        f"{STRAVA_API}/activities/{activity_id}/laps",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        return None
    laps = resp.json() or []
    if not laps:
        return None
    out = []
    for lap in laps:
        dist_m = lap.get("distance", 0) or 0
        moving_s = lap.get("moving_time", 0) or 0
        pace = None
        if dist_m > 0 and moving_s > 0:
            pace_s = moving_s / (dist_m / 1609.344)
            pace = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}"
        out.append({
            "lap_index": lap.get("lap_index"),
            "name": lap.get("name"),
            "distance_mi": round(dist_m / 1609.344, 3),
            "distance_m": round(dist_m, 1),
            "moving_time_s": moving_s,
            "elapsed_time_s": lap.get("elapsed_time"),
            "pace": pace,
            "avg_hr": lap.get("average_heartrate"),
            "max_hr": lap.get("max_heartrate"),
            "avg_cadence_spm": int(lap["average_cadence"] * 2) if lap.get("average_cadence") else None,
            "elev_gain_ft": round((lap.get("total_elevation_gain") or 0) * 3.28084, 1),
        })
    return out


def build_sidecar(detail, hr_zones, laps):
    """Build the JSON object for one activity. Curated fields only — keep stable."""
    start_local = detail.get("start_date_local", "")
    dt = datetime.fromisoformat(start_local.replace("Z", "+00:00"))
    distance_m = detail.get("distance", 0)
    moving_time = detail.get("moving_time", 0)
    avg_cadence = detail.get("average_cadence")
    return {
        "activity_id": detail["id"],
        "name": detail.get("name"),
        "type": detail.get("type"),
        "start_local": start_local,
        "date": dt.strftime("%Y-%m-%d"),
        "date_heading": format_date_heading(dt),
        "distance_mi": round(distance_m / 1609.344, 3),
        "moving_time_s": moving_time,
        "elapsed_time_s": detail.get("elapsed_time", 0),
        "avg_pace": format_pace(moving_time, distance_m),
        "elevation_gain_ft": round((detail.get("total_elevation_gain") or 0) * 3.28084, 1),
        "avg_hr": detail.get("average_heartrate"),
        "max_hr": detail.get("max_heartrate"),
        "avg_cadence_spm": int(avg_cadence * 2) if avg_cadence else None,
        "avg_power_w": detail.get("average_watts"),
        "calories": detail.get("calories"),
        "suffer_score": detail.get("suffer_score"),
        "description": detail.get("description") or "",
        "strava_url": f"https://www.strava.com/activities/{detail['id']}",
        "splits": extract_splits(detail),
        "laps": laps,
        "hr_zones": hr_zones,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def write_sidecar(sidecar):
    """Write JSON sidecar. Returns True if written, False if already existed."""
    path = ACTIVITIES_DIR / f"{sidecar['activity_id']}.json"
    if path.exists():
        return False
    ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n")
    return True


def append_stub(sidecar):
    """Append a minimal narrative stub to WORKOUT_LOG.md for a date not yet present.

    Only the bare-minimum fields. Coach is expected to expand this entry by reading the
    JSON sidecar and folding in the analysis. The stub is here so days when no manual
    feedback is provided still leave a visible breadcrumb in the log.
    """
    hr = "N/A"
    if sidecar.get("avg_hr"):
        hr = f"{sidecar['avg_hr']:.0f} bpm"
        if sidecar.get("max_hr"):
            hr += f" (max {sidecar['max_hr']:.0f})"
    splits = ", ".join(s["pace"] for s in sidecar["splits"] if s.get("pace"))
    cadence = f"{sidecar['avg_cadence_spm']} spm" if sidecar.get("avg_cadence_spm") else "N/A"
    effort = ""
    if sidecar.get("suffer_score"):
        effort = f"\n- **Relative Effort:** {sidecar['suffer_score']}"
    entry = f"""
## {sidecar['date_heading']}

- **Workout:** {sidecar['name']}
- **Type:** {sidecar['type']}
- **Distance:** {sidecar['distance_mi']:.2f} mi
- **Time:** {format_time(sidecar['moving_time_s'])}
- **Avg Pace:** {sidecar['avg_pace']}
- **Elevation Gain:** {sidecar['elevation_gain_ft']:.0f} ft
- **Avg Heart Rate:** {hr}
- **Avg Cadence:** {cadence}
- **Splits:** {splits}{effort}
- **Strava sidecar:** `strava/activities/{sidecar['activity_id']}.json`
- **Knee Status:** (pending — update after reviewing)
- **Notes:** Auto-logged from Strava. Awaiting athlete feedback.
"""
    with WORKOUT_LOG.open("a") as f:
        f.write(entry)


def backfill_laps(token):
    """Add the `laps` field to existing sidecars that don't have it.

    Additive only — does not overwrite any other field. Use when extending the schema
    so historical sidecars get the same data shape as new ones. Idempotent: skips any
    sidecar that already has a non-null `laps` field.
    """
    if not ACTIVITIES_DIR.exists():
        print("No sidecars directory; nothing to backfill")
        return
    paths = sorted(ACTIVITIES_DIR.glob("*.json"))
    print(f"Scanning {len(paths)} sidecar(s) for missing laps")
    updated = 0
    for path in paths:
        data = json.loads(path.read_text())
        if "laps" in data and data["laps"] is not None:
            continue
        aid = data.get("activity_id")
        if not aid:
            continue
        time.sleep(1)
        laps = fetch_laps(aid, token)
        if laps is None:
            print(f"  [none]  {aid} — Strava returned no lap data")
            data["laps"] = None
        else:
            print(f"  [add]   {aid} — {len(laps)} laps")
            data["laps"] = laps
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        updated += 1
    print(f"Backfill complete. Updated {updated} sidecar(s).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3, help="Activity lookback window (default: 3)")
    parser.add_argument(
        "--backfill-laps",
        action="store_true",
        help="Add the `laps` field to existing sidecars that don't have it (additive only), then exit.",
    )
    args = parser.parse_args()

    token = get_access_token()

    if args.backfill_laps:
        backfill_laps(token)
        return

    print(f"Got access token; pulling last {args.days} days")

    after = int((datetime.now() - timedelta(days=args.days)).timestamp())
    resp = requests.get(
        f"{STRAVA_API}/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"after": after, "per_page": 100},
    )
    resp.raise_for_status()
    activities = resp.json()
    print(f"Found {len(activities)} total activities in window")

    runnable = [a for a in activities if a.get("type") in ("Run", "Walk", "Hike")]
    print(f"  {len(runnable)} runnable (Run/Walk/Hike)")

    existing_dates = logged_dates()
    written_sidecars = []
    stubbed_dates = set()

    for a in sorted(runnable, key=lambda x: x.get("start_date_local", "")):
        aid = a["id"]
        sidecar_path = ACTIVITIES_DIR / f"{aid}.json"
        if sidecar_path.exists():
            print(f"  [skip] {aid} sidecar exists ({a.get('name')})")
            continue

        time.sleep(1)
        detail_resp = requests.get(
            f"{STRAVA_API}/activities/{aid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
        hr_zones = fetch_hr_zones(aid, token)
        laps = fetch_laps(aid, token)

        sidecar = build_sidecar(detail, hr_zones, laps)
        if write_sidecar(sidecar):
            print(f"  [write] strava/activities/{aid}.json — {sidecar['name']} ({sidecar['date_heading']})")
            written_sidecars.append(sidecar)

        if (
            sidecar["date_heading"] not in existing_dates
            and sidecar["date_heading"] not in stubbed_dates
        ):
            append_stub(sidecar)
            stubbed_dates.add(sidecar["date_heading"])
            print(f"  [stub]  appended WORKOUT_LOG entry for {sidecar['date_heading']}")
        else:
            print(f"  [keep]  WORKOUT_LOG already has {sidecar['date_heading']} — leaving alone")

    print(f"\nDone. Wrote {len(written_sidecars)} sidecar(s); stubbed {len(stubbed_dates)} date(s).")


if __name__ == "__main__":
    main()
