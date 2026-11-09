"""Shared design tokens + Plotly template so every chart reads as one system.

Brand:  primary = civic blue, secondary = black/white, action = taxi yellow.
Chart colors were checked with a colorblind-safety validator (adjacent CVD dE >= 8 on white).
"""
import plotly.graph_objects as go
import plotly.io as pio

FONT = "Public Sans, system-ui, -apple-system, 'Segoe UI', sans-serif"

# ---- brand tokens (mirrored in assets/style.css :root)
PRIMARY = "#1B47B8"
INK = "#0A0D12"        # secondary: black
INK_2 = "#3D4654"
MUTED = "#6B7484"
GRID = "#EDF0F4"
AXIS = "#D5DAE1"
SURFACE = "#FFFFFF"
ACTION = "#FFC20E"     # taxi yellow, used for the main call to action only

# ---- chart palettes
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4"]        # categorical, fixed order
BOROUGH_COLORS = {"Bronx": "#2a78d6", "Brooklyn": "#eb6834", "Manhattan": "#1baf7a",
                  "Queens": "#6250d6", "Staten Island": "#e87ba4"}          # color follows the borough everywhere
GROUP_COLORS = {"High": "#104281", "Medium": "#2a78d6", "Low": "#86b6ef", "None": "#B8BEC8"}  # ordinal blues
ROAD_USER_COLORS = {"Pedestrians": "#eb6834", "Cyclists": "#1baf7a", "Motorists": "#2a78d6"}
INCOME_COLORS = {"Extremely low": "#0d366b", "Very low": "#184f95", "Low": "#256abf",
                 "Moderate": "#3987e5", "Middle": "#86b6ef", "Other": "#B8BEC8"}
TYPE_COLORS = {"New construction": "#2a78d6", "Preservation": "#eb6834"}
SEQ_BLUE = [[0, "#F3F7FD"], [0.15, "#cde2fb"], [0.3, "#9ec5f4"], [0.45, "#6da7ec"],
            [0.6, "#3987e5"], [0.75, "#256abf"], [0.9, "#184f95"], [1, "#0d366b"]]
HEAT = [[0, "rgba(250,178,25,0)"], [0.25, "rgba(250,178,25,0.55)"], [0.55, "rgba(235,104,52,0.75)"],
        [1, "rgba(200,40,40,0.9)"]]

_axis = dict(gridcolor=GRID, linecolor=AXIS, zeroline=False, ticks="", automargin=True,
             tickfont=dict(color=MUTED, size=11.5), title=dict(font=dict(color=MUTED, size=12), standoff=10))

pio.templates["nyc"] = go.layout.Template(
    layout=dict(
        font=dict(family=FONT, size=12.5, color=INK_2),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, colorway=SERIES,
        margin=dict(l=8, r=12, t=10, b=8),
        xaxis=dict(_axis, showline=True), yaxis=dict(_axis, showline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    title=dict(text=""), font=dict(size=12, color=INK_2), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="white", bordercolor=AXIS, font=dict(family=FONT, size=12, color=INK)),
        barcornerradius=4, bargap=0.32,
        coloraxis=dict(colorbar=dict(outlinewidth=0, thickness=10, tickfont=dict(color=MUTED, size=11))),
    ),
    data=dict(bar=[go.Bar(marker=dict(line=dict(color=SURFACE, width=1.5)))]),
)
pio.templates.default = "nyc"
