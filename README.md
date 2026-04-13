	# Running Coach — SF Marathon 2026

AI running coach powered by Claude Code cloud scheduled tasks.

## What This Does

- Sends a daily workout briefing email at 5:30am PT
- Tracks workout data and adapts the training plan based on feedback
- Monitors knee health and flags concerns early

## Setup

### 1. Push this repo to GitHub (private)

```bash
git init
git add .
git commit -m "Initial training plan and coaching setup"
gh repo create running-coach --private --push
```

### 2. Make sure Gmail connector is enabled

Go to [claude.ai](https://claude.ai) → Settings → Connectors → Enable Gmail.

### 3. Create the cloud scheduled task

Open Claude Code in this repo directory:

```bash
cd running-coach
claude
```

Then run:

```
/schedule
```

When prompted, configure:
- **Name:** Daily Workout Briefing
- **Schedule:** Every day at 5:30am PT (cron: `30 5 * * *`)
- **Prompt:** See below

### Scheduled Task Prompt

```
Read CLAUDE.md for your instructions. You are my running coach.

Read TRAINING_PLAN.md to find today's scheduled workout based on today's date.
Read WORKOUT_LOG.md for my recent workout history and knee status.

Send me a daily workout briefing via Gmail. Keep it to 8-10 sentences max.
Include: today's workout details, one focus cue, where I am in the training
cycle, and any modifications based on my recent feedback.

Subject line format: "🏃 [Day] — [Workout Summary]"
Example: "🏃 Tuesday — Easy 5 mi + strides"
```

### 4. Providing feedback after workouts

Open Claude Code in this repo (or use Dispatch from your phone) and share your workout data:

```
Just finished today's run. Here are my stats:
- Distance: 5.2 mi
- Pace: 9:35/mi
- HR: 142 avg
- Knee: green, felt great
- Notes: easy effort, stayed on Sawyer Camp Trail
```

Claude will log the data to WORKOUT_LOG.md, commit it, and flag anything notable.

## Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Coaching instructions and athlete profile |
| `TRAINING_PLAN.md` | 15-week training plan (Week 1 starts April 13) |
| `WORKOUT_LOG.md` | Running log of all workouts with knee status tracking |
| `README.md` | This file |
