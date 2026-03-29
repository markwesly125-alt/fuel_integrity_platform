from datetime import datetime

import pandas as pd

from backend.database import SessionLocal
from backend.models import (
    DeliveryAnalytics,
    TankerProfile,
    StationProfile,
    StationSale,
    DailyStationSales,
)


def safe_bool(value):
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ["true", "1", "yes"]


def safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_str(value, default=""):
    if pd.isna(value):
        return default
    return str(value)


def safe_dt(value):
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return datetime.now()


def sync_delivery_analytics_from_dataframe(df: pd.DataFrame):
    db = SessionLocal()
    try:
        db.query(DeliveryAnalytics).delete()

        if not df.empty:
            for _, row in df.iterrows():
                record = DeliveryAnalytics(
                    run_timestamp=safe_dt(row.get("run_timestamp")),
                    batch_id=safe_str(row.get("batch_id")),
                    fuel_type=safe_str(row.get("fuel_type")),
                    origin=safe_str(row.get("origin")),
                    destination=safe_str(row.get("destination")),
                    loaded_volume=safe_float(row.get("loaded_volume")),
                    delivered_volume=safe_float(row.get("delivered_volume")),
                    difference=safe_float(row.get("difference")),
                    alert=safe_bool(row.get("alert")),
                    quality_alert=safe_bool(row.get("quality_alert")),
                    combined_alert=safe_bool(row.get("combined_alert")),
                    expected_density=safe_float(row.get("expected_density")),
                    actual_density=safe_float(row.get("actual_density")),
                    status=safe_str(row.get("status")),
                    reason=safe_str(row.get("reason")),
                    tanker_id=safe_str(row.get("tanker_id")),
                    route_risk_score=safe_float(row.get("route_risk_score")),
                    sensor_fault_count=safe_int(row.get("sensor_fault_count")),
                    failed_packet_count=safe_int(row.get("failed_packet_count")),
                    delayed_packet_count=safe_int(row.get("delayed_packet_count")),
                    ai_risk_level=safe_str(row.get("ai_risk_level")),
                    anomaly_score=safe_float(row.get("anomaly_score")),
                    anomaly_label=safe_int(row.get("anomaly_label")),
                )
                db.add(record)

        db.commit()
    finally:
        db.close()


def sync_tanker_profiles_from_dataframe(df: pd.DataFrame):
    db = SessionLocal()
    try:
        db.query(TankerProfile).delete()

        if not df.empty:
            for _, row in df.iterrows():
                record = TankerProfile(
                    tanker_id=safe_str(row.get("tanker_id")),
                    total_trips=safe_int(row.get("total_trips")),
                    avg_loss_liters=safe_float(row.get("avg_loss_liters")),
                    quantity_alert_count=safe_int(row.get("quantity_alert_count")),
                    quality_alert_count=safe_int(row.get("quality_alert_count")),
                    combined_alert_count=safe_int(row.get("combined_alert_count")),
                    high_risk_trip_count=safe_int(row.get("high_risk_trip_count")),
                    moderate_risk_trip_count=safe_int(row.get("moderate_risk_trip_count")),
                    avg_anomaly_score=safe_float(row.get("avg_anomaly_score")),
                    risk_score=safe_float(row.get("risk_score")),
                    behavior_profile=safe_str(row.get("behavior_profile")),
                    updated_at=datetime.now(),
                )
                db.add(record)

        db.commit()
    finally:
        db.close()


def sync_station_profiles_from_dataframe(df: pd.DataFrame):
    db = SessionLocal()
    try:
        db.query(StationProfile).delete()

        if not df.empty:
            for _, row in df.iterrows():
                record = StationProfile(
                    station_id=safe_str(row.get("station_id")),
                    total_deliveries=safe_int(row.get("total_deliveries")),
                    avg_loss_liters=safe_float(row.get("avg_loss_liters")),
                    quantity_alert_count=safe_int(row.get("quantity_alert_count")),
                    quality_alert_count=safe_int(row.get("quality_alert_count")),
                    combined_alert_count=safe_int(row.get("combined_alert_count")),
                    high_risk_delivery_count=safe_int(row.get("high_risk_delivery_count")),
                    moderate_risk_delivery_count=safe_int(row.get("moderate_risk_delivery_count")),
                    avg_anomaly_score=safe_float(row.get("avg_anomaly_score")),
                    risk_score=safe_float(row.get("risk_score")),
                    behavior_profile=safe_str(row.get("behavior_profile")),
                    updated_at=datetime.now(),
                )
                db.add(record)

        db.commit()
    finally:
        db.close()


def sync_station_sales_from_dataframe(df: pd.DataFrame):
    db = SessionLocal()
    try:
        db.query(StationSale).delete()

        if not df.empty:
            for _, row in df.iterrows():
                record = StationSale(
                    sale_timestamp=safe_dt(row.get("sale_timestamp")),
                    station_id=safe_str(row.get("station_id")),
                    batch_id=safe_str(row.get("batch_id")),
                    fuel_type=safe_str(row.get("fuel_type")),
                    delivered_volume=safe_float(row.get("delivered_volume")),
                    liters_sold=safe_float(row.get("liters_sold")),
                    remaining_liters_estimate=safe_float(row.get("remaining_liters_estimate")),
                    price_per_liter=safe_float(row.get("price_per_liter")),
                    revenue=safe_float(row.get("revenue")),
                    source=safe_str(row.get("source"), "SIMULATED"),
                )
                db.add(record)

        db.commit()
    finally:
        db.close()


def sync_daily_station_sales_from_dataframe(df: pd.DataFrame):
    db = SessionLocal()
    try:
        db.query(DailyStationSales).delete()

        if not df.empty:
            for _, row in df.iterrows():
                record = DailyStationSales(
                    sales_date=safe_str(row.get("sales_date")),
                    station_id=safe_str(row.get("station_id")),
                    fuel_type=safe_str(row.get("fuel_type")),
                    opening_stock_liters=safe_float(row.get("opening_stock_liters")),
                    delivered_liters=safe_float(row.get("delivered_liters")),
                    sold_liters=safe_float(row.get("sold_liters")),
                    closing_stock_liters=safe_float(row.get("closing_stock_liters")),
                    avg_price_per_liter=safe_float(row.get("avg_price_per_liter")),
                    revenue=safe_float(row.get("revenue")),
                    stock_variance_liters=safe_float(row.get("stock_variance_liters")),
                    updated_at=datetime.now(),
                )
                db.add(record)

        db.commit()
    finally:
        db.close()