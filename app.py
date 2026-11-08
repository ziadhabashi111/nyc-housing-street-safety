"""Milestone 1 dashboard: affordable housing vs. street safety in NYC (ZIP x year).

Run locally:  python app.py          Deploy (Render):  gunicorn app:server
"""
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, no_update

import charts_member1

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
GROUPS = ["High", "Medium", "Low", "None"]          # housing_group of a ZIP (2018-2025 completed units)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ---------------------------------------------------------------- data
READ = dict(keep_default_na=False, na_values=[""])   # keep the housing_group label "None" (pandas would read it as NaN)
zip_year = pd.read_csv(f"{DATA}/merged_zip_year.csv", dtype={"zip_code": str}, **READ)
borough_year = pd.read_csv(f"{DATA}/merged_borough_year.csv")
housing = pd.read_csv(f"{DATA}/housing_clean.csv", dtype={"zip_code": str}, **READ,
                      usecols=["borough", "zip_code", "latitude", "longitude", "completion_year",
                               "total_units", "affordable_units"])
# crashes_app.csv.gz = crashes_enriched.csv reduced to the columns used here (smaller, faster to load)
CRASH_FILE = "crashes_app.csv.gz" if os.path.exists(f"{DATA}/crashes_app.csv.gz") else "crashes_enriched.csv"
crashes = pd.read_csv(f"{DATA}/{CRASH_FILE}", dtype={"zip_code": str}, **READ,
                      usecols=["crash_year", "crash_hour", "crash_weekday", "borough", "zip_code",
                               "latitude", "longitude", "persons_injured", "persons_killed",
                               "top_contributing_factor", "housing_group"])
YEARS = (int(zip_year["year"].min()), int(zip_year["year"].max()))
ZIPS = sorted(zip_year["zip_code"].unique())

# ---------------------------------------------------------------- filtering
def filter_data(mode, boroughs, years, group, zip_code):
    y0, y1 = years
    z = zip_year[zip_year["year"].between(y0, y1)]
    c = crashes[crashes["crash_year"].between(y0, y1)]
    h = housing[housing["completion_year"].between(y0, y1)]
    b = borough_year[borough_year["year"].between(y0, y1)]
    if mode == "search" and zip_code:
        z, c, h = z[z["zip_code"] == zip_code], c[c["zip_code"] == zip_code], h[h["zip_code"] == zip_code]
        b = b[b["borough"].isin(z["borough"].dropna().unique())]
    else:
        if boroughs:
            z, c, h, b = (z[z["borough"].isin(boroughs)], c[c["borough"].isin(boroughs)],
                          h[h["borough"].isin(boroughs)], b[b["borough"].isin(boroughs)])
        if group and group != "All":
            z, c = z[z["housing_group"] == group], c[c["housing_group"] == group]
            h = h[h["zip_code"].isin(z["zip_code"].unique())]
    return z, c, h, b

# ---------------------------------------------------------------- figures
def kpi(label, value, note=""):
    return html.Div(className="kpi", children=[html.Div(label, className="kpi-label"),
                                               html.Div(value, className="kpi-value"),
                                               html.Div(note, className="kpi-note")])

def empty(msg):
    return charts_member1._empty_figure(msg)

def fig_hour_weekday(c):
    if c.empty:
        return empty("No crashes for these filters")
    grid = (c.dropna(subset=["crash_hour"]).groupby(["crash_weekday", "crash_hour"]).size()
              .unstack(fill_value=0).reindex(WEEKDAYS).fillna(0))
    fig = px.imshow(grid, aspect="auto", color_continuous_scale="YlOrRd", template="plotly_white",
                    labels=dict(x="Hour of day", y="", color="Crashes (sample)"),
                    title="When crashes happen (hour x weekday, 200k-crash sample)")
    return fig

def fig_factors(c):
    if c.empty:
        return empty("No crashes for these filters")
    top = (c[c["top_contributing_factor"] != "Unspecified"]["top_contributing_factor"]
             .value_counts().head(10).sort_values())
    fig = px.bar(x=top.values, y=top.index, orientation="h", template="plotly_white",
                 labels={"x": "Crashes (sample)", "y": ""},
                 title="Top contributing factors (vehicle 1, excluding Unspecified)")
    fig.update_layout(showlegend=False)
    return fig

