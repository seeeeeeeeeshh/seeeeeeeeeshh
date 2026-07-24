from __future__ import annotations

import base64
import html
import json
import os
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


USERNAME = os.getenv("GITHUB_REPOSITORY_OWNER", "seeeeeeeeeshh")
TOKEN = os.environ["GITHUB_TOKEN"]

OUTPUT_PATH = Path("assets/github-dashboard.svg")
WIDTH = 1500
HEIGHT = 980


GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    name
    bio
    avatarUrl(size: 220)
    location
    createdAt
    followers {
      totalCount
    }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      privacy: PUBLIC
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      totalCount
      nodes {
        name
        stargazerCount
        forkCount
        primaryLanguage {
          name
          color
        }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node {
              name
              color
            }
          }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            weekday
          }
        }
      }
    }
  }
}
"""


def graphql_request(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(
        {
            "query": query,
            "variables": variables,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "custom-github-dashboard",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"], indent=2))

    return result["data"]


def download_avatar_data_uri(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "custom-github-dashboard"},
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            encoded = base64.b64encode(response.read()).decode("ascii")
            return f"data:{content_type};base64,{encoded}"
    except Exception:
        return ""


def escape(value: Any) -> str:
    return html.escape(str(value or ""))


def shorten_number(number: int) -> str:
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M".replace(".0M", "M")
    if number >= 1_000:
        return f"{number / 1_000:.1f}K".replace(".0K", "K")
    return str(number)


def calculate_streaks(days: list[dict[str, Any]]) -> tuple[int, int]:
    ordered = sorted(days, key=lambda item: item["date"])

    longest = 0
    running = 0

    for day in ordered:
        if day["contributionCount"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    current = 0

    # Ignore future dates, then count backwards.
    eligible = [
        day
        for day in ordered
        if datetime.strptime(day["date"], "%Y-%m-%d").date() <= date.today()
    ]

    for day in reversed(eligible):
        if day["contributionCount"] > 0:
            current += 1
        elif current == 0:
            # GitHub's current date may not yet have activity.
            continue
        else:
            break

    return current, longest


def language_totals(repositories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, int] = defaultdict(int)
    colors: dict[str, str] = {}

    for repository in repositories:
        edges = repository.get("languages", {}).get("edges", [])

        for edge in edges:
            language = edge["node"]["name"]
            totals[language] += int(edge["size"])
            colors[language] = edge["node"].get("color") or "#58A6FF"

    grand_total = sum(totals.values()) or 1

    languages = [
        {
            "name": name,
            "size": size,
            "percentage": size / grand_total * 100,
            "color": colors[name],
        }
        for name, size in totals.items()
    ]

    return sorted(
        languages,
        key=lambda item: item["size"],
        reverse=True,
    )[:5]


def metric_card(
    x: int,
    title: str,
    value: str,
    icon: str,
    accent: str,
) -> str:
    return f"""
    <g>
      <rect x="{x}" y="122" width="165" height="145"
            rx="14" fill="#0D1522" stroke="#273449"/>
      <text x="{x + 82}" y="163" text-anchor="middle"
            font-size="27" fill="{accent}">{icon}</text>
      <text x="{x + 82}" y="207" text-anchor="middle"
            font-size="31" font-weight="700" fill="#F8FAFC">
        {escape(value)}
      </text>
      <text x="{x + 82}" y="240" text-anchor="middle"
            font-size="15" fill="#AAB7CC">
        {escape(title)}
      </text>
    </g>
    """


def generate_svg(user: dict[str, Any]) -> str:
    repositories = user["repositories"]["nodes"]

    stars = sum(repository["stargazerCount"] for repository in repositories)
    forks = sum(repository["forkCount"] for repository in repositories)

    contributions = user["contributionsCollection"]
    calendar = contributions["contributionCalendar"]

    days = [
        day
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]

    current_streak, longest_streak = calculate_streaks(days)
    languages = language_totals(repositories)

    avatar_uri = download_avatar_data_uri(user["avatarUrl"])

    joined = datetime.fromisoformat(
        user["createdAt"].replace("Z", "+00:00")
    ).strftime("%b %Y")

    display_name = user.get("name") or user["login"]
    bio = user.get("bio") or (
        "Building intelligent systems and full-stack applications "
        "that make an impact."
    )
    location = user.get("location") or "Singapore"

    # Heatmap
    cell = 15
    gap = 5
    heatmap_x = 105
    heatmap_y = 410

    maximum = max(
        (day["contributionCount"] for day in days),
        default=1,
    )

    heatmap_cells: list[str] = []

    for index, day in enumerate(days):
        week_index = index // 7
        weekday = day["weekday"]
        count = day["contributionCount"]

        x = heatmap_x + week_index * (cell + gap)
        y = heatmap_y + weekday * (cell + gap)

        if count == 0:
            fill = "#182332"
        else:
            ratio = count / maximum

            if ratio <= 0.25:
                fill = "#123D43"
            elif ratio <= 0.50:
                fill = "#087F8C"
            elif ratio <= 0.75:
                fill = "#18B8A5"
            else:
                fill = "#52E5B3"

        heatmap_cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
            f'rx="3" fill="{fill}">'
            f"<title>{escape(day['date'])}: {count} contributions</title>"
            f"</rect>"
        )

    # Language bars
    language_elements: list[str] = []

    for index, language in enumerate(languages):
        y = 777 + index * 39
        bar_width = max(10, language["percentage"] * 3.1)

        language_elements.append(
            f"""
            <text x="1040" y="{y}" font-size="16" fill="#D9E2F1">
              {escape(language["name"])}
            </text>
            <rect x="1180" y="{y - 14}" width="225" height="12"
                  rx="6" fill="#1B2737"/>
            <rect x="1180" y="{y - 14}" width="{bar_width:.1f}" height="12"
                  rx="6" fill="{escape(language['color'])}"/>
            <text x="1420" y="{y}" text-anchor="end"
                  font-size="14" fill="#AAB7CC">
              {language["percentage"]:.1f}%
            </text>
            """
        )

    language_total = sum(item["size"] for item in languages) or 1
    donut_parts: list[str] = []
    offset = 0.0
    circumference = 2 * 3.14159265 * 68

    for language in languages:
        fraction = language["size"] / language_total
        segment = fraction * circumference

        donut_parts.append(
            f"""
            <circle cx="745" cy="825" r="68"
                    fill="none"
                    stroke="{escape(language['color'])}"
                    stroke-width="26"
                    stroke-dasharray="{segment:.2f} {circumference - segment:.2f}"
                    stroke-dashoffset="{-offset:.2f}"
                    transform="rotate(-90 745 825)"/>
            """
        )

        offset += segment

    avatar = (
        f"""
        <defs>
          <clipPath id="avatarClip">
            <circle cx="125" cy="194" r="61"/>
          </clipPath>
        </defs>
        <image href="{avatar_uri}" x="64" y="133"
               width="122" height="122"
               preserveAspectRatio="xMidYMid slice"
               clip-path="url(#avatarClip)"/>
        """
        if avatar_uri
        else """
        <circle cx="125" cy="194" r="61" fill="#17324D"/>
        <text x="125" y="213" text-anchor="middle"
              font-size="50" font-weight="700" fill="#52E5B3">S</text>
        """
    )

    commits = contributions["totalCommitContributions"]
    issues = contributions["totalIssueContributions"]
    pull_requests = contributions["totalPullRequestContributions"]

    return f"""<svg xmlns="http://www.w3.org/2000/svg"
        width="{WIDTH}" height="{HEIGHT}"
        viewBox="0 0 {WIDTH} {HEIGHT}"
        role="img"
        aria-labelledby="title description">

      <title id="title">{escape(display_name)} GitHub Analytics</title>
      <desc id="description">
        Custom GitHub analytics dashboard generated using GitHub Actions.
      </desc>

      <defs>
        <linearGradient id="pageGlow" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#06101D"/>
          <stop offset="55%" stop-color="#090D17"/>
          <stop offset="100%" stop-color="#060A11"/>
        </linearGradient>

        <linearGradient id="accentLine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#00C2FF"/>
          <stop offset="48%" stop-color="#2563EB"/>
          <stop offset="100%" stop-color="#D946EF"/>
        </linearGradient>

        <linearGradient id="progressLine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#A855F7"/>
          <stop offset="50%" stop-color="#2563EB"/>
          <stop offset="100%" stop-color="#22D3EE"/>
        </linearGradient>

        <filter id="softGlow">
          <feGaussianBlur stdDeviation="7" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>

      <rect width="1500" height="980" fill="url(#pageGlow)"/>

      <style>
        text {{
          font-family: Inter, ui-sans-serif, system-ui,
                       -apple-system, BlinkMacSystemFont,
                       "Segoe UI", sans-serif;
        }}

        .panel {{
          fill: #0B1421;
          stroke: #243348;
          stroke-width: 1.2;
        }}

        .heading {{
          fill: #F8FAFC;
          font-weight: 700;
        }}

        .muted {{
          fill: #AAB7CC;
        }}
      </style>

      <!-- Header -->
      <text x="28" y="57" font-size="34">📊</text>
      <text x="78" y="58" font-size="35" class="heading">
        GitHub Analytics
      </text>

      <rect x="28" y="78" width="1444" height="3"
            rx="2" fill="url(#accentLine)"/>

      <!-- Profile panel -->
      <rect class="panel" x="28" y="102" width="1444" height="186" rx="16"/>

      {avatar}

      <circle cx="125" cy="194" r="66"
              fill="none" stroke="url(#accentLine)"
              stroke-width="5" filter="url(#softGlow)"/>

      <text x="220" y="157" font-size="31" class="heading">
        {escape(user["login"])}
      </text>

      <text x="220" y="194" font-size="19" fill="#D9E2F1">
        {escape(bio[:58])}
      </text>

      <text x="220" y="222" font-size="19" fill="#D9E2F1">
        {escape(bio[58:116])}
      </text>

      <text x="220" y="258" font-size="16" class="muted">
        ◉ {escape(location)}    ◫ Joined {escape(joined)}
      </text>

      <line x1="680" y1="125" x2="680" y2="265"
            stroke="#35445A"/>

      {metric_card(730, "Repositories", str(user["repositories"]["totalCount"]), "‹›", "#B65CFF")}
      {metric_card(910, "Stars Earned", shorten_number(stars), "☆", "#40E58C")}
      {metric_card(1090, "Forks", shorten_number(forks), "⑂", "#2F81F7")}
      {metric_card(1270, "Contributions", shorten_number(calendar["totalContributions"]), "◷", "#F5C518")}

      <!-- Contribution panel -->
      <rect class="panel" x="28" y="310" width="1444" height="330" rx="16"/>

      <text x="62" y="364" font-size="28">🔥</text>
      <text x="100" y="364" font-size="27" class="heading">
        Contribution Activity
      </text>

      <text x="55" y="452" font-size="14" class="muted">Mon</text>
      <text x="55" y="492" font-size="14" class="muted">Wed</text>
      <text x="55" y="532" font-size="14" class="muted">Fri</text>

      {"".join(heatmap_cells)}

      <line x1="1120" y1="345" x2="1120" y2="612"
            stroke="#35445A"/>

      <text x="1170" y="400" font-size="34" fill="#A855F7">♨</text>
      <text x="1220" y="395" font-size="30" class="heading">
        {current_streak}
      </text>
      <text x="1220" y="421" font-size="16" class="muted">
        Current Streak
      </text>

      <line x1="1170" y1="445" x2="1415" y2="445"
            stroke="#35445A"/>

      <text x="1170" y="497" font-size="34" fill="#2F81F7">◎</text>
      <text x="1220" y="492" font-size="30" class="heading">
        {longest_streak}
      </text>
      <text x="1220" y="518" font-size="16" class="muted">
        Longest Streak
      </text>

      <line x1="1170" y1="542" x2="1415" y2="542"
            stroke="#35445A"/>

      <text x="1170" y="590" font-size="31" fill="#22C55E">▣</text>
      <text x="1220" y="585" font-size="30" class="heading">
        {calendar["totalContributions"]}
      </text>
      <text x="1220" y="611" font-size="16" class="muted">
        Contributions in the last year
      </text>

      <!-- Bottom stats panel -->
      <rect class="panel" x="28" y="660" width="455" height="290" rx="16"/>
      <text x="58" y="713" font-size="25" fill="#A855F7">▥</text>
      <text x="97" y="713" font-size="25" class="heading">
        GitHub Statistics
      </text>

      <rect x="52" y="742" width="190" height="69"
            rx="12" fill="#0D1726" stroke="#273449"/>
      <text x="75" y="777" font-size="25" fill="#8B5CF6">◉</text>
      <text x="111" y="777" font-size="24" class="heading">
        {shorten_number(commits)}
      </text>
      <text x="111" y="799" font-size="13" class="muted">
        Commits · last year
      </text>

      <rect x="258" y="742" width="200" height="69"
            rx="12" fill="#0D1726" stroke="#273449"/>
      <text x="280" y="777" font-size="25" fill="#22C55E">⑂</text>
      <text x="318" y="777" font-size="24" class="heading">
        {shorten_number(pull_requests)}
      </text>
      <text x="318" y="799" font-size="13" class="muted">
        Pull requests · last year
      </text>

      <rect x="52" y="826" width="190" height="69"
            rx="12" fill="#0D1726" stroke="#273449"/>
      <text x="75" y="861" font-size="25" fill="#F5C518">☆</text>
      <text x="111" y="861" font-size="24" class="heading">
        {shorten_number(stars)}
      </text>
      <text x="111" y="883" font-size="13" class="muted">
        Stars earned
      </text>

      <rect x="258" y="826" width="200" height="69"
            rx="12" fill="#0D1726" stroke="#273449"/>
      <text x="280" y="861" font-size="25" fill="#F97316">◌</text>
      <text x="318" y="861" font-size="24" class="heading">
        {shorten_number(issues)}
      </text>
      <text x="318" y="883" font-size="13" class="muted">
        Issues · last year
      </text>

      <rect x="52" y="917" width="406" height="9"
            rx="5" fill="#1B2737"/>
      <rect x="52" y="917" width="315" height="9"
            rx="5" fill="url(#progressLine)"/>

      <!-- Donut panel -->
      <rect class="panel" x="505" y="660" width="455" height="290" rx="16"/>
      <text x="535" y="713" font-size="25" fill="#C84DFF">‹›</text>
      <text x="574" y="713" font-size="25" class="heading">
        Top Languages by Commit
      </text>

      {"".join(donut_parts)}

      <circle cx="745" cy="825" r="46" fill="#0B1421"/>
      <text x="745" y="835" text-anchor="middle"
            font-size="26" fill="#8091AA">‹/›</text>

      <!-- Language bars -->
      <rect class="panel" x="982" y="660" width="490" height="290" rx="16"/>
      <text x="1012" y="713" font-size="25" fill="#F5C518">ϟ</text>
      <text x="1050" y="713" font-size="25" class="heading">
        Most Used Languages
      </text>

      {"".join(language_elements)}

      <text x="750" y="973" text-anchor="middle"
            font-size="15" font-style="italic" class="muted">
        Metrics update automatically through GitHub Actions
      </text>
    </svg>
    """


def main() -> None:
    data = graphql_request(
        GRAPHQL_QUERY,
        {"login": USERNAME},
    )

    user = data.get("user")

    if not user:
        raise RuntimeError(f"GitHub user '{USERNAME}' was not found.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(generate_svg(user), encoding="utf-8")

    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
