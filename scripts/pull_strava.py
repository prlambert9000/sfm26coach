#!/usr/bin/env python3
"""Pull new activities from Strava and append to WORKOUT_LOG.md."""

import os
import re
import sys
import time
import requests
from collections import defaultdict
from datetime import datetime, timedelta

WORKOUT_LOG = "WORKOUT_LOG.md"
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


def get_logged_counts():
    """Read WORKOUT_LOG.md and return {date_heading: count_of_entries}.

    Counts entries per date so multi-run days only re-log the unaccounted tail.
    """
    counts = defaultdict(int)
    with open(WORKOUT_LOG, "r") as f:
        for line in f:
            m = re.match(r"^## ([A-Z][a-z]+ \d{1,2}, \d{4})\b", line.strip())
            if m:
                counts[m.group(1).strip()] += 1
    return counts


def format_pace(moving_time_s, distance_m):
    """Convert to min:sec per mile."""
    if distance_m <= 0:
        return "N/A"
    pace_s = moving_time_s / (distance_m / 1609.344)
    mins = int(pace_s // 60)
    secs = int(pace_s % 60)
    return f"{mins}:{secs:02d}/mi"


def format_time(seconds):
    """Format seconds as H:MM:SS or M:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_date_heading(dt):
    """Format datetime as 'Month Day, Year'."""
    return dt.strftime("%B %-d, %Y")


def get_splits(activity_detail):
    """Extract mile split paces from activity detail."""
    splits = activity_detail.get("splits_standard", [])
    if not splits:
        return "N/A"
    paces = []
    for split in splits:
        dist = split.get("distance", 0)
        time_s = split.get("moving_time", 0)
        if dist > 0:
            pace_s = time_s / (dist / 1609.344)
            mins = int(pace_s // 60)
            secs = int(pace_s % 60)
            paces.append(f"{mins}:{secs:02d}")
    return ", ".join(paces)


def get_hr_zones(activity_id, token):
    """Get heart rate zone distribution."""
    resp = requests.get(
        f"{STRAVA_API}/activities/{activity_id}/zones",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        return None
    zones = resp.json()
    for z in zones:
        if z.get("type") == "heartrate":
            return z.get("distribution_buckets", [])
    return None


def main():
    token = get_access_token()
    print("Got access token")

    logged_counts = get_logged_counts()
    print(f"Already logged counts by date: {dict(logged_counts)}")

    # Fetch activities from the last 3 days
    after = int((datetime.now() - timedelta(days=3)).timestamp())
    resp = requests.get(
        f"{STRAVA_API}/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"after": after, "per_page": 30},
    )
    resp.raise_for_status()
    activities = resp.json()
    print(f"Found {len(activities)} activities in the last 3 days")

    # Group runnable activities by date, sorted oldest-first within each date
    by_date = defaultdict(list)
    for activity in activities:
        activity_type = activity.get("type", "")
        if activity_type not in ("Run", "Walk", "Hike"):
            print(f"Skipping {activity.get('name')} ({activity_type})")
            continue
        start_local = activity.get("start_date_local", "")
        dt = datetime.fromisoformat(start_local.replace("Z", "+00:00"))
        date_heading = format_date_heading(dt)
        by_date[date_heading].append((dt, activity))

    # For each date, only log activities beyond the count already logged
    to_process = []
    for date_heading, items in by_date.items():
        items.sort(key=lambda x: x[0])  # oldest first
        already = logged_counts.get(date_heading, 0)
        if len(items) <= already:
            print(f"All {len(items)} activity(s) on {date_heading} already logged")
            continue
        new_for_date = items[already:]
        print(f"{date_heading}: {already} logged, {len(items)} on Strava → adding {len(new_for_date)}")
        for dt, activity in new_for_date:
            to_process.append((date_heading, activity))

    new_entries = []

    for date_heading, activity in to_process:
        activity_type = activity.get("type", "")
        activity_id = activity["id"]
        print(f"Fetching details for: {activity.get('name')} ({activity_id})")

        # Rate limit: be polite
        time.sleep(1)

        # Get full activity detail
        detail_resp = requests.get(
            f"{STRAVA_API}/activities/{activity_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()

        # Extract metrics
        distance_mi = detail.get("distance", 0) / 1609.344
        moving_time = detail.get("moving_time", 0)
        elapsed_time = detail.get("elapsed_time", 0)
        avg_pace = format_pace(moving_time, detail.get("distance", 0))
        elevation_ft = detail.get("total_elevation_gain", 0) * 3.28084
        avg_hr = detail.get("average_heartrate")
        max_hr = detail.get("max_heartrate")
        avg_cadence = detail.get("average_cadence")
        calories = detail.get("calories")
        splits = get_splits(detail)
        name = detail.get("name", activity_type)
        description = detail.get("description", "")
        suffer_score = detail.get("suffer_score")

        # Format cadence (Strava reports per-foot, double for spm)
        cadence_str = "N/A"
        if avg_cadence:
            cadence_str = f"{int(avg_cadence * 2)} spm"

        # Build HR string
        hr_str = "N/A"
        if avg_hr:
            hr_str = f"{avg_hr:.0f} bpm"
            if max_hr:
                hr_str += f" (max {max_hr:.0f})"

        # Build effort string
        effort_str = ""
        if suffer_score:
            effort_str = f"\n- **Relative Effort:** {suffer_score}"

        # Build the log entry
        entry = f"""
## {date_heading}

- **Workout:** {name}
- **Type:** {activity_type}
- **Distance:** {distance_mi:.2f} mi
- **Time:** {format_time(moving_time)}
- **Avg Pace:** {avg_pace}
- **Elevation Gain:** {elevation_ft:.0f} ft
- **Avg Heart Rate:** {hr_str}
- **Avg Cadence:** {cadence_str}
- **Splits:** {splits}{effort_str}
- **Knee Status:** (pending — update after reviewing)
- **Notes:** Auto-logged from Strava. Awaiting athlete feedback."""

        new_entries.append(entry)

    if not new_entries:
        print("No new activities to log")
        return

    # Append to workout log
    with open(WORKOUT_LOG, "a") as f:
        for entry in new_entries:
            f.write(entry + "\n")

    print(f"Logged {len(new_entries)} new activities")


if __name__ == "__main__":
    main()
