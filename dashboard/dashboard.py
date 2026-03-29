import requests
import pandas as pd
import dash
from dash import dcc, html, dash_table, Input, Output
import plotly.express as px

API_BASE = "http://127.0.0.1:8000/api/telemetry"
REPORT_BASE = "http://127.0.0.1:8000/api/reports"
ANALYTICS_BASE = "http://127.0.0.1:8000/api/analytics"

BG_COLOR = "#0b1220"
PANEL_COLOR = "#111827"
CARD_BORDER = "#1f2937"
TEXT_COLOR = "#e5e7eb"
MUTED_TEXT = "#9ca3af"
ACCENT_BLUE = "#2563eb"
ACCENT_RED = "#dc2626"
ACCENT_ORANGE = "#f59e0b"
ACCENT_PURPLE = "#8b5cf6"
ACCENT_GREEN = "#16a34a"
ACCENT_CYAN = "#0891b2"


def fetch_json(url: str, default: dict):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        return default
    except Exception:
        return default


def load_backend_data():
    stats = fetch_json(f"{API_BASE}/stats", {})
    recent = fetch_json(f"{API_BASE}/recent?limit=200", {"items": []})
    by_asset = fetch_json(f"{API_BASE}/by-asset", {"items": []})
    by_network = fetch_json(f"{API_BASE}/by-network", {"items": []})
    by_sensor = fetch_json(f"{API_BASE}/by-sensor", {"items": []})
    locations = fetch_json(f"{API_BASE}/latest-locations", {"items": []})
    incident_summary = fetch_json(f"{REPORT_BASE}/incident-summary", {})
    sales_summary = fetch_json(f"{ANALYTICS_BASE}/sales-summary", {})
    station_sales = fetch_json(f"{ANALYTICS_BASE}/station-sales/recent?limit=100", {"items": []})
    daily_sales = fetch_json(f"{ANALYTICS_BASE}/station-sales/daily", {"items": []})

    recent_df = pd.DataFrame(recent.get("items", []))
    asset_df = pd.DataFrame(by_asset.get("items", []))
    network_df = pd.DataFrame(by_network.get("items", []))
    sensor_df = pd.DataFrame(by_sensor.get("items", []))
    location_df = pd.DataFrame(locations.get("items", []))
    station_sales_df = pd.DataFrame(station_sales.get("items", []))
    daily_sales_df = pd.DataFrame(daily_sales.get("items", []))

    return (
        stats,
        recent_df,
        asset_df,
        network_df,
        sensor_df,
        location_df,
        incident_summary,
        sales_summary,
        station_sales_df,
        daily_sales_df,
    )


def apply_dark_layout(fig, height=500):
    fig.update_layout(
        paper_bgcolor=PANEL_COLOR,
        plot_bgcolor=PANEL_COLOR,
        font=dict(color=TEXT_COLOR),
        margin=dict(r=15, t=55, l=15, b=15),
        height=height,
    )
    return fig


def kpi_card(title, value, color, icon):
    return html.Div(
        [
            html.Div(
                [
                    html.Span(icon, style={"fontSize": "22px", "marginRight": "10px"}),
                    html.Span(title, style={"fontSize": "15px", "fontWeight": "600"}),
                ],
                style={"marginBottom": "12px", "display": "flex", "alignItems": "center"},
            ),
            html.Div(str(value), style={"fontSize": "28px", "fontWeight": "bold", "lineHeight": "1"}),
        ],
        style={
            "background": f"linear-gradient(135deg, {color}, {PANEL_COLOR})",
            "color": "white",
            "padding": "20px",
            "borderRadius": "16px",
            "minHeight": "120px",
            "border": f"1px solid {CARD_BORDER}",
            "boxShadow": "0 8px 20px rgba(0,0,0,0.25)",
        },
    )


