from datetime import datetime
from io import BytesIO
import os
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.database import Base, SessionLocal, engine
from backend.models import (
    TelemetryEvent,
    DeliveryAnalytics,
    TankerProfile,
    StationProfile,
    StationSale,
    DailyStationSales,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fuel Telemetry API")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

DELIVERY_RESULTS_PATH = os.path.join(DATA_DIR, "delivery_results.csv")
TANKER_PROFILE_PATH = os.path.join(DATA_DIR, "tanker_profiles.csv")
STATION_PROFILE_PATH = os.path.join(DATA_DIR, "station_profiles.csv")

# =========================
# SECURITY CONFIG
# =========================
SECRET_KEY = "supersecretkey123"
ALGORITHM = "HS256"
API_KEY = "fuel-iot-secure-key"

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
ADMIN_HASH = pwd_context.hash(ADMIN_PASSWORD)

fake_users_db = {
    ADMIN_USERNAME: {
        "username": ADMIN_USERNAME,
        "hashed_password": ADMIN_HASH,
        "role": "admin",
    }
}

# =========================
# PYDANTIC MODELS
# =========================
class TelemetryPayload(BaseModel):
    asset_type: str
    asset_id: str
    gateway_id: str
    sensor_id: str
    sensor_type: str
    value: str
    unit: str
    timestamp: str
    network_type: str


class LoginRequest(BaseModel):
    username: str
    password: str


# =========================
# AUTH HELPERS
# =========================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(username: str, password: str):
    user = fake_users_db.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict) -> str:
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# =========================
# UTIL
# =========================
def safe_read_csv(path: str) -> pd.DataFrame:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


# =========================
# ROOT + AUTH
# =========================
@app.get("/")
def root():
    return {"status": "ok", "service": "Fuel Telemetry API"}


@app.post("/api/auth/login")
def login(data: LoginRequest):
    user = authenticate_user(data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": user["username"],
        "role": user["role"],
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
    }


@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return user


