#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成“连续贡献（Streak）”SVG 卡片（亮色/暗色两版）。

设计目标：
1) 不依赖第三方在线卡片服务，避免“Failed to retrieve contributions”这类不稳定问题
2) 在 GitHub Actions 中用 GITHUB_TOKEN 调 GitHub GraphQL API，生成静态 SVG 并发布到 output 分支
3) README 通过 raw.githubusercontent.com 引用输出文件，稳定可用
"""

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
    当前连续天数: int
    当前开始日期: str | None
    最长连续天数: int
    最长开始日期: str | None
    最长结束日期: str | None
    近一年贡献次数: int
    统计截止日期: str


def _iso_date(d: dt.date) -> str:
    return d.isoformat()


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _request_github_graphql(token: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GITHUB_GRAPHQL_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "atoz03-readme-streak-generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
    if "errors" in data:
        raise RuntimeError(f"GitHub GraphQL 返回错误：{data['errors']}")
    return data


def _flatten_days(weeks: Iterable[dict]) -> list[tuple[dt.date, int]]:
    days: list[tuple[dt.date, int]] = []
    for w in weeks:
        for d in w.get("contributionDays", []):
            days.append((_parse_date(d["date"]), int(d["contributionCount"])))
    days.sort(key=lambda x: x[0])
    return days


def _compute_streak(days: list[tuple[dt.date, int]], today: dt.date) -> StreakResult:
    if not days:
        return StreakResult(
            当前连续天数=0,
            当前开始日期=None,
            最长连续天数=0,
            最长开始日期=None,
            最长结束日期=None,
            近一年贡献次数=0,
            统计截止日期=_iso_date(today),
        )

    # 仅保留不超过 today 的数据
    days = [(d, c) for (d, c) in days if d <= today]
    if not days:
        return StreakResult(
            当前连续天数=0,
            当前开始日期=None,
            最长连续天数=0,
            最长开始日期=None,
            最长结束日期=None,
            近一年贡献次数=0,
            统计截止日期=_iso_date(today),
        )

    # 近一年贡献次数：直接按给定范围求和（范围由调用方保证为近一年）
    total = sum(c for _, c in days)

    # 当前连续：如果今天为 0，则按“截至昨天”的口径（更符合多数 streak 卡片体验）
    end_idx = len(days) - 1
    if days[end_idx][0] == today and days[end_idx][1] == 0:
        end_idx -= 1
    if end_idx < 0:
        # 近一年每天都 0
        return StreakResult(
            当前连续天数=0,
            当前开始日期=None,
            最长连续天数=0,
            最长开始日期=None,
            最长结束日期=None,
            近一年贡献次数=total,
            统计截止日期=_iso_date(today),
        )

    current_len = 0
    current_start: dt.date | None = None
    prev_date: dt.date | None = None
    for i in range(end_idx, -1, -1):
        date_i, count_i = days[i]
        if count_i <= 0:
            break
        if prev_date is not None and (prev_date - date_i).days != 1:
            # 数据不连续（理论上不应发生），直接停止
            break
        current_len += 1
        current_start = date_i
        prev_date = date_i

    # 最长连续
    best_len = 0
    best_start: dt.date | None = None
    best_end: dt.date | None = None

    run_len = 0
    run_start: dt.date | None = None
    prev: dt.date | None = None

    for date_i, count_i in days:
        if count_i > 0:
            if run_len == 0:
                run_start = date_i
                run_len = 1
            else:
                if prev is not None and (date_i - prev).days == 1:
                    run_len += 1
                else:
                    run_start = date_i
                    run_len = 1
            if run_len > best_len:
                best_len = run_len
                best_start = run_start
                best_end = date_i
        else:
            run_len = 0
            run_start = None
        prev = date_i

    return StreakResult(
        当前连续天数=current_len,
        当前开始日期=_iso_date(current_start) if current_start else None,
        最长连续天数=best_len,
        最长开始日期=_iso_date(best_start) if best_start else None,
        最长结束日期=_iso_date(best_end) if best_end else None,
        近一年贡献次数=total,
        统计截止日期=_iso_date(today),
    )


def _svg_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _render_svg(result: StreakResult, theme: str) -> str:
    if theme not in {"light", "dark"}:
        raise ValueError("theme 必须为 light 或 dark")

    if theme == "dark":
        bg = "#0d1117"
        card = "#161b22"
        border = "#30363d"
        title = "#c9d1d9"
        text = "#c9d1d9"
        muted = "#8b949e"
        accent = "#7aa2f7"
        accent2 = "#9ece6a"
    else:
        bg = "#ffffff"
        card = "#ffffff"
        border = "#d0d7de"
        title = "#24292f"
        text = "#24292f"
        muted = "#57606a"
        accent = "#0969da"
        accent2 = "#1a7f37"

    current_line = f"{result.当前连续天数} 天"
    if result.当前开始日期:
        current_line += f"（自 {result.当前开始日期}）"

    best_line = f"{result.最长连续天数} 天"
    if result.最长开始日期 and result.最长结束日期:
        best_line += f"（{result.最长开始日期} → {result.最长结束日期}）"

    total_line = f"{result.近一年贡献次数} 次（近一年）"
    update_line = f"更新：{result.统计截止日期}"

    # 简洁卡片：三行数据 + 更新时间
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="140" viewBox="0 0 900 140" role="img" aria-label="连续贡献">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{accent}"/>
      <stop offset="100%" stop-color="{accent2}"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#000000" flood-opacity="0.20"/>
    </filter>
  </defs>
  <rect x="0" y="0" width="900" height="140" fill="{bg}"/>
  <g filter="url(#shadow)">
    <rect x="18" y="16" width="864" height="108" rx="16" fill="{card}" stroke="{border}"/>
  </g>
  <rect x="40" y="40" width="8" height="60" rx="4" fill="url(#g)"/>
  <text x="62" y="52" fill="{title}" font-size="18" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, Apple Color Emoji, Segoe UI Emoji">
    连续贡献
  </text>
  <text x="62" y="78" fill="{text}" font-size="14" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">
    当前：{_svg_escape(current_line)}
  </text>
  <text x="62" y="100" fill="{text}" font-size="14" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">
    最长：{_svg_escape(best_line)}
  </text>
  <text x="62" y="122" fill="{text}" font-size="14" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">
    合计：{_svg_escape(total_line)}
  </text>
  <text x="860" y="52" text-anchor="end" fill="{muted}" font-size="12" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial">
    {_svg_escape(update_line)}
  </text>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="生成连续贡献 SVG 卡片（亮/暗两版）")
    parser.add_argument("--user", required=True, help="GitHub 用户名（login）")
    parser.add_argument("--out-dir", required=True, help="输出目录（例如 dist）")
    parser.add_argument(
        "--days",
        type=int,
        default=370,
        help="拉取贡献日历范围（天），建议 ≥ 366，用于覆盖闰年",
    )
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        print("缺少环境变量 GITHUB_TOKEN（或 GH_TOKEN），无法调用 GitHub GraphQL API", file=sys.stderr)
        return 2

    today = dt.datetime.utcnow().date()
    from_date = today - dt.timedelta(days=int(args.days))
    to_date = today + dt.timedelta(days=1)

    query = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
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
        token=token,
        query=query,
        variables={
            "login": args.user,
            "from": f"{from_date.isoformat()}T00:00:00Z",
            "to": f"{to_date.isoformat()}T00:00:00Z",
        },
    )

    user = (data.get("data") or {}).get("user")
    if not user:
        print("未找到用户数据（可能用户名错误或权限不足）", file=sys.stderr)
        return 3

    cal = (
        user.get("contributionsCollection", {})
        .get("contributionCalendar", {})
    )
    weeks = cal.get("weeks", [])
    days = _flatten_days(weeks)
    # 将范围收敛到“近一年”以便展示合计（从今天往前 365 天）
    year_from = today - dt.timedelta(days=365)
    days_last_year = [(d, c) for (d, c) in days if year_from <= d <= today]
    result = _compute_streak(days_last_year, today=today)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "streak.svg").write_text(_render_svg(result, theme="light"), encoding="utf-8")
    (out_dir / "streak-dark.svg").write_text(_render_svg(result, theme="dark"), encoding="utf-8")

    print("已生成：streak.svg / streak-dark.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

