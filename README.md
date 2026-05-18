# Running Coach — SF Marathon 2026

AI running coach for Paul Lambert's 2026 San Francisco Marathon (July 26, 2026), powered by Claude Code on the web.

## What This Does

- **Evening briefing (~9 PM PT, night before):** Claude reads the plan and recent workout/strength logs, writes the next day's briefing to `briefings/latest.json`, and pushes. A GitHub Action sends it via Resend.
- **Strava sync:** A scheduled GitHub Action pulls activities from Strava four times a day and writes an immutable JSON sidecar per activity (`strava/activities/<id>.json`) — objective HR, splits, cadence, etc. The coach reads the sidecar when writing the narrative log.
- **Feedback via Dispatch:** Paul sends subjective notes (knee status, effort, fueling) from his phone. Claude folds them into `WORKOUT_LOG.md` and adapts the plan.
- **Plan adaptation:** Claude modifies `TRAINING_PLAN.md` directly when knee, fatigue, or performance data calls for it.
- **Strength progression:** Wed/Fri/Mon gym sessions logged in `STRENGTH_LOG.md`; recommended weights update based on feel ratings.

## Repo as Memory

Every Claude session is ephemeral — no memory between runs. The repo files **are** the memory. Every meaningful update is committed and pushed so the next session picks it up. All development happens on `main` directly; feature branches are forbidden.

## Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Coaching instructions, athlete profile, session protocol |
| `TRAINING_PLAN.md` | V6 12-week periodized plan (May 4 – July 26, 2026) |
| `WORKOUT_LOG.md` | Narrative log of every run with knee 5-point reading |
| `STRENGTH_LOG.md` | Strength sessions and current recommended weights |
| `PT_NOTES.md` | PT findings, prescribed exercises, follow-up notes |
| `EXERCISE_GUIDE.md` | Form cues, video references, common mistakes |
| `NUTRITION_GUIDE.md` | Pescatarian marathon fueling and gut training |
| `SHOE_LOG.md` | Shoe rotation and per-pair mileage |
| `strava/activities/*.json` | Immutable per-activity sidecars (objective data) |
| `briefings/latest.json` | Email payload picked up by the send-briefing Action |

## Knee Protocol

Knee status is tracked on a 5-point scale on every workout entry. Readings of 3 trigger the cycling escape valve; two consecutive 3+ readings or any 4–5 forces a modified week and PT contact. The knee outranks every time goal.

## Infrastructure

- **Repo:** https://github.com/prlambert9000/sfm26coach
- **Briefing send:** Resend API via `.github/workflows/send-briefing.yml`
- **Strava puller:** `scripts/pull_strava.py` driven by `.github/workflows/pull-strava.yml` (cron + push to main)
- **Scheduled briefing trigger:** Claude Code on the web (`trig_01MEHiS49qyyz5A5bJ5Fn9SP`)
- **Secrets:** `RESEND_API_KEY`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` in GitHub Actions secrets

## Manual Operations

- **Force a Strava sync:** `git commit --allow-empty -m "trigger strava sync" && git push origin main`
- **Backfill Strava history:** trigger the **Pull Strava Data** workflow via `workflow_dispatch` with a `days` input (e.g. `90`).
- **Provide post-workout feedback:** open Dispatch or Claude Code in the repo and describe the session — Claude will locate the matching sidecar, update `WORKOUT_LOG.md`, and push.
