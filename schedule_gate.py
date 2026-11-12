"""Decide whether this workflow tick should produce today's digest.

GitHub Actions cron on private repos routinely fires hours late or not at all, so
the workflow ticks many times a day and this gate lets exactly one tick through:
the first one at or after 09:00 Europe/Rome that has no successful run logged for
today yet. Later ticks are no-ops, which also makes a delayed tick a retry rather
than a missed day.
"""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TARGET = (9, 0)
ROME = ZoneInfo("Europe/Rome")


def delivered_today(today):
    try:
        with open(os.environ.get("GATE_LOG_PATH", "run-log.json"), encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(entries, list):
        return False
    return any(
        e.get("date") == today and e.get("success") and not e.get("dry_run")
        for e in entries
        if isinstance(e, dict)
    )


def main():
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    now = datetime.now(timezone.utc).astimezone(ROME)
    today = now.strftime("%Y-%m-%d")

    if event != "schedule":
        should_run, reason = True, f"{event or 'local'} run bypasses the gate"
    elif (now.hour, now.minute) < TARGET:
        should_run, reason = False, f"{now:%H:%M} Rome is before 09:00"
    elif delivered_today(today):
        should_run, reason = False, f"{today} already delivered"
    else:
        should_run, reason = True, f"{now:%H:%M} Rome and {today} is still pending"

    print(f"[gate] should_run={should_run} - {reason}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"should_run={'true' if should_run else 'false'}\n")


if __name__ == "__main__":
    main()
