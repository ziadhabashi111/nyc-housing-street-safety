"""Milestone 1 dashboard: affordable housing vs. street safety in NYC (ZIP x year).

Run locally:  python app.py          Deploy: gunicorn app:server (or Vercel)
Design tokens (colors, fonts, chart template) live in theme.py and assets/style.css.
"""
import os
import re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output, State, ALL, ctx, no_update, clientside_callback

import theme  # registers the shared Plotly template (must load before any figure is built)
from theme import (PRIMARY, INK, INK_2, MUTED, SERIES, BOROUGH_COLORS, GROUP_COLORS, ROAD_USER_COLORS,
                   INCOME_COLORS, TYPE_COLORS, SEQ_BLUE)
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
def empty(msg):
    return charts_member1._empty_figure(msg)

def title_boroughs(df, col="borough"):
    return df.assign(**{col: df[col].str.title()})

def fig_group_trend(z):
    """RQ3: crashes per ZIP by housing group, over time (direct-labelled lines)."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = (z.groupby(["year", "housing_group"]).agg(crashes=("crash_count", "sum"), zips=("zip_code", "nunique"))
           .reset_index())
    t["crashes_per_zip"] = t["crashes"] / t["zips"]
    fig = px.line(t, x="year", y="crashes_per_zip", color="housing_group", markers=True,
                  color_discrete_map=GROUP_COLORS, category_orders={"housing_group": GROUPS},
                  labels={"crashes_per_zip": "Crashes per ZIP code", "year": "", "housing_group": "Housing group"})
    fig.update_traces(line=dict(width=2.2), marker=dict(size=8, line=dict(color="white", width=1.5)),
                      hovertemplate="%{x}: %{y:,.0f} crashes per ZIP<extra>%{fullData.name}</extra>")
    last = t[t["year"] == t["year"].max()].sort_values("crashes_per_zip")
    gap = max(t["crashes_per_zip"].max() * 0.07, 1)               # keep end labels from overlapping
    prev = None
    for _, r in last.iterrows():                                  # label each line at its end
        y = r["crashes_per_zip"] if prev is None else max(r["crashes_per_zip"], prev + gap)
        prev = y
        fig.add_annotation(x=r["year"], y=y, text=r["housing_group"], showarrow=False,
                           xanchor="left", xshift=10, font=dict(size=11.5, color=INK_2))
    y0, y1 = int(t["year"].min()), int(t["year"].max())
    fig.update_xaxes(dtick=1, tickformat="d", range=[y0 - 0.3, y1 + 0.3])
    fig.update_yaxes(tickformat=",", rangemode="tozero")
    fig.update_layout(margin=dict(r=64), showlegend=True)
    return fig

def fig_borough(b):
    """RQ4: crashes per 100 completed units, by borough."""
    if b.empty:
        return empty("No data for these filters")
    t = b.groupby("borough").agg(crashes=("crash_count", "sum"), units=("total_units", "sum")).reset_index()
    t["crashes_per_100_units"] = (t["crashes"] / t["units"] * 100).where(t["units"] > 0)
    t = title_boroughs(t)
    fig = px.bar(t, x="borough", y="crashes_per_100_units", color="borough", color_discrete_map=BOROUGH_COLORS,
                 category_orders={"borough": list(BOROUGH_COLORS)}, custom_data=["crashes", "units"],
                 labels={"crashes_per_100_units": "Crashes per 100 units", "borough": ""})
    fig.update_traces(texttemplate="%{y:,.0f}", textposition="outside", cliponaxis=False,
                      textfont=dict(color=INK_2, size=12),
                      hovertemplate="<b>%{x}</b><br>%{y:,.0f} crashes per 100 units<br>"
                                    "%{customdata[0]:,} crashes, %{customdata[1]:,} units<extra></extra>")
    fig.update_layout(showlegend=False)
    fig.update_yaxes(tickformat=",")
    return fig

HOUR_TICKS = dict(tickvals=[0, 3, 6, 9, 12, 15, 18, 21],
                  ticktext=["12 am", "3 am", "6 am", "9 am", "12 pm", "3 pm", "6 pm", "9 pm"])

def fig_hour_weekday(c):
    """RQ5: crashes by hour x weekday (sample)."""
    if c.empty:
        return empty("No crashes for these filters")
    grid = (c.dropna(subset=["crash_hour"]).groupby(["crash_weekday", "crash_hour"]).size()
              .unstack(fill_value=0).reindex(WEEKDAYS).fillna(0))
    fig = go.Figure(go.Heatmap(z=grid.values, x=grid.columns, y=[d[:3] for d in grid.index],
                               colorscale=SEQ_BLUE, xgap=2, ygap=2,
                               colorbar=dict(title=dict(text="Crashes", font=dict(size=11, color=MUTED)),
                                             thickness=10, outlinewidth=0),
                               hovertemplate="%{y}, %{x}:00<br>%{z:,} crashes<extra></extra>"))
    fig.update_xaxes(showline=False, showgrid=False, **HOUR_TICKS)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig

def fig_factors(c):
    """RQ6: top stated contributing factors (sample)."""
    if c.empty:
        return empty("No crashes for these filters")
    top = (c[~c["top_contributing_factor"].isin(["Unspecified", "Does Not Apply"])]["top_contributing_factor"]
             .value_counts().head(10).sort_values())
    if top.empty:
        return empty("No stated contributing factor for these filters")
    fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation="h", marker_color=SERIES[0],
                           hovertemplate="%{y}<br>%{x:,} crashes<extra></extra>"))
    fig.update_xaxes(title_text="Crashes in sample", tickformat=",")
    fig.update_yaxes(showgrid=False)
    fig.update_layout(bargap=0.38)
    return fig

def fig_units_vs_crashes(z):
    """RQ7: yearly completed units (stacked by type) above yearly crashes. Two panels, one shared x-axis."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby("year")[["new_construction_units", "preservation_units", "crash_count"]].sum().reset_index()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.58, 0.42], vertical_spacing=0.14,
                        subplot_titles=("Housing units completed", "Crashes recorded"))
    for col, name in [("new_construction_units", "New construction"), ("preservation_units", "Preservation")]:
        fig.add_bar(x=t["year"], y=t[col], name=name, marker_color=TYPE_COLORS[name], row=1, col=1,
                    hovertemplate="%{x}: %{y:,} units<extra>" + name + "</extra>")
    fig.add_scatter(x=t["year"], y=t["crash_count"], name="Crashes", mode="lines+markers", showlegend=False,
                    line=dict(color=INK, width=2.2), marker=dict(size=8, color=INK, line=dict(color="white", width=1.5)),
                    hovertemplate="%{x}: %{y:,} crashes<extra></extra>", row=2, col=1)
    fig.update_layout(barmode="stack", legend=dict(y=1.1, traceorder="normal"))
    fig.update_yaxes(tickformat=",", rangemode="tozero")
    fig.update_xaxes(dtick=1, tickformat="d")
    for a in fig.layout.annotations:                      # subplot titles: small, left-aligned
        a.update(x=0, xanchor="left", font=dict(size=12, color=MUTED))
    return fig

