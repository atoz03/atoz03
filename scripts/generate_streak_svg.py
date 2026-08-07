#!/usr/bin/env python3
"""Generate light and dark contribution streak SVG cards for the profile README."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"


@dataclass(frozen=True)
class StreakResult:
    current_streak: int
    current_start: str | None
    longest_streak: int
    longest_start: str | None
    longest_end: str | None
    contributions_last_year: int
    updated_at: str


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _request_github_graphql(token: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GITHUB_GRAPHQL_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "atoz03-profile-streak-generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "errors" in data:
        raise RuntimeError(f"GitHub GraphQL error: {data['errors']}")
    return data


def _flatten_days(weeks: Iterable[dict]) -> list[tuple[dt.date, int]]:
    days: list[tuple[dt.date, int]] = []
    for week in weeks:
        for day in week.get("contributionDays", []):
            days.append((_parse_date(day["date"]), int(day["contributionCount"])))
    days.sort(key=lambda item: item[0])
    return days


def _compute_streak(days: list[tuple[dt.date, int]], today: dt.date) -> StreakResult:
    days = [(date, count) for date, count in days if date <= today]
    total = sum(count for _, count in days)

    if not days:
        return StreakResult(0, None, 0, None, None, 0, today.isoformat())

    end_index = len(days) - 1
    if days[end_index][0] == today and days[end_index][1] == 0:
        end_index -= 1

    current_streak = 0
    current_start: dt.date | None = None
    previous_date: dt.date | None = None

    for index in range(end_index, -1, -1):
        date, count = days[index]
        if count <= 0:
            break
        if previous_date is not None and (previous_date - date).days != 1:
            break
        current_streak += 1
        current_start = date
        previous_date = date

    longest_streak = 0
    longest_start: dt.date | None = None
    longest_end: dt.date | None = None
    run_length = 0
    run_start: dt.date | None = None
    previous: dt.date | None = None

    for date, count in days:
        if count > 0:
            if run_length == 0 or previous is None or (date - previous).days != 1:
                run_start = date
                run_length = 1
            else:
                run_length += 1
            if run_length > longest_streak:
                longest_streak = run_length
                longest_start = run_start
                longest_end = date
        else:
            run_length = 0
            run_start = None
        previous = date

    return StreakResult(
        current_streak=current_streak,
        current_start=current_start.isoformat() if current_start else None,
        longest_streak=longest_streak,
        longest_start=longest_start.isoformat() if longest_start else None,
        longest_end=longest_end.isoformat() if longest_end else None,
        contributions_last_year=total,
        updated_at=today.isoformat(),
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _render_svg(result: StreakResult, theme: str) -> str:
    if theme not in {"light", "dark"}:
        raise ValueError("theme must be 'light' or 'dark'")

    if theme == "dark":
        background = "#0d1117"
        card = "#161b22"
        border = "#30363d"
        primary = "#f0f6fc"
        secondary = "#8b949e"
        divider = "#30363d"
        accent_a = "#58a6ff"
        accent_b = "#a371f7"
        accent_c = "#3fb950"
    else:
        background = "#ffffff"
        card = "#ffffff"
        border = "#d0d7de"
        primary = "#1f2328"
        secondary = "#656d76"
        divider = "#d8dee4"
        accent_a = "#0969da"
        accent_b = "#8250df"
        accent_c = "#1a7f37"

    current_note = f"since {result.current_start}" if result.current_start else "no active streak"
    longest_note = (
        f"{result.longest_start} → {result.longest_end}"
        if result.longest_start and result.longest_end
        else "—"
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="168" viewBox="0 0 900 168" role="img" aria-label="Contribution streak statistics">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{accent_a}"/>
      <stop offset="52%" stop-color="{accent_b}"/>
      <stop offset="100%" stop-color="{accent_c}"/>
    </linearGradient>
  </defs>

  <rect width="900" height="168" fill="{background}"/>
  <rect x="10" y="10" width="880" height="148" rx="18" fill="{card}" stroke="{border}"/>
  <rect x="10" y="10" width="880" height="4" rx="2" fill="url(#accent)"/>

  <text x="34" y="43" fill="{primary}" font-size="17" font-weight="600" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">Contribution Streak</text>
  <text x="866" y="43" text-anchor="end" fill="{secondary}" font-size="11" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">Updated {_escape(result.updated_at)}</text>

  <line x1="300" y1="62" x2="300" y2="137" stroke="{divider}"/>
  <line x1="600" y1="62" x2="600" y2="137" stroke="{divider}"/>

  <text x="150" y="82" text-anchor="middle" fill="{secondary}" font-size="12" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">CURRENT STREAK</text>
  <text x="150" y="113" text-anchor="middle" fill="{accent_a}" font-size="27" font-weight="700" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">{result.current_streak} days</text>
  <text x="150" y="134" text-anchor="middle" fill="{secondary}" font-size="11" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">{_escape(current_note)}</text>

  <text x="450" y="82" text-anchor="middle" fill="{secondary}" font-size="12" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">LONGEST STREAK</text>
  <text x="450" y="113" text-anchor="middle" fill="{accent_b}" font-size="27" font-weight="700" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">{result.longest_streak} days</text>
  <text x="450" y="134" text-anchor="middle" fill="{secondary}" font-size="11" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">{_escape(longest_note)}</text>

  <text x="750" y="82" text-anchor="middle" fill="{secondary}" font-size="12" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">CONTRIBUTIONS</text>
  <text x="750" y="113" text-anchor="middle" fill="{accent_c}" font-size="27" font-weight="700" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">{result.contributions_last_year}</text>
  <text x="750" y="134" text-anchor="middle" fill="{secondary}" font-size="11" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">last 365 days</text>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate contribution streak SVG cards")
    parser.add_argument("--user", required=True, help="GitHub username")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--days", type=int, default=370, help="Contribution calendar lookback range")
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        print("GITHUB_TOKEN or GH_TOKEN is required", file=sys.stderr)
        return 2

    today = dt.datetime.now(dt.UTC).date()
    from_date = today - dt.timedelta(days=args.days)
    to_date = today + dt.timedelta(days=1)

    query = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
""".strip()

    data = _request_github_graphql(
        token,
        query,
        {
            "login": args.user,
            "from": f"{from_date.isoformat()}T00:00:00Z",
            "to": f"{to_date.isoformat()}T00:00:00Z",
        },
    )

    user = (data.get("data") or {}).get("user")
    if not user:
        print("GitHub user data could not be retrieved", file=sys.stderr)
        return 3

    weeks = (
        user.get("contributionsCollection", {})
        .get("contributionCalendar", {})
        .get("weeks", [])
    )
    days = _flatten_days(weeks)
    one_year_ago = today - dt.timedelta(days=365)
    result = _compute_streak(
        [(date, count) for date, count in days if one_year_ago <= date <= today],
        today,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "streak.svg").write_text(_render_svg(result, "light"), encoding="utf-8")
    (out_dir / "streak-dark.svg").write_text(_render_svg(result, "dark"), encoding="utf-8")

    print("Generated streak.svg and streak-dark.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
