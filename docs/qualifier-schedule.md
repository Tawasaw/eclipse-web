# NorCal qualifier schedule

The `/qualifiers/` page shows BIOBUZZ 2026–27 assignments from the public
[NorCal team list](https://www.norcalftc.org/norcal-ftc-team-list-new/) and each
team's linked status page. Filter by team name/number and event together.
The filters are saved in the URL, so `/qualifiers/?team=30618` links to Eclipse.
Teams are organized into dated qualifiers, individual leagues, and other
individual event codes. The league/event selector has matching sections and
can show a single competition or an entire category. For example,
`/qualifiers/?event=League_EB` shows that league, while `?event=leagues` shows
all leagues. Category headings disappear when their groups do not match the
active filters. Counts continue to count each matching team once.
Selecting a team opens its official FIRST team page at
`https://ftc-events.firstinspires.org/team/{team-number}`. A separate **NorCal
status** link opens that team’s local assignment and registration status page.

## Nightly refresh

The existing **Deploy site to GitHub Pages** workflow runs daily at 10:23 UTC
(2:23 AM Pacific standard time / 3:23 AM Pacific daylight time). GitHub may
delay scheduled runs. Once these changes are on `main`, no additional token
or service is needed. The workflow can also be run manually from GitHub Actions.

Every deployment refreshes NorCal assignments before building, including
scheduled, manual, and push runs. Snapshots are included in the Pages artifact;
the workflow does not create commits or push changes to the repository. Local
builds use the checked-in snapshots and do not require network access.

Push deployments restore the latest compatible ratings snapshot from GitHub
Actions cache and skip FTCScout entirely. If the cache is missing or evicted,
they use the checked-in ratings snapshot with its original refresh timestamp.
New teams without a saved rating appear as Unrated until the next refresh.
Scheduled and manual runs refresh ratings after fetching the current NorCal
roster. A refresh failure stops deployment, preserving the previous published
page and its successful refresh timestamps.

Successful ratings refreshes and builds save both calculated ratings and raw
completed-season records in Actions cache. Each refresh uses a new cache key;
later deployments restore the most recent compatible key. Changes to the
ratings script or rubric invalidate the CI cache. The first refresh after a
cache miss fetches all history again; subsequent runs reuse completed seasons.
Cache storage is an optimization, so the checked-in snapshot remains the offline
fallback.

To pick up corrections to completed seasons, run the workflow manually with
**Refetch all completed seasons to pick up historical corrections** checked.
Without that option, nightly and manual updates fetch team metadata/awards,
current-season results, and any missing completed-season records for new teams.

The updater uses Python's standard library, requests pages one at a time,
pauses between teams, and retries transient network errors. It collects only
team number, name, city, and qualifier assignments. Eligibility, consent, and
coach fields are not saved.

If any status page fails or its format changes, the refresh fails before
replacing the data. The build/deployment then stops, leaving the last deployed
site available. GitHub Actions shows the failed run. The page displays its last
successful refresh time and a notice when that is more than two days old.

## Refresh the checked-in snapshot locally

```sh
python3 scripts/update-qualifiers.py
python3 scripts/update-team-ratings.py
python3 -m unittest discover -s tests -v
npm run build
```

The ratings updater stores raw completed-season records in the ignored
`.cache/team-history.json`. Use `--refresh-history` to refetch all past results,
or `--cache /path/to/history.json` to select another local cache file.

Review `src/data/qualifier-assignments.json` before committing. This JSON is the
offline snapshot used by regular builds. The first collection can take several
minutes for the full NorCal roster.

## Dates and event codes

`src/data/qualifier-events.json` contains the seven dates, locations, and
capacities from the supplied 2026 NorCal qualifying preference table. For
example, `TPS_1` maps to **TPS #1**, December 5, 2026, at The Play Space.
Codes match without spaces, underscores, punctuation, or case; no fuzzy matches
or inferred dates are used. Additional published codes and league teams appear
in their own groups under **Leagues** or **Other events**, where visitors can follow the team’s official FIRST page link.
Add confirmed dates/codes to this configuration as the season expands.

Registration/preference links are not assignments. Teams with no published
assignments appear in their own group. Assignment counts are independent of
the active team search and are not a statement of available spots.

The updater refuses a different season and unexpectedly large roster drops.
Before the next season, review the season guard, event configuration, page
copy, and fixtures. Parser regression tests use reduced public HTML fixtures
from NorCal, including its malformed closing cell tags.

## Historical team ratings

Every team has a badge beside its name and expandable **Rating details**.
The details include the reason, an official event link, the best available
event qualification record, and seasons checked. FIRST and NorCal team links
remain available. The page also includes the complete scoring rubric.

`scripts/update-team-ratings.py` batches public GraphQL queries to
`https://api.ftcscout.org/graphql`. It fetches metadata, alliance awards, and
event qualification records for the available 2019–2026 season starts. No API
key or extra Python packages are needed. The rubric's `lastSeason` is the active
season: its results are always fetched, while earlier seasons are cached.
Review this setting at season rollover. Requests run sequentially with a pause
between small batches. A failed or partial response cannot replace
`src/data/team-ratings.json`.

`src/data/team-rating-rubric.json` defines the displayed levels and historical
window. The scorer uses the team's highest completed official event milestone:

| Score | Recorded achievement |
| --- | --- |
| 10 | Worlds overall winning or finalist alliance |
| 9 | Worlds division winning or finalist alliance |
| 8 | Worlds match participation or team award |
| 7 | Regional/state overall winning alliance |
| 6 | Regional/state overall finalist or division winner/finalist |
| 5 | Qualifier, super qualifier, or league tournament winning alliance |
| 4 | Qualifier/league tournament finalist or regional/state participation |
| 3 | At least 50% qualification wins in one completed event with at least five matches |
| 2 | At least one recorded qualification win |
| 1 | Current-season rookie without results, or available official results with zero qualification wins |

Missing historical data is **Unrated**, not evidence of zero wins. Older history
may be incomplete. This is an Eclipse achievement rubric, not an official FIRST
ranking or a current-performance prediction; it has no recency decay.

Worlds roster entries without a match record do not prove finals or attendance.
Only alliance winner/finalist awards earn 9–10; individual Dean's List/Compass
and Promote awards do not establish robot participation. Practice, scrimmage,
off-season, premier invitational, and future/incomplete events are excluded.
The best event qualification record is shown instead of a pooled record to
avoid double counting league standings that can contain earlier league meets.
Tests cover all ten levels, division/overall distinctions, rookies vs. absent
history, qualification thresholds, excluded events, and failed-refresh retention.
