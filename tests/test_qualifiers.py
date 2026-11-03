import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("updater", ROOT / "scripts/update-qualifiers.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
EVENTS = json.loads((ROOT / "src/data/qualifier-events.json").read_text())["events"]
STATUS = (ROOT / "tests/fixtures/team-status.html").read_text()
TEAM_LIST = (ROOT / "tests/fixtures/team-list.html").read_text()


class QualifiersTest(unittest.TestCase):
    def test_actual_norcal_markup(self):
        self.assertEqual(updater.parse_teams(TEAM_LIST), [
            {"number": 30618, "name": "Eclipse", "city": "San Jose"}])
        # The source has malformed </TD tags, plus a registration link in slot two.
        self.assertEqual(updater.parse_assignments(STATUS, 30618, EVENTS), (["TPS_1"], []))

    def test_multiple_assignments_and_unknown_event(self):
        html = STATUS.replace("2nd Play Preferences", "San Jose #2").replace(
            "available after 2nd play registration", "Sacramento_1")
        self.assertEqual(updater.parse_assignments(html, 30618, EVENTS),
                         (["SJ_2", "TPS_1"], ["Sacramento_1"]))

    def test_source_codes_map_to_all_seven_events(self):
        for code in ["FMT_1", "FMT_2", "SJ_1", "SJ_2", "ATH", "TPS_1", "TPS_2"]:
            self.assertEqual(updater.parse_assignments(STATUS.replace("TPS_1", code), 30618, EVENTS), ([code], []))

    def test_no_assignments_is_valid(self):
        self.assertEqual(updater.parse_assignments(STATUS.replace("TPS_1", "n/a"), 30618, EVENTS), ([], []))

    def test_league_teams_have_no_qualifier_slots(self):
        html = '<table><tr><td>Team Number</td><td>3470</td></tr><tr><td>League Participation</td><td>League_EBH</td><td>Pay League Play</td></tr></table>'
        self.assertEqual(updater.parse_assignments(html, 3470, EVENTS), ([], ["League_EBH"]))

    def test_wrong_team_or_missing_slots_fails(self):
        with self.assertRaises(ValueError):
            updater.parse_assignments(STATUS, 12345, EVENTS)
        with self.assertRaises(ValueError):
            updater.parse_assignments(STATUS.replace("QT #3", "Other"), 30618, EVENTS)

    def test_invalid_roster_fails(self):
        for html in ["<html>Maintenance</html>", TEAM_LIST.replace("30618", "???")]:
            with self.assertRaises(ValueError):
                updater.parse_teams(html)

    def test_duplicate_roster_fails(self):
        row = '<tr><td>30618</td><td>Eclipse</td><td>San Jose</td><td>2025</td><td>status</td></tr>'
        with self.assertRaises(ValueError):
            updater.parse_teams(TEAM_LIST.replace("</tbody>", row + "</tbody>"))

    def test_failed_refresh_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assignments.json"
            previous = '{"teams": [{"number":30618}], "updatedAt":"unchanged"}'
            output.write_text(previous)
            with patch("sys.argv", ["update", "--output", str(output)]), patch.object(
                    updater, "fetch", side_effect=["2026–27" + TEAM_LIST, "Maintenance"]), patch.object(updater.time, "sleep"):
                with self.assertRaises(ValueError):
                    updater.main()
            self.assertEqual(output.read_text(), previous)

    def test_season_rollover_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assignments.json"
            with patch("sys.argv", ["update", "--output", str(output)]), patch.object(
                    updater, "fetch", return_value="2027–28" + TEAM_LIST):
                with self.assertRaises(ValueError):
                    updater.main()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
