import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ratings", ROOT / "scripts/update-team-ratings.py")
ratings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ratings)


def event(kind="Qualifier", **changes):
    return {"season": 2025, "code": "TEST", "name": "Test event", "type": kind,
            "divisionCode": None, "finished": True, "start": "2026-01-01", **changes}


def team(awards=None, rookie=2025):
    return {"number": 30618, "rookieYear": rookie, "activeSeasons": [2025, 2026], "awards": awards or []}


def participation(wins, losses, kind="Qualifier", **changes):
    return {"event": event(kind, **changes), "stats": {
        "wins": wins, "losses": losses, "ties": 0, "qualMatchesPlayed": wins + losses}}


class TeamRatingTests(unittest.TestCase):
    def test_all_ten_levels(self):
        cases = [
            (10, "FIRSTChampionship", "Winner", None),
            (10, "FIRSTChampionship", "Finalist", None),
            (9, "FIRSTChampionship", "Winner", "FTCCMP1"),
            (9, "FIRSTChampionship", "DivisionFinalist", None),
            (8, "FIRSTChampionship", "Inspire", None),
            (7, "Championship", "Winner", None),
            (6, "Championship", "Finalist", None),
            (6, "Championship", "Winner", "REGIONAL"),
            (5, "Qualifier", "Winner", None),
            (5, "LeagueTournament", "Winner", None),
            (4, "SuperQualifier", "Finalist", None),
        ]
        for expected, kind, award_type, division in cases:
            with self.subTest(expected=expected, kind=kind, award=award_type, division=division):
                result = ratings.rate_team(team([{"type": award_type, "event": event(kind, divisionCode=division)}]), [])
                self.assertEqual(result["score"], expected)
        for expected, wins, losses in [(3, 3, 2), (2, 1, 4), (1, 0, 5)]:
            self.assertEqual(ratings.rate_team(team(), [participation(wins, losses)])["score"], expected)

    def test_worlds_roster_is_not_proof_of_finals(self):
        records = [{"event": event("FIRSTChampionship"), "stats": None},
                   participation(4, 6, "FIRSTChampionship", divisionCode="FTCCMP1")]
        self.assertEqual(ratings.rate_team(team(), records)["score"], 8)
        self.assertIsNone(ratings.rate_team(team(), records[:1])["score"])

    def test_championship_qualifying_matches_prove_participation(self):
        self.assertEqual(ratings.rate_team(team(), [participation(1, 4, "Championship")])["score"], 4)

    def test_individual_awards_do_not_prove_worlds_participation(self):
        for kind in ["DeansListFinalist", "DeansListWinner", "Compass", "Promote"]:
            award = {"type": kind, "event": event("FIRSTChampionship")}
            self.assertEqual(ratings.rate_team(team([award]), [participation(1, 4)])["score"], 2)

    def test_highest_milestone_wins_and_has_evidence(self):
        awards = [{"type": "Finalist", "event": event("FIRSTChampionship", season=2022, code="WORLDS")},
                  {"type": "Winner", "event": event("Qualifier")}]
        result = ratings.rate_team(team(awards), [participation(5, 0)])
        self.assertEqual(result["score"], 10)
        self.assertEqual(result["evidence"]["url"], "https://ftc-events.firstinspires.org/2022/WORLDS")

    def test_new_rookies_and_missing_history_are_different(self):
        self.assertEqual(ratings.rate_team(team(rookie=2026), [])["score"], 1)
        self.assertIsNone(ratings.rate_team(team(rookie=2024), [])["score"])
        self.assertIsNone(ratings.rate_team(None, [])["score"])

    def test_win_rate_requires_five_matches(self):
        self.assertEqual(ratings.rate_team(team(), [participation(1, 0)])["score"], 2)
        self.assertEqual(ratings.rate_team(team(), [participation(3, 3)])["score"], 3)
        self.assertEqual(ratings.rate_team(team(), [participation(2, 3)])["score"], 2)

    def test_incomplete_unofficial_and_outside_window_ignored(self):
        records = [participation(5, 0, kind) for kind in ["OffSeason", "Scrimmage", "Premier", "Other", "NonAdvancement"]]
        records += [participation(5, 0, finished=False), participation(5, 0, season=2018)]
        self.assertIsNone(ratings.rate_team(team(), records)["score"])

    def test_remote_event_never_creates_fake_wins(self):
        remote = {"event": event(season=2020), "stats": {"qualMatchesPlayed": 6}}
        self.assertIsNone(ratings.rate_team(team(), [remote])["score"])

    def test_bad_stats_fail_instead_of_creating_a_rating(self):
        record = participation(1, 4)
        record["stats"]["wins"] = -1
        with self.assertRaises(ValueError):
            ratings.rate_team(team(), [record])

    def test_partial_source_response_fails(self):
        with patch.object(ratings, "batch_query", return_value={}):
            with self.assertRaises(ValueError):
                ratings.collect([30618])

    def test_cached_seasons_reused_but_current_season_refreshed(self):
        cache = {"t30618s2025": {"events": [participation(3, 2)]}}
        current = {"events": [participation(1, 4, season=2026)]}
        with patch.object(ratings, "batch_query", side_effect=[
                {"t30618": team()}, {"t30618s2026": current}]) as query:
            result = ratings.collect([30618], cache)
        self.assertEqual(result["30618"]["score"], 3)
        self.assertNotIn("season:2025", " ".join(query.call_args_list[1].args[0]))
        self.assertIn("season:2026", " ".join(query.call_args_list[1].args[0]))
        self.assertNotIn("t30618s2026", cache)

    def test_new_team_fetches_missing_history_and_retains_absent_teams(self):
        cache = {"t524s2025": {"events": []}}
        with patch.object(ratings, "batch_query", side_effect=[
                {"t30618": team()},
                {"t30618s2025": {"events": [participation(1, 4)]},
                 "t30618s2026": {"events": []}}]):
            ratings.collect([30618], cache)
        self.assertIn("t30618s2025", cache)
        self.assertIn("t524s2025", cache)
        self.assertNotIn("t30618s2026", cache)

    def test_partial_refresh_does_not_mutate_history_cache(self):
        cache = {"t30618s2025": {"events": []}}
        previous = json.dumps(cache)
        with patch.object(ratings, "batch_query", side_effect=[{"t30618": team()}, {}]):
            with self.assertRaises(ValueError):
                ratings.collect([30618], cache)
        self.assertEqual(json.dumps(cache), previous)

    def test_disk_cache_round_trip_and_manual_history_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ratings.json"
            cache = Path(directory) / "cache/history.json"
            history = {"t30618s2025": {"events": []}}
            def collect(numbers, cached):
                cached.update(history)
                return {}
            with patch("sys.argv", ["update", "--output", str(output), "--cache", str(cache)]), patch.object(
                    ratings, "collect", side_effect=collect) as mocked:
                ratings.main()
                self.assertEqual(mocked.call_args.args[1], history)
            self.assertEqual(json.loads(cache.read_text())["histories"], history)
            with patch("sys.argv", ["update", "--output", str(output), "--cache", str(cache)]), patch.object(
                    ratings, "collect", return_value={}) as mocked:
                ratings.main()
                self.assertEqual(mocked.call_args.args[1], history)
            with patch("sys.argv", ["update", "--output", str(output), "--cache", str(cache),
                                    "--refresh-history"]), patch.object(
                    ratings, "collect", return_value={}) as mocked:
                ratings.main()
                self.assertEqual(mocked.call_args.args[1], {})

    def test_failed_refresh_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ratings.json"
            cache = Path(directory) / "history.json"
            previous_cache = '{"version": 1, "histories": {}}'
            cache.write_text(previous_cache)
            previous = '{"updatedAt": "unchanged", "teams": {}}'
            output.write_text(previous)
            with patch("sys.argv", ["update", "--output", str(output), "--cache", str(cache)]), patch.object(
                    ratings, "collect", side_effect=ValueError("Partial API response")):
                with self.assertRaises(ValueError):
                    ratings.main()
            self.assertEqual(output.read_text(), previous)
            self.assertEqual(cache.read_text(), previous_cache)


if __name__ == "__main__":
    unittest.main()