# =========================
# TELEMETRY INGESTION
# =========================
@app.post("/api/telemetry")
def ingest_telemetry(
    payload: TelemetryPayload,
    x_api_key: str = Header(default=None),
):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    db = SessionLocal()
    try:
        event = TelemetryEvent(
            asset_type=payload.asset_type,
            asset_id=payload.asset_id,
            gateway_id=payload.gateway_id,
            sensor_id=payload.sensor_id,
            sensor_type=payload.sensor_type,
            value=str(payload.value),
            unit=payload.unit,
            timestamp=datetime.fromisoformat(payload.timestamp),
            network_type=payload.network_type,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return {
            "status": "accepted",
            "message": "Telemetry ingested successfully",
            "id": event.id,
        }
    finally:
        db.close()


# =========================
# TELEMETRY READ ENDPOINTS
# left open so dashboard keeps working
# =========================
@app.get("/api/telemetry/recent")
def get_recent_telemetry(limit: int = Query(default=100, ge=1, le=1000)):
    db = SessionLocal()
    try:
        rows = db.query(TelemetryEvent).order_by(TelemetryEvent.id.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "items": [
                {
                    "id": row.id,
                    "asset_type": row.asset_type,
                    "asset_id": row.asset_id,
                    "gateway_id": row.gateway_id,
                    "sensor_id": row.sensor_id,
                    "sensor_type": row.sensor_type,
                    "value": row.value,
                    "unit": row.unit,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "network_type": row.network_type,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/telemetry/stats")
def get_telemetry_stats():
    db = SessionLocal()
    try:
        total_events = db.query(func.count(TelemetryEvent.id)).scalar() or 0
        unique_assets = db.query(func.count(func.distinct(TelemetryEvent.asset_id))).scalar() or 0
        unique_gateways = db.query(func.count(func.distinct(TelemetryEvent.gateway_id))).scalar() or 0
        gps_events = (
            db.query(func.count(TelemetryEvent.id))
            .filter(TelemetryEvent.sensor_type == "TANKER_GPS")
            .scalar()
            or 0
        )

        latest_telemetry_ts = db.query(func.max(TelemetryEvent.timestamp)).scalar()
        latest_sales_ts = db.query(func.max(StationSale.sale_timestamp)).scalar()

        latest_candidates = [ts for ts in [latest_telemetry_ts, latest_sales_ts] if ts is not None]
        latest_ts = max(latest_candidates) if latest_candidates else None

        return {
            "total_events": total_events,
            "unique_assets": unique_assets,
            "unique_gateways": unique_gateways,
            "gps_events": gps_events,
            "latest_timestamp": latest_ts.isoformat() if latest_ts else None,
        }
    finally:
        db.close()


@app.get("/api/telemetry/by-asset")
def get_telemetry_by_asset():
    db = SessionLocal()
    try:
        rows = (
            db.query(
                TelemetryEvent.asset_type,
                TelemetryEvent.asset_id,
                func.count(TelemetryEvent.id).label("event_count"),
            )
            .group_by(TelemetryEvent.asset_type, TelemetryEvent.asset_id)
            .order_by(func.count(TelemetryEvent.id).desc())
            .all()
        )
        return {
            "items": [
                {
                    "asset_type": row.asset_type,
                    "asset_id": row.asset_id,
                    "event_count": row.event_count,
                }
                for row in rows
            ]
        }
    finally:
        db.close()


@app.get("/api/telemetry/by-network")
def get_telemetry_by_network():
    db = SessionLocal()
    try:
        rows = (
            db.query(
                TelemetryEvent.network_type,
                func.count(TelemetryEvent.id).label("event_count"),
            )
            .group_by(TelemetryEvent.network_type)
            .order_by(func.count(TelemetryEvent.id).desc())
            .all()
        )
        return {
            "items": [
                {
                    "network_type": row.network_type,
                    "event_count": row.event_count,
                }
                for row in rows
            ]
        }
    finally:
        db.close()


@app.get("/api/telemetry/by-sensor")
def get_telemetry_by_sensor():
    db = SessionLocal()
    try:
        rows = (
            db.query(
                TelemetryEvent.sensor_type,
                func.count(TelemetryEvent.id).label("event_count"),
            )
            .group_by(TelemetryEvent.sensor_type)
            .order_by(func.count(TelemetryEvent.id).desc())
            .all()
        )
        return {
            "items": [
                {
                    "sensor_type": row.sensor_type,
                    "event_count": row.event_count,
                }
                for row in rows
            ]
        }
    finally:
        db.close()


@app.get("/api/telemetry/latest-locations")
def get_latest_locations(asset_prefix: Optional[str] = None):
    db = SessionLocal()
    try:
        gps_rows = (
            db.query(TelemetryEvent)
            .filter(TelemetryEvent.sensor_type == "TANKER_GPS")
            .order_by(TelemetryEvent.id.desc())
            .all()
        )

        latest_by_asset = {}
        for row in gps_rows:
            if asset_prefix and not row.asset_id.startswith(asset_prefix):
                continue
            if row.asset_id in latest_by_asset:
                continue

            try:
                lat_str, lon_str = str(row.value).split(",")
                lat = float(lat_str.strip())
                lon = float(lon_str.strip())
            except Exception:
                continue

            latest_by_asset[row.asset_id] = {
                "asset_id": row.asset_id,
                "gateway_id": row.gateway_id,
                "sensor_id": row.sensor_id,
                "sensor_type": row.sensor_type,
                "lat": lat,
                "lon": lon,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "network_type": row.network_type,
            }

        return {"count": len(latest_by_asset), "items": list(latest_by_asset.values())}
    finally:
        db.close()


@app.get("/api/telemetry/raw")
def get_raw_telemetry(
    limit: int = Query(default=500, ge=1, le=5000),
    asset_type: Optional[str] = None,
    sensor_type: Optional[str] = None,
):
    db = SessionLocal()
    try:
        query = db.query(TelemetryEvent)

        if asset_type:
            query = query.filter(TelemetryEvent.asset_type == asset_type)

        if sensor_type:
            query = query.filter(TelemetryEvent.sensor_type == sensor_type)

        rows = query.order_by(TelemetryEvent.id.desc()).limit(limit).all()

        return {
            "count": len(rows),
            "items": [
                {
                    "id": row.id,
                    "asset_type": row.asset_type,
                    "asset_id": row.asset_id,
                    "gateway_id": row.gateway_id,
                    "sensor_id": row.sensor_id,
                    "sensor_type": row.sensor_type,
                    "value": row.value,
                    "unit": row.unit,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "network_type": row.network_type,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


# =========================
# ANALYTICS ENDPOINTS
# left open so dashboard keeps working
# =========================
@app.get("/api/analytics/deliveries/recent")
def get_recent_delivery_analytics(limit: int = Query(default=100, ge=1, le=1000)):
    db = SessionLocal()
    try:
        rows = db.query(DeliveryAnalytics).order_by(DeliveryAnalytics.id.desc()).limit(limit).all()

        return {
            "count": len(rows),
            "items": [
                {
                    "id": row.id,
                    "run_timestamp": row.run_timestamp.isoformat() if row.run_timestamp else None,
                    "batch_id": row.batch_id,
                    "fuel_type": row.fuel_type,
                    "origin": row.origin,
                    "destination": row.destination,
                    "loaded_volume": row.loaded_volume,
                    "delivered_volume": row.delivered_volume,
                    "difference": row.difference,
                    "alert": row.alert,
                    "quality_alert": row.quality_alert,
                    "combined_alert": row.combined_alert,
                    "expected_density": row.expected_density,
                    "actual_density": row.actual_density,
                    "status": row.status,
                    "reason": row.reason,
                    "tanker_id": row.tanker_id,
                    "route_risk_score": row.route_risk_score,
                    "sensor_fault_count": row.sensor_fault_count,
                    "failed_packet_count": row.failed_packet_count,
                    "delayed_packet_count": row.delayed_packet_count,
                    "ai_risk_level": row.ai_risk_level,
                    "anomaly_score": row.anomaly_score,
                    "anomaly_label": row.anomaly_label,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/analytics/incidents")
def get_incident_analytics(limit: int = Query(default=100, ge=1, le=1000)):
    db = SessionLocal()
    try:
        rows = (
            db.query(DeliveryAnalytics)
            .filter(
                (DeliveryAnalytics.combined_alert == True)
                | (DeliveryAnalytics.ai_risk_level != "NORMAL")
            )
            .order_by(DeliveryAnalytics.id.desc())
            .limit(limit)
            .all()
        )

        return {
            "count": len(rows),
            "items": [
                {
                    "batch_id": row.batch_id,
                    "tanker_id": row.tanker_id,
                    "origin": row.origin,
                    "destination": row.destination,
                    "difference": row.difference,
                    "quality_alert": row.quality_alert,
                    "combined_alert": row.combined_alert,
                    "ai_risk_level": row.ai_risk_level,
                    "route_risk_score": row.route_risk_score,
                    "run_timestamp": row.run_timestamp.isoformat() if row.run_timestamp else None,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/analytics/tanker-profiles")
def get_tanker_profiles():
    db = SessionLocal()
    try:
        rows = db.query(TankerProfile).order_by(TankerProfile.risk_score.desc()).all()
        return {
            "count": len(rows),
            "items": [
                {
                    "tanker_id": row.tanker_id,
                    "total_trips": row.total_trips,
                    "avg_loss_liters": row.avg_loss_liters,
                    "quantity_alert_count": row.quantity_alert_count,
                    "quality_alert_count": row.quality_alert_count,
                    "combined_alert_count": row.combined_alert_count,
                    "high_risk_trip_count": row.high_risk_trip_count,
                    "moderate_risk_trip_count": row.moderate_risk_trip_count,
                    "avg_anomaly_score": row.avg_anomaly_score,
                    "risk_score": row.risk_score,
                    "behavior_profile": row.behavior_profile,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/analytics/station-profiles")
def get_station_profiles():
    db = SessionLocal()
    try:
        rows = db.query(StationProfile).order_by(StationProfile.risk_score.desc()).all()
        return {
            "count": len(rows),
            "items": [
                {
                    "station_id": row.station_id,
                    "total_deliveries": row.total_deliveries,
                    "avg_loss_liters": row.avg_loss_liters,
                    "quantity_alert_count": row.quantity_alert_count,
                    "quality_alert_count": row.quality_alert_count,
                    "combined_alert_count": row.combined_alert_count,
                    "high_risk_delivery_count": row.high_risk_delivery_count,
                    "moderate_risk_delivery_count": row.moderate_risk_delivery_count,
                    "avg_anomaly_score": row.avg_anomaly_score,
                    "risk_score": row.risk_score,
                    "behavior_profile": row.behavior_profile,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/analytics/station-sales/recent")
def get_recent_station_sales(limit: int = Query(default=100, ge=1, le=1000)):
    db = SessionLocal()
    try:
        rows = db.query(StationSale).order_by(StationSale.sale_timestamp.desc(), StationSale.id.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "items": [
                {
                    "sale_timestamp": row.sale_timestamp.isoformat() if row.sale_timestamp else None,
                    "station_id": row.station_id,
                    "batch_id": row.batch_id,
                    "fuel_type": row.fuel_type,
                    "delivered_volume": row.delivered_volume,
                    "liters_sold": row.liters_sold,
                    "remaining_liters_estimate": row.remaining_liters_estimate,
                    "price_per_liter": row.price_per_liter,
                    "revenue": row.revenue,
                    "source": row.source,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/analytics/station-sales/daily")
def get_daily_station_sales():
    db = SessionLocal()
    try:
        rows = db.query(DailyStationSales).order_by(DailyStationSales.sales_date.desc(), DailyStationSales.station_id.asc()).all()
        return {
            "count": len(rows),
            "items": [
                {
                    "sales_date": row.sales_date,
                    "station_id": row.station_id,
                    "fuel_type": row.fuel_type,
                    "opening_stock_liters": row.opening_stock_liters,
                    "delivered_liters": row.delivered_liters,
                    "sold_liters": row.sold_liters,
                    "closing_stock_liters": row.closing_stock_liters,
                    "avg_price_per_liter": row.avg_price_per_liter,
                    "revenue": row.revenue,
                    "stock_variance_liters": row.stock_variance_liters,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ],
        }
    finally:
        db.close()


@app.get("/api/analytics/sales-summary")
def get_sales_summary():
    db = SessionLocal()
    try:
        total_sales_records = db.query(func.count(StationSale.id)).scalar() or 0
        total_daily_rows = db.query(func.count(DailyStationSales.id)).scalar() or 0
        total_liters_sold = db.query(func.coalesce(func.sum(StationSale.liters_sold), 0.0)).scalar() or 0.0
        total_revenue = db.query(func.coalesce(func.sum(StationSale.revenue), 0.0)).scalar() or 0.0
        active_sales_stations = db.query(func.count(func.distinct(StationSale.station_id))).scalar() or 0

        return {
            "total_sales_records": int(total_sales_records),
            "total_daily_rows": int(total_daily_rows),
            "total_liters_sold": round(float(total_liters_sold), 2),
            "total_revenue": round(float(total_revenue), 2),
            "active_sales_stations": int(active_sales_stations),
        }
    finally:
        db.close()


# =========================
# REPORT SUMMARY
# protected
# =========================
@app.get("/api/reports/incident-summary")
def incident_summary(user=Depends(get_current_user)):
    delivery_df = safe_read_csv(DELIVERY_RESULTS_PATH)

    if delivery_df.empty:
        return {
            "report_ready": False,
            "incident_count": 0,
            "high_risk_count": 0,
            "combined_alert_count": 0,
            "message": "No delivery analytics available yet.",
        }

    incident_df = delivery_df[
        (delivery_df["combined_alert"] == True) | (delivery_df["ai_risk_level"] != "NORMAL")
    ].copy()

    high_risk_count = int((delivery_df["ai_risk_level"] == "HIGH RISK").sum())
    combined_alert_count = int(delivery_df["combined_alert"].sum())

    return {
        "report_ready": True,
        "incident_count": int(len(incident_df)),
        "high_risk_count": high_risk_count,
        "combined_alert_count": combined_alert_count,
        "message": "Incident report available." if len(incident_df) > 0 else "No active incidents, but report can still be generated.",
    }


# =========================
# PDF BUILDERS
# =========================
def build_incident_pdf_bytes():
    delivery_df = safe_read_csv(DELIVERY_RESULTS_PATH)
    tanker_df = safe_read_csv(TANKER_PROFILE_PATH)
    station_df = safe_read_csv(STATION_PROFILE_PATH)

    incident_df = pd.DataFrame()
    if not delivery_df.empty:
        incident_df = delivery_df[
            (delivery_df["combined_alert"] == True) | (delivery_df["ai_risk_level"] != "NORMAL")
        ].copy()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0b1220"),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=16,
    )
    section_style = ParagraphStyle(
        "SectionStyle",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#111827"),
        spaceAfter=8,
        spaceBefore=8,
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )

    story = []
    story.append(Paragraph("Fuel Integrity Incident Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style))

    total_deliveries = len(delivery_df) if not delivery_df.empty else 0
    incident_count = len(incident_df) if not incident_df.empty else 0
    high_risk_count = int((delivery_df["ai_risk_level"] == "HIGH RISK").sum()) if not delivery_df.empty else 0
    combined_alert_count = int(delivery_df["combined_alert"].sum()) if not delivery_df.empty else 0

    story.append(Paragraph("Executive Summary", section_style))
    story.append(Paragraph(
        f"Total deliveries analysed: <b>{total_deliveries}</b>. "
        f"Incident deliveries: <b>{incident_count}</b>. "
        f"High-risk deliveries: <b>{high_risk_count}</b>. "
        f"Combined alerts: <b>{combined_alert_count}</b>.",
        body_style
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Incident Register", section_style))
    if incident_df.empty:
        story.append(Paragraph("No active incidents available at the moment.", body_style))
    else:
        rows = [["Batch", "Tanker", "Origin", "Destination", "Loss(L)", "Quality", "AI Risk"]]
        for _, row in incident_df.head(20).iterrows():
            rows.append([
                str(row.get("batch_id", "")),
                str(row.get("tanker_id", "")),
                str(row.get("origin", "")),
                str(row.get("destination", "")),
                str(row.get("difference", "")),
                "YES" if bool(row.get("quality_alert", False)) else "NO",
                str(row.get("ai_risk_level", "")),
            ])

        table = Table(rows, colWidths=[22 * mm, 22 * mm, 28 * mm, 28 * mm, 18 * mm, 18 * mm, 24 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b91c1c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)

    if not tanker_df.empty:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Top Tanker Profiles", section_style))
        rows = [["Tanker", "Trips", "Risk Score", "Profile"]]
        for _, row in tanker_df.head(8).iterrows():
            rows.append([
                str(row.get("tanker_id", "")),
                str(row.get("total_trips", "")),
                str(row.get("risk_score", "")),
                str(row.get("behavior_profile", "")),
            ])
        table = Table(rows, colWidths=[35 * mm, 22 * mm, 28 * mm, 35 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)

    if not station_df.empty:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Top Station Profiles", section_style))
        rows = [["Station", "Deliveries", "Risk Score", "Profile"]]
        for _, row in station_df.head(8).iterrows():
            rows.append([
                str(row.get("station_id", "")),
                str(row.get("total_deliveries", "")),
                str(row.get("risk_score", "")),
                str(row.get("behavior_profile", "")),
            ])
        table = Table(rows, colWidths=[35 * mm, 28 * mm, 28 * mm, 35 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def build_sales_pdf_bytes():
    db = SessionLocal()
    try:
        sales_rows = db.query(StationSale).order_by(StationSale.sale_timestamp.desc(), StationSale.id.desc()).limit(30).all()
        daily_rows = db.query(DailyStationSales).order_by(DailyStationSales.sales_date.desc(), DailyStationSales.station_id.asc()).limit(30).all()

        total_liters_sold = db.query(func.coalesce(func.sum(StationSale.liters_sold), 0.0)).scalar() or 0.0
        total_revenue = db.query(func.coalesce(func.sum(StationSale.revenue), 0.0)).scalar() or 0.0
        active_sales_stations = db.query(func.count(func.distinct(StationSale.station_id))).scalar() or 0
    finally:
        db.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SalesTitleStyle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0b1220"),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "SalesSubtitleStyle",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=16,
    )
    section_style = ParagraphStyle(
        "SalesSectionStyle",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#111827"),
        spaceAfter=8,
        spaceBefore=8,
    )
    body_style = ParagraphStyle(
        "SalesBodyStyle",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827"),
    )

    story = []
    story.append(Paragraph("Fuel Station Sales Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style))

    story.append(Paragraph("Executive Summary", section_style))
    story.append(Paragraph(
        f"Active sales stations: <b>{int(active_sales_stations)}</b>. "
        f"Total liters sold: <b>{round(float(total_liters_sold), 2)}</b>. "
        f"Total revenue: <b>KES {round(float(total_revenue), 2):,.2f}</b>.",
        body_style
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Sales Per Delivery", section_style))
    if not sales_rows:
        story.append(Paragraph("No station sales data available.", body_style))
    else:
        rows = [["Station", "Batch", "Fuel", "Sold", "Remain", "Price/L", "Revenue", "Time"]]
        for row in sales_rows:
            rows.append([
                str(row.station_id),
                str(row.batch_id),
                str(row.fuel_type),
                str(round(row.liters_sold, 2)),
                str(round(row.remaining_liters_estimate, 2)),
                str(round(row.price_per_liter, 2)),
                str(round(row.revenue, 2)),
                row.sale_timestamp.strftime("%H:%M:%S") if row.sale_timestamp else "",
            ])
        table = Table(rows, colWidths=[20 * mm, 20 * mm, 16 * mm, 16 * mm, 18 * mm, 16 * mm, 20 * mm, 20 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#15803d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ]))
        story.append(table)

    story.append(Spacer(1, 10))
    story.append(Paragraph("Sales Per Day", section_style))
    if not daily_rows:
        story.append(Paragraph("No daily station sales data available.", body_style))
    else:
        rows = [["Date", "Station", "Fuel", "Delivered", "Sold", "Closing", "Revenue"]]
        for row in daily_rows:
            rows.append([
                str(row.sales_date),
                str(row.station_id),
                str(row.fuel_type),
                str(round(row.delivered_liters, 2)),
                str(round(row.sold_liters, 2)),
                str(round(row.closing_stock_liters, 2)),
                str(round(row.revenue, 2)),
            ])
        table = Table(rows, colWidths=[24 * mm, 24 * mm, 18 * mm, 22 * mm, 20 * mm, 22 * mm, 24 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0369a1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ]))
        story.append(table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# =========================
# PDF ENDPOINTS
# protected
# =========================
@app.get("/api/reports/incident-pdf")
def incident_pdf(user=Depends(get_current_user)):
    pdf_bytes = build_incident_pdf_bytes()
    filename = f"fuel_incident_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/reports/sales-pdf")
def sales_pdf(user=Depends(get_current_user)):
    pdf_bytes = build_sales_pdf_bytes()
    filename = f"fuel_sales_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )