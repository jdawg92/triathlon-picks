# Triathlon Picks

Triathlon Picks is a Streamlit + Supabase app for triathlon race prediction, athlete rankings, split analysis, and evidence-backed scorecards. The app imports public ProTriNews / TriNews API data, stores it in Supabase, builds a clean scoring pool, and generates athlete scorecards used by the dashboard.

The core workflow is:

```text
TriNews API
  → trinews_* source tables
  → scoring_result_pool
  → athlete_scorecards + athlete_scorecard_evidence
  → race dashboard / rankings
```

## What the app does

The app is built to answer questions like:

- Who are the strongest overall athletes on a start list?
- Who has the best swim, bike, or run profile for this race type?
- Which results support an athlete’s score?
- Is an athlete proven, low-sample/high-ceiling, or backed by cross-distance history?
- How complete is the imported API data?

The app is not meant to rank athletes from one isolated race result. It creates scorecards from recent race evidence, field strength, race relevance, discipline performance, and reliability.

## Current app pages

The intended user-facing pages are:

- **Race Dashboard** — race/start-list predictions and split picks.
- **Athlete Rankings** — global ranking views by race profile and discipline.
- **Race Lookup** — search and inspect races.
- **Start Lists** — view/import/migrate start-list data.
- **Athletes** — search athlete profiles.
- **API Sync** — staged TriNews API import tools.
- **Model Cache** — build scoring pool and scorecards.
- **Connection** — Supabase connection/status checks.

Legacy/internal pages such as old CSV import flows, database viewer, data-quality audit, command center, split audit, and gender tools should stay hidden or removed unless actively being debugged.

## Data architecture

### Source/API cache tables

These tables store the imported TriNews API data.

```text
trinews_athletes
trinews_races
trinews_results
trinews_start_lists
```

They should be treated as the raw/source-of-truth API cache.

### App display tables

```text
athletes
start_lists
```

These tables are used by the dashboard and UI. Athlete and start-list rows should be linked by stable IDs or canonical URLs when possible.

### Model tables

```text
scoring_result_pool
athlete_scorecards
athlete_scorecard_evidence
```

These are the model-ready and model-output tables.

The new model workflow should use:

```text
trinews_results → scoring_result_pool → athlete_scorecards / athlete_scorecard_evidence
```

Do not use the old `athlete_results` or `race_field_results` tables for the new model workflow. Those were part of the earlier manual/CSV workflow and caused duplicate/upsert issues.

## API sync workflow

Use the API Sync page in stages:

```text
1. Test API pulls
2. Sync athletes
3. Sync races
4. Sync results
5. Sync start lists
6. Build scoring pool
7. Check coverage/status
```

### Athletes

Athletes are imported from the TriNews API into `trinews_athletes` and normalized into `athletes`.

Use TriNews athlete IDs and canonical athlete URLs as stable identity keys. Names should only be display/fallback values because they can vary by casing or formatting.

### Races

Races are imported into `trinews_races`.

Important race fields include:

```text
id
slug
name
date
distance_category
tier
circuit
brand
country
venue
strength_of_field
updated_at
```

### Results

Results are imported by race ID from the TriNews API and stored in `trinews_results`.

The clean API result rows include fields such as:

```text
race_id
athlete_id
program_name
placement
status
finish_time
swim_time
bike_time
run_time
swim_rank
bike_rank
run_rank
points.openrank
points.pto
points.t100
source
updated_at
```

Results should write only to `trinews_results` in the new workflow.

### Start lists

Start-list data may appear in `trinews_start_lists` in two forms:

1. **Athlete rows** — ready to migrate into `start_lists`.
2. **Header-only rows** — race/list metadata with no athlete attached.

A header-only row may look like:

```text
race_id: present
race_slug: present
race_name: present
gender: present
athlete_id: null
athlete_name: null
athlete_slug: null
```

Those rows cannot be migrated directly because they do not contain athletes. Use the safe/batched start-list refetch tool to fetch athlete entries for those cached race headers.

Recommended start-list workflow:

```text
1. API Sync → Sync start lists
2. Migrate cached start lists to app table
3. If rows are header-only, use the batched refetch tool one race at a time
4. Re-run migration after athlete rows exist
```

## Scoring pool

`scoring_result_pool` is the clean model-ready table. It is built from:

```text
trinews_results
+ trinews_races
+ trinews_athletes
```

The scoring pool keeps recent, useful, normalized result rows. It filters out rows that should not drive model rankings.

Common exclusions include:

```text
super sprint
supertri
eliminator formats
continental cups
invalid or missing scoring fields
```

The pool normalizes time fields:

```text
finish_time → finish_seconds
swim_time   → swim_seconds
bike_time   → bike_seconds
run_time    → run_seconds
```

It also carries scoring context:

```text
OpenRank / ORS
SOF / strength of field
race profile
gender
discipline split ranks
status
race date
```

### SOF handling

Strength of field matters because a good split in a weak field should not count the same as a good split in a world-class field.

Preferred SOF logic:

```text
1. Use race strength_of_field if available.
2. If missing, compute race/gender SOF from top OpenRank values.
3. If still missing, cap or flag the row so it cannot create an elite score.
```

A common computed SOF method is the average of the top 10 OpenRank values in a race/gender field.

## Scorecards

`athlete_scorecards` stores the final athlete ranking summaries.

Scorecards are built by:

```text
gender × profile × discipline
```

Profiles:

```text
Long Course / 70.3 + T100
Short Course / WTCS
Full IRONMAN
All
```

Disciplines:

```text
overall
swim
bike
run
```

So one athlete can have multiple scorecards, for example:

```text
Athlete A — Long Course / 70.3 + T100 — overall
Athlete A — Long Course / 70.3 + T100 — swim
Athlete A — Long Course / 70.3 + T100 — bike
Athlete A — Long Course / 70.3 + T100 — run
Athlete A — Short Course / WTCS — overall
...
```

This lets the dashboard choose the right scoring lens for the selected race.

For example:

```text
T100 race overall pick  → Long Course / overall score
T100 fastest swim pick  → Long Course / swim score
WTCS overall pick       → Short Course / overall score
Full IRONMAN run pick   → Full IRONMAN / run score
```

## Evidence rows

`athlete_scorecard_evidence` stores the race results that support each scorecard.

Evidence rows explain why an athlete received a score. They should include:

```text
race name
race date
profile
discipline
split seconds / split time
placement / split rank
SOF
OpenRank / ORS
individual evidence score
```

Evidence rows are not meant to include every scoring-pool row. They are the top selected reference rows, usually the top 5, that explain the scorecard.

This makes the model explainable instead of just displaying a black-box ranking.

## Scoring overview

At a high level:

```text
split performance
+ field strength
+ race relevance
+ recency
+ consistency/reliability
= ranking score
```

For split disciplines, the score considers:

```text
split rank
time gap to the best split
field strength / SOF
race relevance
recency
```

For overall score, the model uses ORS/OpenRank when available, then applies recency and race relevance.

## Reliability-adjusted rankings

The rankings should not be driven only by one outstanding result.

The model should distinguish between:

- A proven athlete with repeated strong evidence.
- A short-course athlete with one strong long-course result and strong transfer potential.
- An injured/inactive athlete with one recent race but strong historical proof.
- A one-race athlete with no supporting evidence.
- A proven elite athlete who had one bad race.

The current desired ranking concept is:

```text
ranking_score =
performance_score × reliability_weight
+ prior_score × (1 - reliability_weight)
```

Where:

```text
performance_score   = what the recent evidence shows
reliability_weight  = how much we trust the recent sample
prior_score         = backup ability from older/same-profile/all-profile/cross-profile evidence
```

A one-race athlete can still show a high ceiling, but should not automatically outrank a proven athlete with multiple elite results.

A proven athlete with one bad race should not be buried if their broader evidence remains strong.

