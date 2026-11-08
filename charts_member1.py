"""Member 1 charts (RQ1, RQ2). Each function takes already-filtered DataFrames and returns a Plotly figure."""
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

def _empty_figure(message):
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=16))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig

def fig_rq1(df_filtered):
    """RQ1: do ZIP-years with more completed affordable units also record more crashes?
    Input: filtered merged_zip_year DataFrame."""
    data = df_filtered[df_filtered["affordable_units"] > 0]
    if data.empty:
        return _empty_figure("No ZIP-years with completed affordable housing for these filters")

    fig = px.scatter(
        data, x="affordable_units", y="crash_count", color="borough", log_x=True,
        opacity=0.7, template="plotly_white",
        hover_data={"zip_code": True, "year": True, "total_units": True, "injuries_per_crash": True},
        labels={"affordable_units": "Affordable units completed in the ZIP that year (log scale)",
                "crash_count": "Crashes in the ZIP that year", "borough": "Borough"},
        title="Affordable housing completed vs. crashes, by ZIP code and year")
    fig.update_xaxes(tickvals=[1, 10, 100, 1000, 10000],
                     ticktext=["1", "10", "100", "1,000", "10,000"])

    # Trend line fitted on log10(units) vs crashes (numpy only, no extra dependency)
    x = data["affordable_units"].to_numpy(dtype=float)
    y = data["crash_count"].to_numpy(dtype=float)
    if len(data) >= 3 and x.min() != x.max():
        slope, intercept = np.polyfit(np.log10(x), y, 1)
        xs = np.linspace(x.min(), x.max(), 100)
        fig.add_trace(go.Scatter(x=xs, y=slope * np.log10(xs) + intercept, mode="lines",
                                 name="Trend (all ZIP-years)", line=dict(color="black", dash="dash")))
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
        lat=crashes["latitude"], lon=crashes["longitude"], radius=4,
        colorscale="YlOrRd", opacity=0.6, showscale=False, name="Crash density"))
    fig.add_trace(go.Scattermapbox(
        lat=housing["latitude"], lon=housing["longitude"], mode="markers",
        marker=dict(size=np.clip(np.sqrt(housing["total_units"].fillna(1)), 3, 12),
                    color="royalblue", opacity=0.65),
        text=("ZIP " + housing["zip_code"].astype(str) + " | " + housing["total_units"].astype(str)
              + " units | completed " + housing["completion_year"].astype(str)),
        hoverinfo="text", name="Affordable housing buildings"))
    fig.update_layout(
        title="Affordable housing buildings over crash density",
        # white-bg + free USGS tiles: no API key needed, works on the deployed site
        mapbox=dict(style="white-bg",
                    layers=[dict(below="traces", sourcetype="raster",
                                 source=["https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}"])],
                    center=dict(lat=40.71, lon=-73.97), zoom=9.3),
        margin=dict(l=0, r=0, t=40, b=0), legend=dict(x=0.01, y=0.99))
    return fig
