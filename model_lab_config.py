"""Model Lab configuration for fast local score tuning.

Edit this file first when you want to change what the lab prints or which
athletes/races you want to sanity-check.

The scoring math itself still lives in score_engine.py. The lab is intentionally
read-only: it loads Supabase data, builds scorecards locally, and writes CSV
outputs for review without saving anything back to Supabase.
"""

MODEL_VERSION = "score_engine_v7_openrank_distance_weighted"
DEFAULT_AS_OF_DATE = "2026-06-17"
DEFAULT_TOP_N_EVIDENCE = 4

# Fast default test slice. Override from CLI when needed.
DEFAULT_GENDER = "Men"
DEFAULT_PROFILE = "Long Course / 70.3 + T100"
DEFAULT_TOP_ROWS = 40

# Athletes you want to eyeball every time you tune the model.
WATCHLIST = [
    "Jelle Geens",
    "Morgan Pearson",
    "Matthew Hauser",
    "Henry Graf",
    "Dorian Coninx",
    "Alessio Crociani",
    "Hayden Wilde",
    "Marten Van Riel",
    "Rico Bogen",
    "Taylor Knibb",
    "Ashleigh Gentle",
    "Hanne De Vet",
]

# Plain-English expectations. These are not hard pass/fail tests yet; they are
# notes printed beside watchlist outputs so the rankings can be reviewed quickly.
EXPECTATIONS = {
    "Jelle Geens": "Run should stay elite even if one recent race was bad; one bad race should be a warning, not a collapse.",
    "Morgan Pearson": "For 70.3/T100, should get meaningful short-course transfer credit, especially swim/run/overall.",
    "Matthew Hauser": "Short-course star; should not rank as proven long-course unless backed by actual LC evidence.",
    "Henry Graf": "WTCS/short-course evidence should matter strongly for Short Course profile.",
    "Taylor Knibb": "Long-course overall/bike should remain elite with strong evidence.",
    "Ashleigh Gentle": "Long-course/T100 consistency should be rewarded.",
    "Hanne De Vet": "Long-course evidence should be visible and explainable through references.",
}

# Race search examples for the local lab. Override with --race.
SAMPLE_RACE_QUERIES = [
    "T100",
    "World Triathlon",
    "IRONMAN 70.3",
]