## Model version

Use the current scorecard model version consistently across app, engine, scorecards, evidence, and dashboard filters:

```text
score_engine_v6_reliability_prior
```

If this changes, rebuild all scorecards and ensure dashboard filters are updated to the same version.

## Model Cache workflow

Recommended workflow after syncing new API results:

```text
1. Build or rebuild scoring_result_pool
2. Clear existing scorecards for the current model version
3. Rebuild scorecards
4. Confirm counts
5. Refresh dashboard/rankings
```

Important: `scoring_result_pool` row count is not expected to match scorecard or evidence row counts.

Example:

```text
scoring_result_pool rows: 21,216
scorecard rows: 4,455
evidence rows: 8,458
```

That can be valid because:

- scoring pool rows = every eligible race result
- scorecard rows = athlete/profile/discipline summaries
- evidence rows = selected top reference rows used to explain scorecards

## Performance notes

Streamlit/PostgREST requests can time out on long-running database jobs, often around 10 seconds. Avoid one giant request for heavy rebuilds.

Use one of these strategies:

```text
Database-side SQL/RPC
small batches
pagination in 1,000-row pages
slice-by-slice rebuilds
```

Do not fetch 20k+ rows and write everything row-by-row unless the page is explicitly built to handle it safely.

Supabase often caps returned rows at around 1,000 rows per request. Any function that reads many rows should use pagination with 1,000-row pages and continue until a short page is returned.

## Environment variables / secrets

The app expects Supabase and TriNews credentials in Streamlit secrets.

Required secrets:

```toml
SUPABASE_URL = "..."
SUPABASE_SERVICE_KEY = "..."
TRINEWS_API_KEY = "..."
```

For local development, use `.streamlit/secrets.toml`.

Do not commit real secrets to GitHub.

## Local setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Run locally:

```bash
streamlit run streamlit_app.py
```

If using a separate requirements file, make sure it includes:

```text
streamlit
supabase
pandas
numpy
requests
```

## Deployment

The app is intended for Streamlit Cloud deployment from GitHub.

Typical deploy flow:

```text
1. Save updated streamlit_app.py and helper files.
2. Commit changes.
3. Push to GitHub.
4. Streamlit Cloud redeploys.
5. Confirm the app shows the new UI labels/version.
```

## Troubleshooting

### Scorecard rebuild only creates a small number of scorecards

Check that the app loaded the full scoring pool, not just the first page.

Expected:

```text
Loaded ~21,216 scoring-pool rows
```

If it loads around 1,000 rows, pagination is broken or the deployed file is stale.

### Scorecard model version mismatch

Make sure all references use the same version:

```text
score_engine_v6_reliability_prior
```

Check:

```text
streamlit_app.py
score_engine.py
athlete_scorecards.model_version
athlete_scorecard_evidence.model_version
dashboard filters
ranking filters
```

### Start-list migration says no migratable rows

Inspect the cached row shape.

If the row has no athlete data:

```text
athlete_id: null
athlete_name: null
athlete_slug: null
```

then it is a header-only start-list row. It cannot migrate until athlete entries are fetched.

Use the batched refetch tool one race at a time.

### PostgREST statement timeout

If an app button fails with:

```text
canceling statement due to statement timeout
```

the job is too large for a single Streamlit/API request. Convert it to a batched job or run it directly in Supabase SQL Editor.

### Dashboard missing athletes from a start list

Check that `start_lists` rows contain stable identity fields:

```text
athlete_id
athlete_url
athlete_name
race_id
race_slug
gender
```

The dashboard should join by athlete ID or canonical athlete URL where possible, not by name alone.

## Development rules

When editing the app:

- Preserve working dashboard behavior.
- Avoid full rewrites unless necessary.
- Keep public-facing wording clean and non-debuggy.
- Use staged imports and batch tools for long jobs.
- Keep old manual/CSV tables out of the new scoring model path.
- Prefer stable IDs over names.
- Make scorecard rankings explainable through evidence rows.
