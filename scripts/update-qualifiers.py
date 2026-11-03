#!/usr/bin/env python3
"""Collect public NorCal qualifier assignments; publish only a complete snapshot."""

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TEAM_LIST = "https://www.norcalftc.org/norcal-ftc-team-list-new/"
STATUS = "https://www.norcalftc.org/ftc-team-status/?ftcteam="


class Tables(HTMLParser):
    """Read table cells, including NorCal's malformed closing TD tags."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.feed(html)

    def finish_cell(self):
        if self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
        self.cell = None

    def finish_row(self):
        self.finish_cell()
        if self.row is not None and self.table is not None:
            self.table.append(self.row)
        self.row = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.finish_row()
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.finish_cell()
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.finish_cell()
        elif tag == "tr":
            self.finish_row()
        elif tag == "table" and self.table is not None:
            self.finish_row()
            self.tables.append(self.table)
            self.table = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def parse_teams(html):
    tables = [table for table in Tables(html).tables
              if table and table[0][:3] == ["Team #", "Team Name", "City"]]
    if len(tables) != 1:
        raise ValueError("NorCal team list table is missing or has changed")
    teams = []
    for row in tables[0][1:]:
        if len(row) != 5 or not row[0].isdigit() or not row[1]:
            raise ValueError(f"Unexpected team list row: {row}")
        teams.append({"number": int(row[0]), "name": row[1], "city": row[2]})
    numbers = [team["number"] for team in teams]
    if not teams or len(set(numbers)) != len(numbers):
        raise ValueError("Empty team list or duplicate team numbers")
    return sorted(teams, key=lambda team: team["number"])


def event_key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def parse_assignments(html, number, events):
    tables = [table for table in Tables(html).tables
              if any(row[:2] == ["Team Number", str(number)] for row in table)]
    if len(tables) != 1:
        raise ValueError(f"Team {number}: status table is missing or belongs to another team")
    rows = [row for row in tables[0] if row and re.fullmatch(r"QT\s*#\s*\d+", row[0])]
    leagues = [row for row in tables[0] if row and row[0] == "League Participation"]
    if leagues and not rows:
        rows = leagues
    elif len(rows) != 3 or {re.sub(r"\s", "", row[0]) for row in rows} != {"QT#1", "QT#2", "QT#3"}:
        raise ValueError(f"Team {number}: expected three qualifier slots or league participation")
    known = {event_key(alias): event["id"] for event in events
             for alias in [event["id"], event["name"]]}
    assigned = []
    unmapped = []
    for row in rows:
        if len(row) != 3:
            raise ValueError(f"Team {number}: malformed qualifier row")
        value = row[1]
        event_id = known.get(event_key(value))
        if event_id:
            assigned.append(event_id)
        elif (not value or value.lower() in {"n/a", "none", "tbd", "not assigned", "pending"}
              or re.fullmatch(r"(?:1st|2nd|3rd) Play Preferences", value, re.I)
              or re.fullmatch(r"available after (?:1st|2nd|3rd) play registration", value, re.I)):
            continue
        else:
            # Keep assignments to events outside the supplied seven; never guess a date.
            unmapped.append(value)
    return sorted(set(assigned)), sorted(set(unmapped))


def fetch(url):
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "Eclipse30618-QualifierSchedule/1.0 (+https://eclipse30618.com/qualifiers/)"})
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "src/data/qualifier-assignments.json")
    args = parser.parse_args()
    config = json.loads((ROOT / "src/data/qualifier-events.json").read_text())
    html = fetch(TEAM_LIST)
    if not re.search(r"2026\s*[-–]\s*27", html):
        raise ValueError("NorCal list is no longer the 2026–27 season; review event configuration")
    teams = parse_teams(html)
    if not any(team["number"] == 30618 for team in teams):
        raise ValueError("Eclipse is missing from the team list")
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        if len(teams) < len(previous["teams"]) * 0.9:
            raise ValueError("Team list shrank by more than 10%; retaining previous snapshot")
    for index, team in enumerate(teams, 1):
        time.sleep(0.4)  # One request at a time; avoid hammering the volunteer-run site.
        team["events"], team["unmappedEvents"] = parse_assignments(
            fetch(STATUS + str(team["number"])), team["number"], config["events"])
        print(f"[{index}/{len(teams)}] {team['number']} {team['name']}: {', '.join(team['events'] + team['unmappedEvents']) or 'pending'}", flush=True)
    snapshot = {"season": config["season"], "updatedAt": datetime.now(timezone.utc).isoformat(),
                "source": TEAM_LIST, "teams": teams}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(args.output)
    print(f"Saved complete snapshot of {len(teams)} teams to {args.output}")


if __name__ == "__main__":
    main()
