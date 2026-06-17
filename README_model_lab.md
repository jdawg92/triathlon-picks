# Local Model Lab

Use this to tune rankings without waiting for Streamlit deploys.

## Install

From the repo root:

```bash
pip install -r requirements.txt
```

Make sure these files are in the repo root:

```text
model_lab.py
model_lab_config.py
score_engine.py
```

Make sure Supabase secrets exist in either environment variables or `.streamlit/secrets.toml`:

```toml
SUPABASE_URL = "..."
SUPABASE_SERVICE_KEY = "..."
```

## First run

Pull the local cache from Supabase and build the default test slice:

```bash
python model_lab.py --refresh
```

This creates:

```text
model_lab_cache/
model_lab_outputs/
```

## Fast tuning loop

After the first run, do not refresh unless the data changed.

```bash
python model_lab.py --profile "Long Course / 70.3 + T100" --gender Men
```

Then edit `score_engine.py` and rerun the same command. This should be much faster than redeploying Streamlit.

## Test short course

```bash
python model_lab.py --profile "Short Course / WTCS" --gender Men
```

## Test a start-list race

```bash
python model_lab.py --race "World Triathlon" --profile "Short Course / WTCS" --gender Men
```

## Build all slices locally

```bash
python model_lab.py --all-slices
```

## Output files

Outputs are saved to `model_lab_outputs/`:

```text
*_scorecards.csv
*_evidence.csv
*_logs.csv
*_watchlist.csv
*_race_overall.csv
*_race_swim.csv
*_race_bike.csv
*_race_run.csv
```

## What to inspect

For rankings, compare:

```text
score
performance_score
prior_score
reliability_weight
evidence_count
prior_evidence_count
confidence
```

Use the watchlist to sanity-check athletes like Jelle Geens, Morgan Pearson, Taylor Knibb, and others before committing.
