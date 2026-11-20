#!/usr/bin/env python3
"""Rate published NorCal teams using auditable FTCScout historical results."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.ftcscout.org/graphql"
RUBRIC = json.loads((ROOT / "src/data/team-rating-rubric.json").read_text())
OFFICIAL_TYPES = {"LeagueMeet", "Qualifier", "LeagueTournament", "SuperQualifier", "Championship", "FIRSTChampionship"}
QUALIFIER_TYPES = {"Qualifier", "LeagueTournament", "SuperQualifier"}
EVENT_FIELDS = "season code name type divisionCode finished start"


def graphql(query):
    for attempt in range(3):
        try:
            request = Request(ENDPOINT, data=json.dumps({"query": query}).encode(), headers={
                "Content-Type": "application/json",
                "User-Agent": "Eclipse30618-HistoryRatings/1.0 (+https://eclipse30618.com/qualifiers/)"})
            with urlopen(request, timeout=90) as response:
                payload = json.load(response)
            if payload.get("errors") or not isinstance(payload.get("data"), dict):
                raise ValueError(f"FTCScout returned incomplete data: {payload.get('errors')}")
            return payload["data"]
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def batch_query(fields):
    result = {}
    # Small sequential GraphQL batches avoid hundreds of individual REST calls.
    for start in range(0, len(fields), 8):
        time.sleep(0.5)
        result.update(graphql("{" + " ".join(fields[start:start + 8]) + "}"))
        if start % 80 == 0 or start + 8 >= len(fields):
            print(f"History queries: {min(start + 8, len(fields))}/{len(fields)}", flush=True)
    return result


def event_evidence(event, record=None):
    result = {key: event[key] for key in ("season", "code", "name", "type")}
    result["url"] = f"https://ftc-events.firstinspires.org/{event['season']}/{event['code']}"
    if record is not None:
        result["record"] = record
    return result


def official(event):
    return (RUBRIC["firstSeason"] <= event["season"] <= RUBRIC["lastSeason"]
            and event["finished"] and event["type"] in OFFICIAL_TYPES)


def rate_team(team, participations):
    if team is None:
        return {"score": None, "reason": "No team history available from FTCScout.", "evidence": None,
                "rookieYear": None, "seasons": [], "eventsWithRecords": 0, "bestQualificationRecord": None}
    candidates = []
    records = []
    played = set()

    def milestone(score, event, record=None):
        candidates.append((score, event["season"], event["start"], event["code"], event_evidence(event, record)))

    for participation in participations:
        event = participation["event"]
        if not official(event):
            continue
        stats = participation["stats"]
        if stats is None:
            continue
        matches = stats.get("qualMatchesPlayed", 0)
        if not isinstance(matches, int) or matches < 0:
            raise ValueError("Invalid qualification match count")
        if matches > 0:
            played.add((event["season"], event["code"]))
            if event["type"] == "FIRSTChampionship":
                milestone(8, event)
            elif event["type"] == "Championship":
                milestone(4, event)
        if all(key in stats for key in ("wins", "losses", "ties")):
            record = {key: stats[key] for key in ("wins", "losses", "ties")}
            if any(not isinstance(value, int) or value < 0 for value in record.values()):
                raise ValueError("Invalid qualification record")
            total = sum(record.values())
            if total:
                records.append((record["wins"] / total, total, event["season"], event["code"], event_evidence(event, record)))
                if record["wins"]:
                    milestone(3 if total >= 5 and record["wins"] / total >= 0.5 else 2, event, record)
                else:
                    milestone(1, event, record)

    for award in team["awards"]:
        event = award["event"]
        if not official(event):
            continue
        kind = award["type"]
        if kind in {"DeansListFinalist", "DeansListSemiFinalist", "DeansListWinner", "Compass", "Promote"}:
            continue
        division = bool(event["divisionCode"]) or kind in {"DivisionWinner", "DivisionFinalist"}
        # Only alliance awards prove finals. Inspire/Dean's List never count as match finals.
        winner = kind in {"Winner", "DivisionWinner"}
        finalist = kind in {"Finalist", "DivisionFinalist"}
        if event["type"] == "FIRSTChampionship":
            milestone((9 if division else 10) if winner or finalist else 8, event)
        elif event["type"] == "Championship":
            milestone(6 if division and (winner or finalist) else 7 if winner else 6 if finalist else 4, event)
        elif event["type"] in QUALIFIER_TYPES and (winner or finalist):
            milestone(5 if winner else 4, event)

    best = max(candidates, key=lambda item: item[:4]) if candidates else None
    best_record = max(records, key=lambda item: item[:4])[-1] if records else None
    score = best[0] if best else 1 if team["rookieYear"] == RUBRIC["lastSeason"] else None
    label = next((level["label"] for level in RUBRIC["levels"] if level["score"] == score), "History unavailable")
    if score is None:
        reason = "No scored official results found in the available history."
    elif score == 1 and not best:
        reason = f"{team['rookieYear']} rookie; no scored official results yet."
    elif score == 1:
        reason = "No qualification match wins in the available official records."
    else:
        reason = label + "."
    return {"score": score, "reason": reason, "evidence": best[-1] if best else None,
            "rookieYear": team["rookieYear"],
            "seasons": sorted(year for year in team["activeSeasons"] if RUBRIC["firstSeason"] <= year <= RUBRIC["lastSeason"]),
            "eventsWithRecords": len(played), "bestQualificationRecord": best_record}


def collect(numbers, cached_histories=None):
    cached_histories = cached_histories if cached_histories is not None else {}
    metadata = batch_query([
        f"t{number}:teamByNumber(number:{number})" + "{number rookieYear activeSeasons awards{type event{" + EVENT_FIELDS + "}}}"
        for number in numbers])
    if set(metadata) != {f"t{number}" for number in numbers}:
        raise ValueError("FTCScout omitted requested teams")
    fields = []
    histories = {}
    for number in numbers:
        team = metadata[f"t{number}"]
        if team is None:
            continue
        if team["number"] != number:
            raise ValueError(f"FTCScout returned the wrong team for {number}")
        for year in team["activeSeasons"]:
            if not RUBRIC["firstSeason"] <= year <= RUBRIC["lastSeason"]:
                continue
            alias = f"t{number}s{year}"
            if year < RUBRIC["lastSeason"] and alias in cached_histories:
                histories[alias] = cached_histories[alias]
                continue
            stat_type = f"TeamEventStats{year}" + ("Trad" if year in (2020, 2021) else "")
            # Remote 2020/2021 events had no win/loss record and cannot earn win-based points.
            remote = f"... on TeamEventStats{year}Remote{{qualMatchesPlayed}}" if year in (2020, 2021) else ""
            fields.append(f"t{number}s{year}:teamByNumber(number:{number})" + "{" + f"events(season:{year})" + "{event{" + EVENT_FIELDS + "} stats{" + f"... on {stat_type}" + "{wins losses ties qualMatchesPlayed} " + remote + "}}}")
    print(f"Fetching {len(fields)} team-season histories for {len(numbers)} teams", flush=True)
    fetched = batch_query(fields)
    if set(fetched) != {field.split(":", 1)[0] for field in fields}:
        raise ValueError("FTCScout omitted requested team-season histories")
    histories.update(fetched)
    ratings = {}
    for number in numbers:
        team = metadata[f"t{number}"]
        events = []
        if team is not None:
            for year in team["activeSeasons"]:
                if RUBRIC["firstSeason"] <= year <= RUBRIC["lastSeason"]:
                    history = histories[f"t{number}s{year}"]
                    if history is None:
                        raise ValueError(f"Team {number} history disappeared during refresh")
                    events.extend(history["events"])
        ratings[str(number)] = rate_team(team, events)
        print(f"{number}: {ratings[str(number)]['score']} — {ratings[str(number)]['reason']}", flush=True)
    # Commit cached raw records only after every team has been scored successfully.
    # Keep records for teams temporarily absent from the NorCal roster.
    cached_histories.update({key: value for key, value in histories.items()
                             if int(key.rsplit("s", 1)[1]) < RUBRIC["lastSeason"]})
    return ratings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "src/data/team-ratings.json")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/team-history.json")
    parser.add_argument("--refresh-history", action="store_true",
                        help="Refetch completed seasons as well as current-season results")
    args = parser.parse_args()
    assignments = json.loads((ROOT / "src/data/qualifier-assignments.json").read_text())
    numbers = [team["number"] for team in assignments["teams"]]
    cached_histories = {}
    if args.cache.exists() and not args.refresh_history:
        cache = json.loads(args.cache.read_text())
        if cache.get("version") == 1:
            cached_histories = cache["histories"]
    ratings = collect(numbers, cached_histories)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    cache_temporary = args.cache.with_suffix(".tmp")
    cache_temporary.write_text(json.dumps({"version": 1, "histories": cached_histories}) + "\n")
    cache_temporary.replace(args.cache)
    payload = {"updatedAt": datetime.now(timezone.utc).isoformat(), "source": "https://ftcscout.org/api",
               "firstSeason": RUBRIC["firstSeason"], "lastSeason": RUBRIC["lastSeason"],
               "rubricVersion": RUBRIC["version"], "teams": ratings}
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(args.output)
    print(f"Saved {len(ratings)} ratings to {args.output}")


if __name__ == "__main__":
    main()