def build_figures(asset_df, network_df, sensor_df, location_df, recent_df, station_sales_df, daily_sales_df):
    if asset_df.empty:
        asset_fig = px.bar(pd.DataFrame({"asset_id": [], "event_count": []}), x="asset_id", y="event_count", title="Telemetry Events by Asset")
    else:
        asset_fig = px.bar(
            asset_df.sort_values(by="event_count", ascending=False).head(20),
            x="asset_id",
            y="event_count",
            color="asset_type",
            title="Telemetry Events by Asset",
        )
    apply_dark_layout(asset_fig, 480)

    if network_df.empty:
        network_fig = px.pie(pd.DataFrame({"network_type": []}), names="network_type", title="Network Distribution")
    else:
        network_fig = px.pie(network_df, names="network_type", values="event_count", title="Network Distribution")
    apply_dark_layout(network_fig, 480)

    if sensor_df.empty:
        sensor_fig = px.bar(pd.DataFrame({"sensor_type": [], "event_count": []}), x="sensor_type", y="event_count", title="Sensor Event Volume")
    else:
        sensor_fig = px.bar(
            sensor_df.sort_values(by="event_count", ascending=False),
            x="sensor_type",
            y="event_count",
            color="sensor_type",
            title="Sensor Event Volume",
        )
    apply_dark_layout(sensor_fig, 480)

    if location_df.empty:
        map_fig = px.scatter_map(pd.DataFrame({"lat": [], "lon": []}), lat="lat", lon="lon", title="Latest Tanker Positions")
    else:
        map_fig = px.scatter_map(
            location_df,
            lat="lat",
            lon="lon",
            hover_name="asset_id",
            hover_data={
                "gateway_id": True,
                "network_type": True,
                "timestamp": True,
                "lat": False,
                "lon": False,
            },
            zoom=5,
            title="Latest Tanker Positions",
        )
        map_fig.update_traces(marker=dict(size=16, opacity=0.95))
    apply_dark_layout(map_fig, 620)

    if recent_df.empty:
        timeline_fig = px.histogram(pd.DataFrame({"timestamp": []}), x="timestamp", title="Recent Telemetry Timeline")
    else:
        timeline_df = recent_df.copy()
        timeline_df["timestamp"] = pd.to_datetime(timeline_df["timestamp"], errors="coerce")
        timeline_df = timeline_df.dropna(subset=["timestamp"])
        if timeline_df.empty:
            timeline_fig = px.histogram(pd.DataFrame({"timestamp": []}), x="timestamp", title="Recent Telemetry Timeline")
        else:
            timeline_fig = px.histogram(
                timeline_df,
                x="timestamp",
                color="asset_type" if "asset_type" in timeline_df.columns else None,
                title="Recent Telemetry Timeline",
            )
    apply_dark_layout(timeline_fig, 480)

    if station_sales_df.empty:
        sales_station_fig = px.bar(pd.DataFrame({"station_id": [], "revenue": []}), x="station_id", y="revenue", title="Revenue by Station")
    else:
        sales_station_grouped = (
            station_sales_df.groupby("station_id", as_index=False)[["revenue", "liters_sold"]]
            .sum()
            .sort_values(by="revenue", ascending=False)
        )
        sales_station_fig = px.bar(
            sales_station_grouped,
            x="station_id",
            y="revenue",
            title="Revenue by Station",
        )
    apply_dark_layout(sales_station_fig, 480)

    if daily_sales_df.empty:
        daily_sales_fig = px.bar(pd.DataFrame({"station_id": [], "sold_liters": []}), x="station_id", y="sold_liters", title="Daily Sold Liters by Station")
    else:
        daily_sales_fig = px.bar(
            daily_sales_df.sort_values(by="sold_liters", ascending=False),
            x="station_id",
            y="sold_liters",
            color="fuel_type",
            title="Daily Sold Liters by Station",
        )
    apply_dark_layout(daily_sales_fig, 480)

    return (
        asset_fig,
        network_fig,
        sensor_fig,
        map_fig,
        timeline_fig,
        sales_station_fig,
        daily_sales_fig,
    )


(
    stats,
    recent_df,
    asset_df,
    network_df,
    sensor_df,
    location_df,
    incident_summary,
    sales_summary,
    station_sales_df,
    daily_sales_df,
) = load_backend_data()

