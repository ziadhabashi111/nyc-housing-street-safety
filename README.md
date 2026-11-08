# Affordable housing and street safety in NYC (Milestone 1)

Do the ZIP codes where affordable housing was completed (2018-2025) see more or fewer traffic crashes?
Data Engineering and Visualization, GIU, Milestone 1.

- Housing: NYC Open Data **hg8x-zxpr** (Affordable Housing Production by Building), 9,551 raw buildings.
- Crashes: NYC Open Data **h9gi-nx95** (Motor Vehicle Collisions - Crashes), 1,043,903 crashes 2018-2025.
- Integration: ZIP code x year (borough x year as fallback). The datasets share no record-level key, so both are aggregated, never joined row by row.

## Files

| File | What it is |
|---|---|
| `Milestone1_Main_updated.ipynb` | Colab notebook: download, cleaning, integration, post-integration cleaning (all outputs saved) |
| `app.py`, `charts_member1.py`, `assets/` | Dash site (dropdowns, ZIP search mode, "Generate Report") |
| `data/housing_clean.csv` | 9,427 buildings, ZIP as a 5-character string |
| `data/transport_clean.csv` | 199,999 crashes, stratified by year (crash-level charts only) |
| `data/crashes_enriched.csv` | `transport_clean` + `housing_group` of each crash's ZIP |
| `data/merged_zip_year.csv` | 1,683 ZIP-years, 228 ZIPs: exact crash totals + completed housing |
| `data/merged_borough_year.csv` | 40 borough-years, includes buildings and crashes with no ZIP |
| `data/housing_excluded_summary.csv`, `data/housing_audit.csv` | What was excluded and the housing verification |

## Run locally

```
pip install -r requirements.txt
python app.py        # http://localhost:8050
```

**Live dashboard: https://nyc-housing-street-safety-tau.vercel.app**

Deploy on Vercel: import the repo as a project (Hobby plan). `vercel.json` + `api/index.py` expose the Dash server; no build command is needed.
The site loads `data/crashes_app.csv.gz` (a slim copy of `crashes_enriched.csv`) to stay under Vercel's size limit; `.vercelignore` leaves the large CSVs out of the deployment.
Plotly is pinned to 5.24.1 because `charts_member1.fig_rq2` uses `Densitymapbox` (deprecated in newer releases).

## Read the CSVs correctly

`housing_group` has a value **"None"** (a ZIP with no completed housing 2018-2025). pandas reads the string
"None" as missing by default. Load with:

```python
pd.read_csv(path, dtype={"zip_code": str}, keep_default_na=False, na_values=[""])
```

Always read `zip_code` as a string, otherwise leading zeros and the 5-digit format are lost.
In `crashes_enriched.csv`, `housing_group = "No ZIP"` means the crash has no ZIP (unknown), which is different from "None".

## Key numbers

- Crashes: 1,043,903 downloaded; 266,590 missing ZIPs recovered from coordinates (BallTree, haversine, max 200 m, flag `zip_recovered`); 77,351 (7.4%) still without ZIP; 17 rows dropped for missing or negative counts.
- Housing: 9,427 buildings in `housing_clean.csv`; 3,542 (37.6%) have no ZIP or no completion year; 4,350 buildings (242,248 units) completed 2018-2025 with ZIP and year.
- Join (ZIP x year outer join): 718 ZIP-years with both, 965 crashes only, 0 housing only. All 242,248 units and 966,552 crashes with a ZIP are preserved (asserted in the notebook).
- `housing_group`: terciles of each ZIP's units completed 2018-2025: 48 High, 48 Medium, 48 Low, 84 None.

## Limitations

- Buildings without a completion year hold 25.9% of all units and are missing from ZIP-level views; buildings without a ZIP hold 0.8%.
- Missing ZIPs are uneven: Staten Island 71.5%, Queens 41.8%, Bronx 16.9%, Brooklyn 15.5%, Manhattan 5.9%. ZIP-level results for Staten Island and Queens are the least reliable.
- 124 of the 9,551 raw buildings (13,213 units) are not in `housing_clean.csv`.
- `affordable_units` excludes `other_income_units`, so it is lower than the raw `all_counted_units` in 1,332 buildings (usually by 1 unit).
- Nearest-neighbour ZIP recovery can assign the wrong ZIP near boundaries. `crashes_enriched` is a 200k sample; ZIP totals use all crashes.
- 2026 is excluded (partial year). Only vehicle 1's contributing factor was downloaded.
- The comparison is correlational: dense, busy areas can have both more housing and more crashes.

## Team

Member 1 (integration, post-integration cleaning, RQ1-RQ2 charts), plus four teammates for housing cleaning, transport cleaning and their charts.