def fig_group_trend(z):
    """Crashes per ZIP-year by housing group: exact totals, not the sample."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = (z.groupby(["year", "housing_group"]).agg(crashes=("crash_count", "sum"), zips=("zip_code", "nunique"))
           .reset_index())
    t["crashes_per_zip"] = t["crashes"] / t["zips"]
    fig = px.line(t, x="year", y="crashes_per_zip", color="housing_group", markers=True,
                  template="plotly_white",
                  category_orders={"housing_group": GROUPS},
                  labels={"crashes_per_zip": "Crashes per ZIP", "year": "Year", "housing_group": "Housing group"},
                  title="Crashes per ZIP by housing group (all crashes with a ZIP)")
    return fig

def fig_borough(b):
    if b.empty:
        return empty("No data for these filters")
    t = b.groupby("borough").agg(crashes=("crash_count", "sum"), units=("total_units", "sum")).reset_index()
    t["crashes_per_100_units"] = (t["crashes"] / t["units"] * 100).where(t["units"] > 0)
    fig = px.bar(t, x="borough", y="crashes_per_100_units", template="plotly_white",
                 hover_data=["crashes", "units"],
                 labels={"crashes_per_100_units": "Crashes per 100 housing units completed", "borough": ""},
                 title="Crashes per 100 housing units, by borough (all buildings with a year)")
    return fig

# ---------------------------------------------------------------- layout
app = Dash(__name__, title="NYC Housing & Street Safety")
server = app.server

app.layout = html.Div(className="page", children=[
    html.H1("Affordable housing and street safety in NYC"),
    html.P("Do the ZIP codes where affordable housing was completed (2018-2025) see more or fewer crashes? "
           "Pick filters, then press Generate Report.", className="sub"),
    html.Div(className="controls", children=[
        html.Div([html.Label("Mode"),
                  dcc.RadioItems(id="mode", value="explore", inline=True,
                                 options=[{"label": "Explore", "value": "explore"},
                                          {"label": "Search a ZIP code", "value": "search"}])]),
        html.Div([html.Label("Borough"),
                  dcc.Dropdown(id="boroughs", options=BOROUGHS, value=BOROUGHS, multi=True)], id="box-boroughs"),
        html.Div([html.Label("Housing group"),
                  dcc.Dropdown(id="group", clearable=False, value="All",
                               options=["All"] + GROUPS)], id="box-group"),
        html.Div([html.Label("ZIP code"),
                  dcc.Dropdown(id="zip", options=ZIPS, value=None, placeholder="Type a ZIP code...")],
                 id="box-zip", style={"display": "none"}),
        html.Div([html.Label("Years"),
                  dcc.RangeSlider(id="years", min=YEARS[0], max=YEARS[1], step=1, value=list(YEARS),
                                  marks={y: str(y) for y in range(YEARS[0], YEARS[1] + 1)})],
                 className="wide"),
        html.Button("Generate Report", id="go", n_clicks=0),
    ]),
    dcc.Loading(html.Div(id="report"), type="circle"),
    html.Div(className="notes", children=[
        html.H3("How to read this"),
        html.Ul([
            html.Li("Housing and crashes are compared by ZIP code and year (counts per ZIP), not building by crash."),
            html.Li("housing_group = tercile (High / Medium / Low) of a ZIP's units completed 2018-2025; "
                    "None = no completed housing in that window."),
            html.Li("3,542 of 9,427 buildings (37.6%) have no ZIP or no completion year and are missing from ZIP-level "
                    "views; Staten Island (71.5% missing ZIP) and Queens (41.8%) are the least reliable."),
            html.Li("7.4% of crashes still have no ZIP after recovery from coordinates; they only appear in the borough view."),
            html.Li("Crash-level charts use a 200k-crash sample stratified by year; ZIP totals use all crashes."),
            html.Li("Correlation only: more housing and more crashes can both come from dense, busy areas."),
        ])]),
])

@app.callback(Output("box-boroughs", "style"), Output("box-group", "style"), Output("box-zip", "style"),
              Input("mode", "value"))
def toggle_mode(mode):
    show, hide = {}, {"display": "none"}
    return (hide, hide, show) if mode == "search" else (show, show, hide)

@app.callback(Output("report", "children"), Input("go", "n_clicks"),
              State("mode", "value"), State("boroughs", "value"), State("years", "value"),
              State("group", "value"), State("zip", "value"))
def generate_report(n, mode, boroughs, years, group, zip_code):
    if not n:
        return html.P("Choose filters and press Generate Report.", className="hint")
    if mode == "search" and not zip_code:
        return html.P("Pick a ZIP code first.", className="hint")
    z, c, h, b = filter_data(mode, boroughs, years, group, zip_code)
    if z.empty and c.empty:
        return html.P("No data for these filters.", className="hint")

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
    graphs = [
        charts_member1.fig_rq1(z),
        charts_member1.fig_rq2(h.assign(zip_code=h["zip_code"].fillna("?"), completion_year=h["completion_year"]), c),
        fig_group_trend(z), fig_borough(b), fig_hour_weekday(c), fig_factors(c),
    ]
    return [kpis, html.Div(className="grid", children=[dcc.Graph(figure=f) for f in graphs])]

if __name__ == "__main__":
    app.run(debug=False, port=int(os.environ.get("PORT", 8050)))