(
    asset_fig,
    network_fig,
    sensor_fig,
    map_fig,
    timeline_fig,
    sales_station_fig,
    daily_sales_fig,
) = build_figures(
    asset_df,
    network_df,
    sensor_df,
    location_df,
    recent_df,
    station_sales_df,
    daily_sales_df,
)

app = dash.Dash(__name__)
app.title = "Fuel Telemetry Live Control Room"

app.layout = html.Div(
    [
        dcc.Interval(id="refresh-interval", interval=5000, n_intervals=0),

        html.Div(
            [
                html.H1("Fuel Telemetry Live Control Room", style={"marginBottom": "6px", "color": TEXT_COLOR}),
                html.Div(
                    "Live backend-driven telemetry, integrity analytics, and station sales monitoring.",
                    style={"color": MUTED_TEXT, "marginBottom": "20px"},
                ),
                html.Div(
                    "Streaming simulation mode active.",
                    id="status-text",
                    style={"color": "#93c5fd", "marginBottom": "20px", "fontWeight": "bold"},
                ),
            ]
        ),

        html.Div(
            [
                html.Div(id="kpi-total-events", style={"width": "19%", "display": "inline-block", "marginRight": "1%", "marginBottom": "12px"}),
                html.Div(id="kpi-unique-assets", style={"width": "19%", "display": "inline-block", "marginRight": "1%", "marginBottom": "12px"}),
                html.Div(id="kpi-unique-gateways", style={"width": "19%", "display": "inline-block", "marginRight": "1%", "marginBottom": "12px"}),
                html.Div(id="kpi-gps-events", style={"width": "19%", "display": "inline-block", "marginRight": "1%", "marginBottom": "12px"}),
                html.Div(id="kpi-incident-count", style={"width": "19%", "display": "inline-block", "marginBottom": "12px"}),
            ]
        ),

        html.Div(
            [
                html.Div(id="kpi-latest-time", style={"width": "24%", "display": "inline-block", "marginRight": "1%", "marginBottom": "12px"}),
                html.Div(id="kpi-location-count", style={"width": "24%", "display": "inline-block", "marginRight": "1%", "marginBottom": "12px"}),
                html.Div(id="kpi-total-sales-liters", style={"width": "24%", "display": "inline-block", "marginRight": "1%", "marginBottom": "12px"}),
                html.Div(id="kpi-total-revenue", style={"width": "24%", "display": "inline-block", "marginBottom": "12px"}),
            ]
        ),

        html.Div(
            [
                html.A(
                    "Download Incident PDF",
                    id="incident-pdf-link",
                    href=f"{REPORT_BASE}/incident-pdf",
                    target="_blank",
                    style={
                        "display": "inline-block",
                        "padding": "12px 20px",
                        "backgroundColor": ACCENT_RED,
                        "color": "white",
                        "textDecoration": "none",
                        "borderRadius": "10px",
                        "fontWeight": "bold",
                        "marginBottom": "20px",
                        "marginRight": "12px",
                    },
                ),
                html.A(
                    "Download Sales PDF",
                    id="sales-pdf-link",
                    href=f"{REPORT_BASE}/sales-pdf",
                    target="_blank",
                    style={
                        "display": "inline-block",
                        "padding": "12px 20px",
                        "backgroundColor": ACCENT_GREEN,
                        "color": "white",
                        "textDecoration": "none",
                        "borderRadius": "10px",
                        "fontWeight": "bold",
                        "marginBottom": "20px",
                    },
                ),
                html.Div(
                    id="report-status-text",
                    style={"color": "#fca5a5", "marginTop": "10px", "marginBottom": "20px", "fontWeight": "bold"},
                ),
            ]
        ),

        dcc.Tabs(
            colors={"border": CARD_BORDER, "primary": ACCENT_BLUE, "background": PANEL_COLOR},
            children=[
                dcc.Tab(
                    label="Live Map",
                    style={"backgroundColor": PANEL_COLOR, "color": TEXT_COLOR, "border": f"1px solid {CARD_BORDER}"},
                    selected_style={"backgroundColor": BG_COLOR, "color": "white", "borderTop": f"2px solid {ACCENT_BLUE}"},
                    children=[
                        html.Div([dcc.Graph(id="live-map-graph", figure=map_fig)], style={"marginTop": "20px"}),
                    ],
                ),
                dcc.Tab(
                    label="Telemetry Analytics",
                    style={"backgroundColor": PANEL_COLOR, "color": TEXT_COLOR, "border": f"1px solid {CARD_BORDER}"},
                    selected_style={"backgroundColor": BG_COLOR, "color": "white", "borderTop": f"2px solid {ACCENT_BLUE}"},
                    children=[
                        html.Div(
                            [
                                html.Div([dcc.Graph(id="asset-chart-graph", figure=asset_fig)], style={"width": "49%", "display": "inline-block", "marginRight": "2%"}),
                                html.Div([dcc.Graph(id="network-chart-graph", figure=network_fig)], style={"width": "49%", "display": "inline-block"}),
                            ],
                            style={"marginTop": "20px"},
                        ),
                        html.Div(
                            [
                                html.Div([dcc.Graph(id="sensor-chart-graph", figure=sensor_fig)], style={"width": "49%", "display": "inline-block", "marginRight": "2%"}),
                                html.Div([dcc.Graph(id="timeline-chart-graph", figure=timeline_fig)], style={"width": "49%", "display": "inline-block"}),
                            ],
                            style={"marginTop": "10px"},
                        ),
                    ],
                ),
                dcc.Tab(
                    label="Sales Analytics",
                    style={"backgroundColor": PANEL_COLOR, "color": TEXT_COLOR, "border": f"1px solid {CARD_BORDER}"},
                    selected_style={"backgroundColor": BG_COLOR, "color": "white", "borderTop": f"2px solid {ACCENT_BLUE}"},
                    children=[
                        html.Div(
                            [
                                html.Div([dcc.Graph(id="sales-station-chart-graph", figure=sales_station_fig)], style={"width": "49%", "display": "inline-block", "marginRight": "2%"}),
                                html.Div([dcc.Graph(id="daily-sales-chart-graph", figure=daily_sales_fig)], style={"width": "49%", "display": "inline-block"}),
                            ],
                            style={"marginTop": "20px"},
                        ),
                        html.H3("Sales Per Delivery", style={"color": TEXT_COLOR, "marginTop": "20px"}),
                        dash_table.DataTable(
                            id="station-sales-table",
                            data=station_sales_df.to_dict("records"),
                            columns=[{"name": col, "id": col} for col in station_sales_df.columns],
                            page_size=10,
                            filter_action="native",
                            sort_action="native",
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "textAlign": "left",
                                "padding": "10px",
                                "backgroundColor": PANEL_COLOR,
                                "color": TEXT_COLOR,
                                "border": f"1px solid {CARD_BORDER}",
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": BG_COLOR,
                                "color": "white",
                                "border": f"1px solid {CARD_BORDER}",
                            },
                        ),
                        html.H3("Sales Per Day", style={"color": TEXT_COLOR, "marginTop": "20px"}),
                        dash_table.DataTable(
                            id="daily-sales-table",
                            data=daily_sales_df.to_dict("records"),
                            columns=[{"name": col, "id": col} for col in daily_sales_df.columns],
                            page_size=10,
                            filter_action="native",
                            sort_action="native",
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "textAlign": "left",
                                "padding": "10px",
                                "backgroundColor": PANEL_COLOR,
                                "color": TEXT_COLOR,
                                "border": f"1px solid {CARD_BORDER}",
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": BG_COLOR,
                                "color": "white",
                                "border": f"1px solid {CARD_BORDER}",
                            },
                        ),
                    ],
                ),
                dcc.Tab(
                    label="Recent Telemetry",
                    style={"backgroundColor": PANEL_COLOR, "color": TEXT_COLOR, "border": f"1px solid {CARD_BORDER}"},
                    selected_style={"backgroundColor": BG_COLOR, "color": "white", "borderTop": f"2px solid {ACCENT_BLUE}"},
                    children=[
                        html.H3("Latest Telemetry Events", style={"color": TEXT_COLOR, "marginTop": "20px"}),
                        dash_table.DataTable(
                            id="recent-telemetry-table",
                            data=recent_df.to_dict("records"),
                            columns=[{"name": col, "id": col} for col in recent_df.columns],
                            page_size=15,
                            filter_action="native",
                            sort_action="native",
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "textAlign": "left",
                                "padding": "10px",
                                "backgroundColor": PANEL_COLOR,
                                "color": TEXT_COLOR,
                                "border": f"1px solid {CARD_BORDER}",
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_header={
                                "fontWeight": "bold",
                                "backgroundColor": BG_COLOR,
                                "color": "white",
                                "border": f"1px solid {CARD_BORDER}",
                            },
                        ),
                    ],
                ),
            ],
        ),
    ],
    style={
        "padding": "20px",
        "fontFamily": "Arial, sans-serif",
        "backgroundColor": BG_COLOR,
        "minHeight": "100vh",
    },
)