def fig_road_users(z):
    """RQ8: share of injured pedestrians / cyclists / motorists by housing group."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby("housing_group")[["ped_injured", "cyc_injured", "motorist_injured"]].sum()
    t = t.div(t.sum(axis=1), axis=0).mul(100).reindex([g for g in GROUPS if g in t.index]).reset_index()
    t = t.melt(id_vars="housing_group", var_name="road_user", value_name="share")
    t["road_user"] = t["road_user"].map({"ped_injured": "Pedestrians", "cyc_injured": "Cyclists",
                                         "motorist_injured": "Motorists"})
    fig = px.bar(t, x="housing_group", y="share", color="road_user", color_discrete_map=ROAD_USER_COLORS,
                 category_orders={"road_user": list(ROAD_USER_COLORS)},
                 labels={"share": "% of injured people", "housing_group": "Housing group", "road_user": ""})
    fig.update_traces(hovertemplate="%{x} housing group<br>%{y:.1f}% of injured<extra>%{fullData.name}</extra>")
    fig.update_yaxes(ticksuffix="%", range=[0, 100])
    return fig

def fig_top_zips(z):
    """RQ9: ZIP codes with the most crashes per 100 housing units completed."""
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby(["zip_code", "borough"]).agg(crashes=("crash_count", "sum"), units=("total_units", "sum")).reset_index()
    t = t[t["units"] >= 100]
    if t.empty:
        return empty("No ZIP codes with at least 100 completed units for these filters")
    t["crashes_per_100_units"] = t["crashes"] / t["units"] * 100
    t = title_boroughs(t.nlargest(12, "crashes_per_100_units").sort_values("crashes_per_100_units"))
    fig = px.bar(t, x="crashes_per_100_units", y="zip_code", color="borough", orientation="h",
                 color_discrete_map=BOROUGH_COLORS, category_orders={"borough": list(BOROUGH_COLORS)},
                 custom_data=["crashes", "units"],
                 labels={"crashes_per_100_units": "Crashes per 100 units completed", "zip_code": "",
                         "borough": ""})
    fig.update_traces(hovertemplate="<b>ZIP %{y}</b><br>%{x:,.0f} crashes per 100 units<br>"
                                    "%{customdata[0]:,} crashes, %{customdata[1]:,} units<extra>%{fullData.name}</extra>")
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=t["zip_code"].tolist(), showgrid=False)
    fig.update_xaxes(tickformat=",")
    fig.update_layout(bargap=0.3)
    return fig

def fig_income(z):
    """RQ10: which income levels the completed affordable units serve, by borough."""
    cols = {"extremely_low_income_units": "Extremely low", "very_low_income_units": "Very low",
            "low_income_units": "Low", "moderate_income_units": "Moderate",
            "middle_income_units": "Middle", "other_income_units": "Other"}
    if z.empty:
        return empty("No ZIP-years for these filters")
    t = z.groupby("borough")[list(cols)].sum().rename(columns=cols).reset_index().melt(
        id_vars="borough", var_name="income_tier", value_name="units")
    t = title_boroughs(t)
    fig = px.bar(t, x="borough", y="units", color="income_tier", color_discrete_map=INCOME_COLORS,
                 category_orders={"income_tier": list(INCOME_COLORS), "borough": list(BOROUGH_COLORS)},
                 labels={"units": "Affordable units completed", "borough": "", "income_tier": ""})
    fig.update_traces(hovertemplate="%{x}<br>%{y:,} units<extra>%{fullData.name} income</extra>")
    fig.update_yaxes(tickformat=",")
    fig.update_layout(bargap=0.45)
    return fig

# ---------------------------------------------------------------- page building blocks
GRAPH_CONFIG = {"displaylogo": False, "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
                "toImageButtonOptions": {"format": "png", "scale": 2}}

def chart_card(rq, title, caption, fig, wide=False, height=360):
    return html.Section(className="chart-card" + (" wide" if wide else ""), children=[
        html.Div(className="chart-head", children=[
            html.H3(title, className="chart-title"),
            html.Span(rq, className="rq-tag", title="Research question"),
        ]),
        html.P(caption, className="chart-caption"),
        dcc.Graph(figure=fig, config=GRAPH_CONFIG, className="chart", style={"height": f"{height}px"}),
    ])

def kpi(label, value):
    return html.Div(className="kpi", children=[html.Div(value, className="kpi-value"),
                                               html.Div(label, className="kpi-label")])

def notice(text, kind="info"):
    return html.Div(text, className=f"notice notice-{kind}", role="status")

def field(label, control, box_id, hint=None):
    return html.Div(id=box_id, className="field", children=[
        html.Div(label, className="field-label"), control,
        html.P(hint, className="field-hint") if hint else None])

TABS = [{"label": "Housing & crashes", "value": "housing"},
        {"label": "Map", "value": "map"},
        {"label": "When & why", "value": "when"},
        {"label": "People & places", "value": "people"}]

EXAMPLES = ["Brooklyn 2022 new buildings", "fatal crashes in Queens since 2021",
            "high housing speed", "11234", "Bronx preservation 2019 to 2023"]

def default_filters():
    return dict(boroughs=BOROUGHS, years=list(YEARS), group="All", zip=None, category="All",
                factor="All", outcome="Any crash")

def empty_state():
    return html.Div(className="empty-state", children=[
        html.H3("Your report will appear here"),
        html.Ol([html.Li("Pick a mode: Explore, ZIP search, or Free text."),
                 html.Li("Choose filters, or leave them as they are to see all of NYC."),
                 html.Li(["Press ", html.Strong("Generate Report"), "."])]),
    ])

FINDINGS = [
    ("RQ1, RQ3", "More housing, slightly more crashes",
     "ZIP codes in the High housing group average more crashes per year than Medium and Low ones. ZIP-years "
     "with more affordable units also tend to have somewhat more crashes, but the pattern is weak.", "housing"),
    ("RQ4", "Staten Island and Queens stand out",
     "They record the most crashes per 100 completed housing units. The Bronx records the fewest.", "housing"),
    ("RQ5, RQ6, RQ7", "Crashes fell after 2019 and peak in the afternoon",
     "Recorded crashes dropped after 2019. They peak between 2 pm and 6 pm, Friday is the busiest day, and "
     "driver distraction is the most common stated factor.", "when"),
]

LIMITS = [
    ("Association, not cause",
     "Housing and crashes are matched by ZIP code and year, not building to crash. Dense, busy areas can have "
     "both more housing and more crashes."),
    ("What the housing groups mean",
     "ZIP codes are split into thirds (High, Medium, Low) by units completed 2018 to 2025. None means no "
     "completed housing in that period."),
    ("Missing locations",
     "37.6% of buildings have no ZIP or completion year and 7.4% of crashes have no ZIP. Staten Island and "
     "Queens are the least reliable at ZIP level."),
    ("Sampled charts",
     "The map, the timing heatmap and the factors chart use a 200k-crash sample. All other charts use every "
     "crash. The crash factor and outcome filters only affect those three."),
]

TEAM = [("Ziad M", "Dataset selection and feasibility check, full crash download and ZIP recovery, "
                   "post-integration cleaning, RQ1 and RQ2"),
        ("Ahmed", "Housing dataset EDA and pre-integration cleaning, RQ3 and RQ4"),
        ("Yahia", "Crash dataset EDA and pre-integration cleaning, RQ5 and RQ6, website UI/UX redesign"),
        ("Habashi", "Dash app (dropdowns, search mode, Generate Report), Vercel deployment, RQ7 and RQ8"),
        ("Abdelrahman", "GitHub repo, notebook assembly, story section, README, final testing, RQ9 and RQ10")]

TOTAL_CRASHES = int(zip_year["crash_count"].sum())
TOTAL_UNITS = int(zip_year["total_units"].sum())

# ---------------------------------------------------------------- layout
app = Dash(__name__, title="NYC Housing & Street Safety",
           external_stylesheets=["https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800&display=swap"],
           meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"},
                      {"name": "description", "content": "Affordable housing completed vs. traffic crashes in NYC, "
                                                         "by ZIP code, 2018-2025."}])
server = app.server

topbar = html.Header(className="topbar", children=[
    html.Div(className="topbar-inner", children=[
        html.A(href="#top", className="brand", children=[
            html.Img(src=app.get_asset_url("logo.svg"), alt="", className="brand-mark"),
            html.Span("NYC Housing & Street Safety", className="brand-name"),
        ]),
        html.Nav(className="nav", children=[html.A("Explore", href="#explore"), html.A("The story", href="#findings"),
                                            html.A("About the data", href="#about")]),
    ]),
])

hero = html.Section(id="top", className="hero", children=[
    html.Div(className="hero-floor", **{"aria-hidden": "true"}),
    html.Div(className="hero-inner", children=[
        html.Div(className="hero-copy", children=[
            html.H1("Where New York built affordable housing, were the streets less safe?"),
            html.P(f"We matched {TOTAL_UNITS:,} affordable housing units completed between 2018 and 2025 with "
                   f"{TOTAL_CRASHES:,} police-reported crashes, ZIP code by ZIP code. Filter the data, search a "
                   "neighborhood, then press Generate Report.", className="lead"),
            html.Div(className="hero-actions", children=[
                html.A("Explore the data", href="#explore", className="btn btn-action"),
                html.A("Read the story", href="#findings", className="btn btn-ghost"),
            ]),
        ]),
        html.Aside(className="answer", **{"data-tilt": ""}, children=[
            html.H2("The short answer"),
            html.P("ZIP codes that got more affordable housing see somewhat more crashes, but the link is weak and "
                   "reflects busy, dense areas rather than the housing itself."),
            html.Dl(className="facts", children=[
                html.Div([html.Dt("Crashes with a ZIP"), html.Dd(f"{TOTAL_CRASHES:,}")]),
                html.Div([html.Dt("Units completed"), html.Dd(f"{TOTAL_UNITS:,}")]),
                html.Div([html.Dt("ZIP codes"), html.Dd(f"{len(ZIPS)}")]),
                html.Div([html.Dt("Years covered"), html.Dd(f"{YEARS[0]} to {YEARS[1]}")]),
            ]),
        ]),
    ]),
])

sidebar = html.Aside(className="sidebar", **{"aria-label": "Report filters"}, children=[
    html.Div(className="sidebar-body", children=[
        html.H2("Build your report", className="sidebar-title"),
        html.Div("Mode", className="field-label"),
        dcc.RadioItems(id="mode", value="explore", className="segmented", labelClassName="seg",
                       inputClassName="pill-input",
                       options=[{"label": "Explore", "value": "explore"},
                                {"label": "ZIP search", "value": "search"},
                                {"label": "Free text", "value": "text"}]),
        html.Div(id="box-query", className="field", style={"display": "none"}, children=[
            html.Div("Search", className="field-label"),
            dcc.Input(id="query", type="text", debounce=False, className="text-input",
                      placeholder="e.g. Brooklyn 2022 new buildings"),
            html.P("Mention a borough, year or range, ZIP code, 'new buildings' or 'preservation', "
                   "'high housing', a crash factor like 'speed', or 'fatal'. Then press Generate Report.",
                   className="field-hint"),
            html.Div("Examples (click to fill the search)", className="field-label examples-label"),
            html.Div(className="examples", children=[
                html.Button(e, id={"type": "example", "index": i}, className="example-chip", n_clicks=0)
                for i, e in enumerate(EXAMPLES)]),
        ]),
        field("ZIP code", dcc.Dropdown(id="zip", options=ZIPS, value=None, placeholder="Type a ZIP code...",
                                       className="dropdown"), "box-zip"),
        field("Borough", dcc.Dropdown(id="boroughs", options=[{"label": b.title(), "value": b} for b in BOROUGHS],
                                      value=BOROUGHS, multi=True, className="dropdown dropdown-multi",
                                      placeholder="All boroughs"), "box-boroughs"),
        field("Housing group (ZIP level)", dcc.Dropdown(id="group", clearable=False, value="All",
                                                        options=["All"] + GROUPS, className="dropdown"),
              "box-group", "ZIP codes split into thirds by units completed 2018 to 2025."),
        field("Housing category", dcc.Dropdown(id="category", clearable=False, value="All",
                                               options=["All"] + CATEGORIES, className="dropdown"),
              "box-category"),
        html.Div(id="box-years", className="field", children=[
            html.Div(className="field-label field-label-row", children=[
                html.Span("Years"), html.Span(id="years-label", className="years-label")]),
            dcc.RangeSlider(id="years", min=YEARS[0], max=YEARS[1], step=1, value=list(YEARS), allowCross=False,
                            marks={y: f"'{str(y)[2:]}" for y in range(YEARS[0], YEARS[1] + 1)},
                            className="range"),
        ]),
        html.Div(className="sub-group", children=[
            html.P("Crash filters apply to the map and the When & why charts (200k-crash sample).",
                   className="sub-group-note"),
            field("Crash factor (transport category)", dcc.Dropdown(id="factor", clearable=False, value="All",
                                                                    options=["All"] + FACTORS,
                                                                    className="dropdown"), "box-factor"),
            field("Crash outcome", dcc.Dropdown(id="outcome", clearable=False, value="Any crash", options=OUTCOMES,
                                                className="dropdown"), "box-outcome"),
        ]),
    ]),
    html.Div(className="sidebar-foot", children=[
        html.P(id="dirty-note", className="dirty-note", **{"aria-live": "polite"}),
        html.Div(className="sidebar-buttons", children=[
            html.Button("Reset", id="reset", n_clicks=0, className="btn btn-ghost btn-sm"),
            html.Button("Generate Report", id="go", n_clicks=0, className="btn btn-action btn-grow"),
        ]),
    ]),
])

main = html.Div(className="report", id="report", children=[
    html.Div(id="summary", className="summary"),
    dcc.Loading(type="dot", color=PRIMARY, parent_className="loading-wrap", children=[
        html.Div(id="kpis", className="kpis"),
        dcc.RadioItems(id="tab", value="housing", options=TABS, className="tabbar", labelClassName="tab",
                       inputClassName="pill-input"),
        html.Div(id="section", className="chart-grid"),
    ]),
])

findings = html.Section(id="findings", className="band", children=[
    html.Div(className="band-inner", children=[
        html.H2("The story", className="band-title"),
        html.H3("Question", className="story-sub"),
        html.P("Do the ZIP codes where affordable housing was completed between 2018 and 2025 also record more "
               "traffic crashes? The answer shows where street-safety work should go alongside new housing.",
               className="story-question"),
        html.H3("What we found", className="story-sub"),
        html.Div(className="findings", children=[
            html.Article(className="finding", children=[
                html.Span(rqs, className="rq-tag"),
                html.H3(title), html.P(text),
                html.Button("See the charts", id={"type": "finding", "index": i}, n_clicks=0,
                            className="link-btn"),
            ]) for i, (rqs, title, text, _tab) in enumerate(FINDINGS)]),
        html.H3("Limits", className="story-sub"),
        html.Div(className="limits", children=[
            html.Details(className="limit", children=[html.Summary(t), html.P(d)]) for t, d in LIMITS]),
        html.H3("How this helps NYC", className="story-sub"),
        html.P("Agencies can use the ZIP ranking (RQ9) to prioritize street-safety work near new housing and the "
               "timing heatmap (RQ5) to schedule enforcement.", className="helps"),
    ]),
])

about = html.Section(id="about", className="band band-white", children=[
    html.Div(className="band-inner about", children=[
        html.Div(children=[
            html.H2("About the data", className="band-title"),
            html.Ul(className="sources", children=[
                html.Li([html.A("Affordable Housing Production by Building",
                                href="https://data.cityofnewyork.us/Housing-Development/Affordable-Housing-Production-by-Building/hg8x-zxpr",
                                target="_blank", rel="noopener"),
                         html.Span("NYC Open Data, 9,551 buildings")]),
                html.Li([html.A("Motor Vehicle Collisions: Crashes",
                                href="https://data.cityofnewyork.us/Public-Safety/Motor-Vehicle-Collisions-Crashes/h9gi-nx95",
                                target="_blank", rel="noopener"),
                         html.Span("NYC Open Data, 1,043,903 crashes 2018 to 2025")]),
            ]),
            html.P("The two datasets share no record-level key, so both are counted per ZIP code and year and then "
                   "joined. 266,590 crashes without a ZIP got one recovered from their coordinates (nearest ZIP "
                   "within 200 m). Every one of the 242,248 units and 966,552 crashes with a ZIP is kept.",
                   className="about-text"),
        ]),
        html.Div(children=[
            html.H2("Team", className="band-title"),
            html.Table(className="team", children=[html.Tbody([
                html.Tr([html.Th(n, scope="row"), html.Td(r)]) for n, r in TEAM])]),
        ]),
    ]),
])

app.layout = html.Div(className="app", children=[
    dcc.Store(id="applied", data=None),
    topbar, hero,
    html.Section(id="explore", className="workspace", children=[sidebar, main]),
    findings, about,
    html.Footer(className="footer", children=[
        html.Div(className="footer-inner", children=[
            html.Span("Data Engineering and Visualization, GIU. Milestone 1."),
            html.Span("Data: NYC Open Data."),
        ])]),
])

# ---------------------------------------------------------------- callbacks
CONTROLS = ["boroughs", "group", "zip", "category", "factor", "outcome", "years"]

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

@app.callback(Output("years-label", "children"), Input("years", "value"))
def years_label(years):
    y0, y1 = years
    return str(y0) if y0 == y1 else f"{y0} to {y1}"

@app.callback([Output(c, "value") for c in CONTROLS] + [Output("query", "value")],
              Input("reset", "n_clicks"), prevent_initial_call=True)
def reset_controls(_):
    d = default_filters()
    return [d[c] for c in CONTROLS] + [""]

@app.callback(Output("query", "value", allow_duplicate=True),
              Input({"type": "example", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def fill_example(clicks):
    if not any(clicks or []):
        return no_update
    return EXAMPLES[ctx.triggered_id["index"]]

def controls_to_filters(mode, boroughs, group, zip_code, category, factor, outcome, years):
    return dict(boroughs=boroughs or [], years=[int(y) for y in years], group=group,
                zip=zip_code if mode == "search" else None, category=category, factor=factor, outcome=outcome)

def applied_from_text(query):
    q = (query or "").strip()
    if not q:
        return dict(mode="text", query=q, error="Type a search first, for example: Brooklyn 2022 new buildings.")
    f, seen = parse_query(q)
    if not seen:
        return dict(mode="text", query=q,
                    error="Nothing recognized in that search. Try a borough, a year or range, 'new buildings' or "
                          "'preservation', a ZIP code, 'high housing', or a crash factor like 'speed'.")
    return dict(mode="text", query=q, f=f, seen=seen, error=None)

@app.callback(Output("applied", "data"), Input("go", "n_clicks"),
              State("mode", "value"), [State(c, "value") for c in CONTROLS], State("query", "value"),
              prevent_initial_call=True)
def generate_report(_n, mode, boroughs, group, zip_code, category, factor, outcome, years, query):
    """Generate Report is the only trigger: it snapshots the current filters (or the parsed search)."""
    if mode == "text":
        return applied_from_text(query)
    if mode == "search" and not zip_code:
        return dict(mode="search", error="Pick a ZIP code first.")
    f = controls_to_filters(mode, boroughs, group, zip_code, category, factor, outcome, years)
    return dict(mode=mode, f=f, query="", seen=[], error=None)

@app.callback(Output("go", "className"), Output("dirty-note", "children"),
              Input("mode", "value"), [Input(c, "value") for c in CONTROLS], Input("query", "value"),
              Input("applied", "data"))
def mark_dirty(mode, boroughs, group, zip_code, category, factor, outcome, years, query, applied):
    base = "btn btn-action btn-grow"
    if not applied:                                   # nothing generated yet
        return base, ""
    if applied.get("error"):
        dirty = True
    elif mode == "text":
        dirty = (query or "").strip() != (applied.get("query") or "") or applied.get("mode") != "text"
    else:
        cur = controls_to_filters(mode, boroughs, group, zip_code, category, factor, outcome, years)
        af = applied.get("f") or {}
        norm = lambda f: (sorted(f.get("boroughs") or []), list(f.get("years") or []), f.get("group"),
                          f.get("zip"), f.get("category"), f.get("factor"), f.get("outcome"))
        dirty = norm(cur) != norm(af) or (applied.get("mode") == "text")
    if dirty:
        return base + " is-dirty", "Press Generate Report to apply your changes."
    return base, ""

def summary_chips(f):
    chips = []
    if f.get("zip"):
        chips.append(f"ZIP {f['zip']}")
    else:
        bs = f.get("boroughs") or []
        chips.append("All boroughs" if not bs or set(bs) == set(BOROUGHS) else ", ".join(b.title() for b in bs))
    y0, y1 = f["years"]
    chips.append(str(y0) if y0 == y1 else f"{y0} to {y1}")
    if f.get("group", "All") != "All" and not f.get("zip"):
        chips.append(f"{f['group']} housing group")
    if f.get("category", "All") != "All":
        chips.append(f["category"])
    if f.get("factor", "All") != "All":
        chips.append(f["factor"])
    if f.get("outcome", "Any crash") != "Any crash":
        chips.append(f["outcome"])
    return chips

@app.callback(Output("summary", "children"), Output("kpis", "children"), Output("section", "children"),
              Output("tab", "style"), Input("applied", "data"), Input("tab", "value"))
def render(applied, tab):
    hide_tabs = {"display": "none"}
    if not applied:
        return None, None, [empty_state()], hide_tabs
    if applied.get("error"):
        return None, None, [notice(applied["error"], "warn")], hide_tabs
    f = applied["f"]
    z, c, h, b = filter_data(f)
    lead = "Understood as" if applied.get("mode") == "text" else "Showing"
    summary = [html.Span(lead, className="summary-lead")] + [html.Span(t, className="chip") for t in summary_chips(f)]
    if z.empty and c.empty:
        return summary, None, [notice("No data matches these filters. Try a wider year range or remove a filter.",
                                      "warn")], hide_tabs

    crashes_total = int(z["crash_count"].sum())
    units = int(z["total_units"].sum())
    kpis = [
        kpi("ZIP codes", f"{z['zip_code'].nunique():,}"),
        kpi("Crashes", f"{crashes_total:,}"),
        kpi("People injured", f"{int(z['persons_injured'].sum()):,}"),
        kpi("People killed", f"{int(z['persons_killed'].sum()):,}"),
        kpi("Housing units completed", f"{units:,}"),
        kpi("Crashes per 100 units", f"{crashes_total / units * 100:,.0f}" if units else "n/a"),
    ]

    if tab == "map":
        rq2 = charts_member1.fig_rq2(h.assign(zip_code=h["zip_code"].fillna("?")), c)
        cards = [chart_card("RQ2", "Where housing sits relative to crash hotspots",
                            "Blue dots are affordable housing buildings; bigger dots have more units. Warmer areas "
                            "have more crashes. Right-drag to tilt or rotate. Crash layer uses a 200k sample.", rq2, wide=True, height=600)]
    elif tab == "when":
        cards = [
            chart_card("RQ5", "When crashes happen",
                       "Darker cells have more crashes. Hour of day across, day of week down. 200k-crash sample.",
                       fig_hour_weekday(c), wide=True, height=340),
            chart_card("RQ6", "Most common contributing factors",
                       "Factor reported for the first vehicle, excluding 'unspecified'. 200k-crash sample.",
                       fig_factors(c), height=400),
            chart_card("RQ7", "Housing built vs. crashes, year by year",
                       "Top: units completed by type. Bottom: crashes in the same ZIP codes.",
                       fig_units_vs_crashes(z), height=400),
        ]
    elif tab == "people":
        cards = [
            chart_card("RQ8", "Who gets hurt",
                       "Share of injured people who were pedestrians, cyclists or motorists, by housing group.",
                       fig_road_users(z)),
            chart_card("RQ9", "ZIP codes with the most crashes per 100 units",
                       "Top 12 ZIP codes with at least 100 units completed. Hover for totals.", fig_top_zips(z)),
            chart_card("RQ10", "Which incomes the new units serve",
                       "Affordable units completed per borough, by income tier from extremely low to middle.",
                       fig_income(z), wide=True, height=340),
        ]
    else:
        rq1 = charts_member1.fig_rq1(z)
        cards = [
            chart_card("RQ1", "More affordable units, more crashes?",
                       "Each dot is one ZIP code in one year. The dashed trend line is nearly flat: the link is weak.",
                       rq1, wide=True, height=420),
            chart_card("RQ3", "Crashes per ZIP code, by housing group",
                       "ZIP codes split into thirds by units completed 2018 to 2025. None means no completed housing.",
                       fig_group_trend(z)),
            chart_card("RQ4", "Crashes per 100 housing units, by borough",
                       "Higher means more crashes relative to the housing completed there.", fig_borough(b)),
        ]
    return summary, kpis, cards, {}

@app.callback(Output("tab", "value"), Input({"type": "finding", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def open_finding(clicks):
    if not any(clicks or []):
        return no_update
    return FINDINGS[ctx.triggered_id["index"]][3]

clientside_callback(
    """function(clicks) {
        if (clicks && clicks.some(Boolean)) {
            const el = document.getElementById('explore');
            if (el) el.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
        }
        return window.dash_clientside.no_update;
    }""",
    Output("findings", "className"), Input({"type": "finding", "index": ALL}, "n_clicks"), prevent_initial_call=True)

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
