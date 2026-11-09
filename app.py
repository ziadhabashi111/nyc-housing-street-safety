"""Milestone 1 dashboard: affordable housing vs. street safety in NYC (ZIP x year).

Run locally:  python app.py          Deploy: gunicorn app:server (or Vercel)
"""
import os
import re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output, State

import charts_member1

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
GROUPS = ["High", "Medium", "Low", "None"]          # housing_group of a ZIP (2018-2025 completed units)
CATEGORIES = ["New Construction", "Preservation"]   # housing category (construction_type)
OUTCOMES = ["Any crash", "Injury crashes", "Fatal crashes"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ---------------------------------------------------------------- data
READ = dict(keep_default_na=False, na_values=[""])   # keep the housing_group label "None" (pandas would read it as NaN)
zip_year = pd.read_csv(f"{DATA}/merged_zip_year.csv", dtype={"zip_code": str}, **READ)
borough_year = pd.read_csv(f"{DATA}/merged_borough_year.csv")
housing = pd.read_csv(f"{DATA}/housing_clean.csv", dtype={"zip_code": str}, **READ,
                      usecols=["borough", "zip_code", "latitude", "longitude", "completion_year",
                               "construction_type", "total_units", "affordable_units"])
# crashes_app.csv.gz = crashes_enriched.csv reduced to the columns used here (smaller, faster to load)
CRASH_FILE = "crashes_app.csv.gz" if os.path.exists(f"{DATA}/crashes_app.csv.gz") else "crashes_enriched.csv"
crashes = pd.read_csv(f"{DATA}/{CRASH_FILE}", dtype={"zip_code": str}, **READ,
                      usecols=["crash_year", "crash_hour", "crash_weekday", "borough", "zip_code",
                               "latitude", "longitude", "persons_injured", "persons_killed",
                               "top_contributing_factor", "housing_group"])
YEARS = (int(zip_year["year"].min()), int(zip_year["year"].max()))
ZIPS = sorted(zip_year["zip_code"].unique())
FACTORS = (crashes[~crashes["top_contributing_factor"].isin(["Unspecified", "Does Not Apply"])]
           ["top_contributing_factor"].value_counts().head(15).index.tolist())

# ---------------------------------------------------------------- filtering
def filter_data(f):
    """f = dict(boroughs, years, group, zip, category, factor, outcome). Returns (z, c, h, b)."""
    y0, y1 = f["years"]
    z = zip_year[zip_year["year"].between(y0, y1)]
    c = crashes[crashes["crash_year"].between(y0, y1)]
    h = housing[housing["completion_year"].between(y0, y1)]
    b = borough_year[borough_year["year"].between(y0, y1)]

    if f.get("zip"):                                  # one ZIP code
        z, c, h = z[z["zip_code"] == f["zip"]], c[c["zip_code"] == f["zip"]], h[h["zip_code"] == f["zip"]]
        b = b[b["borough"].isin(z["borough"].dropna().unique())]
    else:
        if f.get("boroughs"):
            bs = f["boroughs"]
            z, c, h, b = (z[z["borough"].isin(bs)], c[c["borough"].isin(bs)],
                          h[h["borough"].isin(bs)], b[b["borough"].isin(bs)])
        if f.get("group") and f["group"] != "All":
            z, c = z[z["housing_group"] == f["group"]], c[c["housing_group"] == f["group"]]
            h = h[h["zip_code"].isin(z["zip_code"].unique())]

    cat = f.get("category")                           # housing category: keep ZIP-years / buildings of that type
    if cat and cat != "All":
        col = "new_construction_units" if cat == "New Construction" else "preservation_units"
        z = z[z[col] > 0]
        h = h[h["construction_type"] == cat]
        b = b[b[col] > 0]
    fac = f.get("factor")                             # transport category: contributing factor (crash-level charts)
    if fac and fac != "All":
        c = c[c["top_contributing_factor"] == fac]
    out = f.get("outcome")
    if out == "Injury crashes":
        c = c[c["persons_injured"] > 0]
    elif out == "Fatal crashes":
        c = c[c["persons_killed"] > 0]
    return z, c, h, b

# ---------------------------------------------------------------- free-text search
BOROUGH_WORDS = {"BRONX": ["bronx"], "BROOKLYN": ["brooklyn"], "MANHATTAN": ["manhattan"],
                 "QUEENS": ["queens"], "STATEN ISLAND": ["staten island", "staten"]}
FACTOR_WORDS = {"speed": "Unsafe Speed", "alcohol": "Alcohol Involvement", "drunk": "Alcohol Involvement",
                "distract": "Driver Inattention/Distraction", "inattention": "Driver Inattention/Distraction",
                "yield": "Failure to Yield Right-of-Way", "following": "Following Too Closely",
                "tailgat": "Following Too Closely", "backing": "Backing Unsafely",
                "lane": "Unsafe Lane Changing", "traffic control": "Traffic Control Disregarded",
                "inexperience": "Driver Inexperience", "turning": "Turning Improperly"}

def parse_query(text):
    """Turn a sentence like 'Brooklyn 2022 new buildings' into filters. Returns (filters, understood list)."""
    t = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    f = dict(boroughs=BOROUGHS, years=list(YEARS), group="All", zip=None, category="All",
             factor="All", outcome="Any crash")
    seen = []
    bs = [b for b, words in BOROUGH_WORDS.items() if any(re.search(rf"\b{w}\b", t) for w in words)]
    if bs:
        f["boroughs"] = bs
        seen.append("Borough: " + ", ".join(b.title() for b in bs))
    z = [m for m in re.findall(r"\b\d{5}\b", t) if m in ZIPS]
    if z:
        f["zip"] = z[0]
        seen.append(f"ZIP code: {z[0]}")
    # years: ranges, 'since/after', 'before/until', or single years
    lo, hi = YEARS
    rng = re.search(r"\b(20\d{2})\s*(?:-|to|and|through|until)\s*(20\d{2})\b", t)
    since = re.search(r"\b(?:since|after|from)\s+(20\d{2})\b", t)
    until = re.search(r"\b(?:before|until|up to|through)\s+(20\d{2})\b", t)
    singles = [int(y) for y in re.findall(r"\b(20\d{2})\b", t)]
    if rng:
        lo, hi = sorted((int(rng.group(1)), int(rng.group(2))))
    elif since or until:
        if since:
            lo = int(since.group(1))
        if until:
            hi = int(until.group(1))
    elif singles:
        lo, hi = min(singles), max(singles)
    lo, hi = max(lo, YEARS[0]), min(hi, YEARS[1])
    if lo > hi:
        lo, hi = YEARS
    if [lo, hi] != list(YEARS):
        f["years"] = [lo, hi]
        seen.append(f"Years: {lo}" if lo == hi else f"Years: {lo}-{hi}")
    if re.search(r"\bnew\b(?!\s+york)", t):
        f["category"] = "New Construction"
        seen.append("Housing category: New Construction")
    elif re.search(r"preserv|renovat|rehab", t):
        f["category"] = "Preservation"
        seen.append("Housing category: Preservation")
    g = re.search(r"\b(high|medium|low)\s+(?:housing|group)\b|\b(?:housing|group)\s+(high|medium|low)\b", t)
    if g:
        f["group"] = (g.group(1) or g.group(2)).title()
        seen.append(f"Housing group: {f['group']}")
    elif re.search(r"\bno housing\b", t):
        f["group"] = "None"
        seen.append("Housing group: None")
    for fac in FACTORS:
        if fac.lower() in t:
            f["factor"] = fac
            break
    else:
        for word, fac in FACTOR_WORDS.items():
            if word in t and fac in FACTORS:
                f["factor"] = fac
                break
    if f["factor"] != "All":
        seen.append(f"Crash factor: {f['factor']}")
    if re.search(r"fatal|killed|death|deadly", t):
        f["outcome"] = "Fatal crashes"
        seen.append("Crashes: fatal only")
    elif re.search(r"injur", t):
        f["outcome"] = "Injury crashes"
        seen.append("Crashes: injury only")
    return f, seen

# ---------------------------------------------------------------- figures
def kpi(label, value, note=""):
    return html.Div(className="kpi", children=[html.Div(label, className="kpi-label"),
                                               html.Div(value, className="kpi-value"),
                                               html.Div(note, className="kpi-note")])

def empty(msg):
    return charts_member1._empty_figure(msg)

def titled(fig, text):
    """Short chart title in a smaller font so it never gets cut off."""
    fig.update_layout(title=dict(text=text, font=dict(size=15), x=0.01, xanchor="left"))
    return fig

def fig_group_trend(z):
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = (z.groupby(["year", "housing_group"]).agg(crashes=("crash_count", "sum"), zips=("zip_code", "nunique"))
           .reset_index())
    t["crashes_per_zip"] = t["crashes"] / t["zips"]
    fig = px.line(t, x="year", y="crashes_per_zip", color="housing_group", markers=True,
                  template="plotly_white", category_orders={"housing_group": GROUPS},
                  labels={"crashes_per_zip": "Crashes per ZIP", "year": "Year", "housing_group": "Housing group"})
    return titled(fig, "RQ3: Crashes per ZIP by housing group")

def fig_borough(b):
    if b.empty:
        return empty("No data for these filters")
    t = b.groupby("borough").agg(crashes=("crash_count", "sum"), units=("total_units", "sum")).reset_index()
    t["crashes_per_100_units"] = (t["crashes"] / t["units"] * 100).where(t["units"] > 0)
    fig = px.bar(t, x="borough", y="crashes_per_100_units", template="plotly_white",
                 hover_data=["crashes", "units"],
                 labels={"crashes_per_100_units": "Crashes per 100 units completed", "borough": ""})
    return titled(fig, "RQ4: Crashes per 100 housing units, by borough")

def fig_hour_weekday(c):
    if c.empty:
        return empty("No crashes for these filters")
    grid = (c.dropna(subset=["crash_hour"]).groupby(["crash_weekday", "crash_hour"]).size()
              .unstack(fill_value=0).reindex(WEEKDAYS).fillna(0))
    fig = px.imshow(grid, aspect="auto", color_continuous_scale="YlOrRd", template="plotly_white",
                    labels=dict(x="Hour of day", y="", color="Crashes"))
    return titled(fig, "RQ5: When crashes happen (hour x weekday, sample)")

def fig_factors(c):
    if c.empty:
        return empty("No crashes for these filters")
    top = (c[~c["top_contributing_factor"].isin(["Unspecified", "Does Not Apply"])]["top_contributing_factor"]
             .value_counts().head(10).sort_values())
    if top.empty:
        return empty("No stated contributing factor for these filters")
    fig = px.bar(x=top.values, y=top.index, orientation="h", template="plotly_white",
                 labels={"x": "Crashes (sample)", "y": ""})
    fig.update_layout(showlegend=False)
    return titled(fig, "RQ6: Top contributing factors (sample)")

def fig_units_vs_crashes(z):
    """RQ7: yearly completed units (new vs preservation bars) against yearly crashes (line)."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby("year")[["new_construction_units", "preservation_units", "crash_count"]].sum().reset_index()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=t["year"], y=t["new_construction_units"], name="New construction units")
    fig.add_bar(x=t["year"], y=t["preservation_units"], name="Preservation units")
    fig.add_scatter(x=t["year"], y=t["crash_count"], name="Crashes", mode="lines+markers",
                    line=dict(color="black"), secondary_y=True)
    fig.update_layout(barmode="stack", template="plotly_white", legend=dict(orientation="h", y=-0.2))
    fig.update_yaxes(title_text="Housing units completed", secondary_y=False)
    fig.update_yaxes(title_text="Crashes", secondary_y=True)
    return titled(fig, "RQ7: Housing completed vs. crashes, by year")

def fig_road_users(z):
    """RQ8: who gets hurt? share of injured pedestrians / cyclists / motorists by housing group."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby("housing_group")[["ped_injured", "cyc_injured", "motorist_injured"]].sum()
    t = t.div(t.sum(axis=1), axis=0).mul(100).reindex([g for g in GROUPS if g in t.index]).reset_index()
    t = t.melt(id_vars="housing_group", var_name="road_user", value_name="share")
    t["road_user"] = t["road_user"].map({"ped_injured": "Pedestrians", "cyc_injured": "Cyclists",
                                         "motorist_injured": "Motorists"})
    fig = px.bar(t, x="housing_group", y="share", color="road_user", template="plotly_white",
                 labels={"share": "% of injured people", "housing_group": "Housing group", "road_user": ""})
    return titled(fig, "RQ8: Who is injured, by housing group")

def fig_top_zips(z):
    """RQ9: ZIP codes with the most crashes per 100 housing units completed."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby(["zip_code", "borough"]).agg(crashes=("crash_count", "sum"), units=("total_units", "sum")).reset_index()
    t = t[t["units"] >= 100]
    if t.empty:
        return empty("No ZIP codes with at least 100 completed units for these filters")
    t["crashes_per_100_units"] = t["crashes"] / t["units"] * 100
    t = t.nlargest(12, "crashes_per_100_units").sort_values("crashes_per_100_units")
    fig = px.bar(t, x="crashes_per_100_units", y="zip_code", color="borough", orientation="h",
                 template="plotly_white", hover_data=["crashes", "units"],
                 labels={"crashes_per_100_units": "Crashes per 100 units completed", "zip_code": "ZIP code",
                         "borough": ""})
    fig.update_yaxes(type="category")
    return titled(fig, "RQ9: ZIP codes with most crashes per 100 units (>=100 units)")

def fig_income(z):
    """RQ10: which income levels the completed affordable units serve, by borough."""
    cols = {"extremely_low_income_units": "Extremely low", "very_low_income_units": "Very low",
            "low_income_units": "Low", "moderate_income_units": "Moderate",
            "middle_income_units": "Middle", "other_income_units": "Other"}
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby("borough")[list(cols)].sum().rename(columns=cols).reset_index().melt(
        id_vars="borough", var_name="income_tier", value_name="units")
    fig = px.bar(t, x="borough", y="units", color="income_tier", template="plotly_white",
                 labels={"units": "Affordable units completed", "borough": "", "income_tier": "Income tier"})
    return titled(fig, "RQ10: Income tiers served by completed units")

# ---------------------------------------------------------------- layout
STORY = [
    html.H2("The story: does new affordable housing go together with more street danger?"),
    html.H3("Question and why it matters"),
    html.P("New York City builds and preserves thousands of affordable homes every year. Planners and residents ask "
           "whether the neighborhoods that receive them also see more traffic crashes, so that street safety can "
           "be planned together with housing instead of after it."),
    html.H3("What we found"),
    html.Ul([
        html.Li("ZIP codes with the most completed housing (High group) record more crashes per ZIP and year than "
                "Medium and Low ZIP codes (RQ3). ZIP-years with more affordable units also tend to have more "
                "crashes (RQ1), but the link is weak."),
        html.Li("Crashes per 100 units completed are far higher in Staten Island and Queens than in the Bronx "
                "(RQ4), because those boroughs completed far fewer units."),
        html.Li("Recorded crashes fall sharply after 2019 while completed units stay uneven from year to year (RQ7). "
                "The drop may partly reflect events such as the 2020 lockdowns and partly changes in how crashes "
                "are reported."),
        html.Li("Crashes peak between 2 pm and 6 pm and Friday is the busiest day; driver distraction, following "
                "too closely and failing to yield are the most common stated factors (RQ5, RQ6)."),
    ]),
    html.H3("Limits"),
    html.Ul([
        html.Li("Housing and crashes are joined by ZIP code and year, not building by crash, so we show association, "
                "never cause."),
        html.Li("Dense, busy ZIP codes can have both more housing and more crashes (a confounder we do not measure)."),
        html.Li("37.6% of buildings have no ZIP or completion year; 7.4% of crashes still have no ZIP."),
        html.Li("Crash-level charts use a 200k-crash sample; ZIP totals use all crashes."),
    ]),
    html.H3("How this helps NYC"),
    html.P("City agencies can use the ZIP codes with the most crashes per housing unit (RQ9) to place street-safety "
           "work such as signal timing, speed cameras and protected crossings next to new housing, and can check "
           "the time-of-day pattern (RQ5) when scheduling enforcement."),
]

app = Dash(__name__, title="NYC Housing & Street Safety")
server = app.server

app.layout = html.Div(className="page", children=[
    html.H1("Affordable housing and street safety in NYC"),
    html.P("Do the ZIP codes where affordable housing was completed (2018-2025) see more or fewer crashes? "
           "Pick filters or type a question, then press Generate Report.", className="sub"),
    html.Div(className="controls", children=[
        html.Div([html.Label("Mode"),
                  dcc.RadioItems(id="mode", value="explore", inline=True,
                                 options=[{"label": "Explore", "value": "explore"},
                                          {"label": "Search a ZIP code", "value": "search"},
                                          {"label": "Free-text search", "value": "text"}])]),
        html.Div([html.Label("Search"),
                  dcc.Input(id="query", type="text", debounce=False, style={"width": "100%", "padding": "9px"},
                            placeholder="e.g. Brooklyn 2022 new buildings")],
                 id="box-query", className="wide", style={"display": "none"}),
        html.Div([html.Label("Borough"),
                  dcc.Dropdown(id="boroughs", options=BOROUGHS, value=BOROUGHS, multi=True)], id="box-boroughs"),
        html.Div([html.Label("Housing group (ZIP level)"),
                  dcc.Dropdown(id="group", clearable=False, value="All", options=["All"] + GROUPS)], id="box-group"),
        html.Div([html.Label("ZIP code"),
                  dcc.Dropdown(id="zip", options=ZIPS, value=None, placeholder="Type a ZIP code...")],
                 id="box-zip", style={"display": "none"}),
        html.Div([html.Label("Housing category"),
                  dcc.Dropdown(id="category", clearable=False, value="All", options=["All"] + CATEGORIES)],
                 id="box-category"),
        html.Div([html.Label("Crash factor (transport category)"),
                  dcc.Dropdown(id="factor", clearable=False, value="All", options=["All"] + FACTORS)],
                 id="box-factor"),
        html.Div([html.Label("Crash outcome"),
                  dcc.Dropdown(id="outcome", clearable=False, value="Any crash", options=OUTCOMES)],
                 id="box-outcome"),
        html.Div([html.Label("Years"),
                  dcc.RangeSlider(id="years", min=YEARS[0], max=YEARS[1], step=1, value=list(YEARS),
                                  marks={y: str(y) for y in range(YEARS[0], YEARS[1] + 1)})],
                 id="box-years", className="wide"),
        html.Button("Generate Report", id="go", n_clicks=0),
    ]),
    dcc.Loading(html.Div(id="report"), type="circle"),
    html.Div(className="story", children=STORY),
    html.Div(className="notes", children=[
        html.H3("How to read this"),
        html.Ul([
            html.Li("Housing and crashes are compared by ZIP code and year (counts per ZIP), not building by crash."),
            html.Li("housing_group = tercile (High / Medium / Low) of a ZIP's units completed 2018-2025; "
                    "None = no completed housing in that window."),
            html.Li("Housing category keeps ZIP codes and buildings with new construction or preservation units. "
                    "Crash factor and crash outcome apply to the crash-level charts (RQ2, RQ5, RQ6) only."),
            html.Li("3,542 of 9,427 buildings (37.6%) have no ZIP or no completion year and are missing from ZIP-level "
                    "views; Staten Island (71.5% missing ZIP) and Queens (41.8%) are the least reliable."),
            html.Li("7.4% of crashes still have no ZIP after recovery from coordinates; they only appear in the borough view."),
            html.Li("Crash-level charts use a 200k-crash sample stratified by year; ZIP totals use all crashes."),
            html.Li("Correlation only: more housing and more crashes can both come from dense, busy areas."),
        ])]),
])

@app.callback(Output("box-boroughs", "style"), Output("box-group", "style"), Output("box-zip", "style"),
              Output("box-query", "style"), Output("box-category", "style"), Output("box-factor", "style"),
              Output("box-outcome", "style"), Output("box-years", "style"),
              Input("mode", "value"))
def toggle_mode(mode):
    show, hide = {}, {"display": "none"}
    if mode == "text":                      # only the search box is needed
        return hide, hide, hide, show, hide, hide, hide, hide
    if mode == "search":                    # one ZIP code
        return hide, hide, show, hide, show, show, show, show
    return show, show, hide, hide, show, show, show, show

@app.callback(Output("report", "children"), Input("go", "n_clicks"),
              State("mode", "value"), State("boroughs", "value"), State("years", "value"),
              State("group", "value"), State("zip", "value"), State("category", "value"),
              State("factor", "value"), State("outcome", "value"), State("query", "value"))
def generate_report(n, mode, boroughs, years, group, zip_code, category, factor, outcome, query):
    if not n:
        return html.P("Choose filters (or type a search) and press Generate Report.", className="hint")
    understood = None
    if mode == "text":
        if not (query or "").strip():
            return html.P("Type a search first, for example: Brooklyn 2022 new buildings.", className="hint")
        f, seen = parse_query(query)
        if not seen:
            return html.P("Nothing recognised in that search. Try a borough, a year or range, 'new buildings' or "
                          "'preservation', a ZIP code, 'high housing', or a crash factor like 'speed'.",
                          className="hint")
        understood = html.P("Understood as: " + " | ".join(seen), className="understood")
    else:
        if mode == "search" and not zip_code:
            return html.P("Pick a ZIP code first.", className="hint")
        f = dict(boroughs=boroughs, years=years, group=group, category=category, factor=factor, outcome=outcome,
                 zip=zip_code if mode == "search" else None)
    z, c, h, b = filter_data(f)
    if z.empty and c.empty:
        return [understood, html.P("No data for these filters.", className="hint")]

    crashes_total = int(z["crash_count"].sum())
    units = int(z["total_units"].sum())
    kpis = html.Div(className="kpis", children=[
        kpi("ZIP codes", f"{z['zip_code'].nunique():,}"),
        kpi("Crashes (with ZIP)", f"{crashes_total:,}"),
        kpi("Persons injured", f"{int(z['persons_injured'].sum()):,}"),
        kpi("Persons killed", f"{int(z['persons_killed'].sum()):,}"),
        kpi("Housing units completed", f"{units:,}", "buildings with ZIP + year"),
        kpi("Crashes per 100 units", f"{crashes_total / units * 100:,.0f}" if units else "n/a",
            "undefined when no units"),
    ])
    rq1 = charts_member1.fig_rq1(z)
    rq2 = charts_member1.fig_rq2(h.assign(zip_code=h["zip_code"].fillna("?")), c)
    graphs = [
        titled(rq1, "RQ1: Affordable units completed vs. crashes (ZIP-year)"),
        titled(rq2, "RQ2: Housing buildings over crash density"),
        fig_group_trend(z), fig_borough(b), fig_hour_weekday(c), fig_factors(c),
        fig_units_vs_crashes(z), fig_road_users(z), fig_top_zips(z), fig_income(z),
    ]
    return [understood, kpis, html.Div(className="grid", children=[dcc.Graph(figure=g) for g in graphs])]

dash_app = app          # keep the Dash object for local runs


def _restore_path(environ, start_response):
    """Vercel rewrites every URL to /api/index?__path=<original path>; put the original path back
    so Dash can serve its own routes (/_dash-layout, /_dash-component-suites/..., /assets/...)."""
    from urllib.parse import parse_qsl, urlencode
    qs = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    orig = [v for k, v in qs if k == "__path"]
    if orig:
        environ["PATH_INFO"] = "/" + orig[0].lstrip("/")
        environ["QUERY_STRING"] = urlencode([(k, v) for k, v in qs if k != "__path"])
    return server(environ, start_response)


app = _restore_path     # hosts (Vercel) look for a WSGI callable named `app` (gunicorn: app:server)

if __name__ == "__main__":
    dash_app.run(debug=False, port=int(os.environ.get("PORT", 8050)))