@app.callback(
    Output("kpi-total-events", "children"),
    Output("kpi-unique-assets", "children"),
    Output("kpi-unique-gateways", "children"),
    Output("kpi-gps-events", "children"),
    Output("kpi-incident-count", "children"),
    Output("kpi-latest-time", "children"),
    Output("kpi-location-count", "children"),
    Output("kpi-total-sales-liters", "children"),
    Output("kpi-total-revenue", "children"),
    Output("report-status-text", "children"),
    Output("live-map-graph", "figure"),
    Output("asset-chart-graph", "figure"),
    Output("network-chart-graph", "figure"),
    Output("sensor-chart-graph", "figure"),
    Output("timeline-chart-graph", "figure"),
    Output("sales-station-chart-graph", "figure"),
    Output("daily-sales-chart-graph", "figure"),
    Output("recent-telemetry-table", "data"),
    Output("station-sales-table", "data"),
    Output("daily-sales-table", "data"),
    Input("refresh-interval", "n_intervals"),
)
def refresh_live_dashboard(_):
    (
        stats,
        recent_df,
        asset_df,
        network_df,
        sensor_df,
        location_df,
        incident_summary,
        sales_summary,
        station_sales_df,
        daily_sales_df,
    ) = load_backend_data()

    (
        asset_fig,
        network_fig,
        sensor_fig,
        map_fig,
        timeline_fig,
        sales_station_fig,
        daily_sales_fig,
    ) = build_figures(
        asset_df,
        network_df,
        sensor_df,
        location_df,
        recent_df,
        station_sales_df,
        daily_sales_df,
    )

    latest_time = stats.get("latest_timestamp", "No data yet")
    location_count = len(location_df)
    incident_count = incident_summary.get("incident_count", 0)
    report_status = incident_summary.get("message", "Report status unavailable.")

    total_liters_sold = sales_summary.get("total_liters_sold", 0)
    total_revenue = sales_summary.get("total_revenue", 0)

    return (
        kpi_card("Total Events", stats.get("total_events", 0), ACCENT_BLUE, "📡"),
        kpi_card("Unique Assets", stats.get("unique_assets", 0), ACCENT_GREEN, "🏭"),
        kpi_card("Unique Gateways", stats.get("unique_gateways", 0), ACCENT_PURPLE, "📶"),
        kpi_card("GPS Events", stats.get("gps_events", 0), ACCENT_ORANGE, "🛰️"),
        kpi_card("Incident Deliveries", incident_count, "#7c2d12", "📄"),
        kpi_card("Latest Timestamp", latest_time, ACCENT_RED, "⏰"),
        kpi_card("Mapped Tankers", location_count, ACCENT_CYAN, "🗺️"),
        kpi_card("Liters Sold", total_liters_sold, "#0f766e", "⛽"),
        kpi_card("Revenue", f"KES {total_revenue:,.2f}", "#15803d", "💰"),
        report_status,
        map_fig,
        asset_fig,
        network_fig,
        sensor_fig,
        timeline_fig,
        sales_station_fig,
        daily_sales_fig,
        recent_df.to_dict("records"),
        station_sales_df.to_dict("records"),
        daily_sales_df.to_dict("records"),
    )


if __name__ == "__main__":
    app.run(debug=True)