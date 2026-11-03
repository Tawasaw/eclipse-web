# NorCal qualifier schedule

The `/qualifiers/` page shows BIOBUZZ 2026–27 assignments from the public
[NorCal team list](https://www.norcalftc.org/norcal-ftc-team-list-new/) and each
team's linked status page. Filter by team name/number and event together.
The filters are saved in the URL, so `/qualifiers/?team=30618` links to Eclipse.
Selecting a team opens its official FIRST team page at
`https://ftc-events.firstinspires.org/team/{team-number}`. A separate **NorCal
status** link opens that team’s local assignment and registration status page.

## Nightly refresh

The existing **Deploy site to GitHub Pages** workflow runs daily at 10:23 UTC
(2:23 AM Pacific standard time / 3:23 AM Pacific daylight time). GitHub may
delay scheduled runs. Once these changes are on `main`, no additional token
or service is needed. The workflow can also be run manually from GitHub Actions.

Every deployment refreshes the data before building, including scheduled,
manual, and push runs. This prevents a website push from restoring an older
checked-in snapshot. Snapshots are included in the Pages artifact; the workflow
does not create commits or push changes to the repository. Local builds use the
checked-in snapshot and do not require network access to NorCal.

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
python3 -m unittest discover -s tests -v
npm run build
```

Review `src/data/qualifier-assignments.json` before committing. This JSON is the
offline snapshot used by regular builds. The first collection can take several
minutes for the full NorCal roster.

## Dates and event codes

`src/data/qualifier-events.json` contains the seven dates, locations, and
capacities from the supplied 2026 NorCal qualifying preference table. For
example, `TPS_1` maps to **TPS #1**, December 5, 2026, at The Play Space.
Codes match without spaces, underscores, punctuation, or case; no fuzzy matches
or inferred dates are used. Additional published codes and league teams appear
in **Other events & leagues**, where visitors can follow the team’s official FIRST page link.
Add confirmed dates/codes to this configuration as the season expands.

Registration/preference links are not assignments. Teams with no published
assignments appear in their own group. Assignment counts are independent of
the active team search and are not a statement of available spots.

The updater refuses a different season and unexpectedly large roster drops.
Before the next season, review the season guard, event configuration, page
copy, and fixtures. Parser regression tests use reduced public HTML fixtures
from NorCal, including its malformed closing cell tags.
