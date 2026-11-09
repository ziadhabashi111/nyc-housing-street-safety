"""Member 1 charts (RQ1, RQ2). Each function takes already-filtered DataFrames and returns a Plotly figure."""
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from theme import BOROUGH_COLORS, INK, MUTED, HEAT, FONT

def _empty_figure(message):
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color=MUTED, family=FONT))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig

def fig_rq1(df_filtered):
    """RQ1: do ZIP-years with more completed affordable units also record more crashes?
    Input: filtered merged_zip_year DataFrame."""
    data = df_filtered[df_filtered["affordable_units"] > 0]
    if data.empty:
        return _empty_figure("No ZIP-years with completed affordable housing for these filters")
    data = data.assign(borough=data["borough"].str.title())

    fig = px.scatter(
        data, x="affordable_units", y="crash_count", color="borough", log_x=True,
        opacity=0.7, color_discrete_map=BOROUGH_COLORS,
        category_orders={"borough": list(BOROUGH_COLORS)},
        hover_data={"zip_code": True, "year": True, "total_units": True, "injuries_per_crash": True},
        labels={"affordable_units": "Affordable units completed in the ZIP that year (log scale)",
                "crash_count": "Crashes in the ZIP that year", "borough": "Borough",
                "zip_code": "ZIP", "year": "Year", "total_units": "Total units",
                "injuries_per_crash": "Injuries per crash"})
    fig.update_traces(marker=dict(size=8, line=dict(color="white", width=0.8)))
    fig.update_xaxes(tickvals=[1, 10, 100, 1000, 10000],
                     ticktext=["1", "10", "100", "1,000", "10,000"])
    fig.update_yaxes(tickformat=",")

    # Trend line fitted on log10(units) vs crashes (numpy only, no extra dependency)
    x = data["affordable_units"].to_numpy(dtype=float)
    y = data["crash_count"].to_numpy(dtype=float)
    if len(data) >= 3 and x.min() != x.max():
        slope, intercept = np.polyfit(np.log10(x), y, 1)
        xs = np.linspace(x.min(), x.max(), 100)
        fig.add_trace(go.Scatter(x=xs, y=slope * np.log10(xs) + intercept, mode="lines",
                                 name="Trend", hoverinfo="skip",
                                 line=dict(color=INK, dash="dash", width=2)))
    return fig

def fig_rq2(housing_points, crash_points, max_crash_points=40000):
    """RQ2: where do affordable housing buildings overlap with crash hotspots?
    housing_points needs: latitude, longitude, total_units, zip_code, completion_year
    crash_points needs: latitude, longitude"""
    housing = housing_points.dropna(subset=["latitude", "longitude"])
    crashes = crash_points.dropna(subset=["latitude", "longitude"])
    if housing.empty and crashes.empty:
        return _empty_figure("No locations to show for these filters")
    if len(crashes) > max_crash_points:
        crashes = crashes.sample(max_crash_points, random_state=42)

    fig = go.Figure()
    fig.add_trace(go.Densitymapbox(
        lat=crashes["latitude"], lon=crashes["longitude"], radius=4, opacity=0.75,
        colorscale=HEAT, showscale=False, name="Crash density", hoverinfo="skip"))
    fig.add_trace(go.Scattermapbox(
        lat=housing["latitude"], lon=housing["longitude"], mode="markers",
        marker=dict(size=np.clip(np.sqrt(housing["total_units"].fillna(1)), 4, 12),
                    color="#104281", opacity=0.6),
        text=("ZIP " + housing["zip_code"].astype(str) + "<br>" + housing["total_units"].astype(str)
              + " units, completed " + housing["completion_year"].astype(str)),
        hoverinfo="text", name="Affordable housing building"))
    center = dict(lat=40.71, lon=-73.95)
    zoom = 9.4
    if 0 < len(housing) and housing["zip_code"].nunique() == 1:   # one ZIP: zoom in on it
        center = dict(lat=float(housing["latitude"].median()), lon=float(housing["longitude"].median()))
        zoom = 13
    fig.update_layout(
        # Esri light-gray raster tiles: free, no API key, quiet enough for the data to stand out
        mapbox=dict(style="white-bg", center=center, zoom=zoom, pitch=38, bearing=-12,   # tilted 3D view
                    layers=[dict(below="traces", sourcetype="raster", sourceattribution="Esri, HERE, Garmin, OpenStreetMap",
                                 source=["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
                                         "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"])]),
        margin=dict(l=0, r=0, t=0, b=0), showlegend=True,
        legend=dict(x=0.01, y=0.99, yanchor="top", orientation="v", bgcolor="rgba(255,255,255,0.9)"))
    return fig
