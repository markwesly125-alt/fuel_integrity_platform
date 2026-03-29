from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean
from backend.database import Base


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id = Column(Integer, primary_key=True, index=True)
    asset_type = Column(String, nullable=False)
    asset_id = Column(String, nullable=False)
    gateway_id = Column(String, nullable=False)
    sensor_id = Column(String, nullable=False)
    sensor_type = Column(String, nullable=False)
    value = Column(String, nullable=False)
    unit = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    network_type = Column(String, nullable=False)


class DeliveryAnalytics(Base):
    __tablename__ = "delivery_analytics"

    id = Column(Integer, primary_key=True, index=True)
    run_timestamp = Column(DateTime, nullable=False)
    batch_id = Column(String, nullable=False)
    fuel_type = Column(String, nullable=False)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    loaded_volume = Column(Float, nullable=False)
    delivered_volume = Column(Float, nullable=False)
    difference = Column(Float, nullable=False)
    alert = Column(Boolean, nullable=False)
    quality_alert = Column(Boolean, nullable=False)
    combined_alert = Column(Boolean, nullable=False)
    expected_density = Column(Float, nullable=False)
    actual_density = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    tanker_id = Column(String, nullable=True)
    route_risk_score = Column(Float, nullable=False)
    sensor_fault_count = Column(Integer, nullable=False)
    failed_packet_count = Column(Integer, nullable=False)
    delayed_packet_count = Column(Integer, nullable=False)
    ai_risk_level = Column(String, nullable=False)
    anomaly_score = Column(Float, nullable=False)
    anomaly_label = Column(Integer, nullable=False)


class TankerProfile(Base):
    __tablename__ = "tanker_profiles"

    id = Column(Integer, primary_key=True, index=True)
    tanker_id = Column(String, nullable=False, unique=True)
    total_trips = Column(Integer, nullable=False)
    avg_loss_liters = Column(Float, nullable=False)
    quantity_alert_count = Column(Integer, nullable=False)
    quality_alert_count = Column(Integer, nullable=False)
    combined_alert_count = Column(Integer, nullable=False)
    high_risk_trip_count = Column(Integer, nullable=False)
    moderate_risk_trip_count = Column(Integer, nullable=False)
    avg_anomaly_score = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    behavior_profile = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class StationProfile(Base):
    __tablename__ = "station_profiles"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String, nullable=False, unique=True)
    total_deliveries = Column(Integer, nullable=False)
    avg_loss_liters = Column(Float, nullable=False)
    quantity_alert_count = Column(Integer, nullable=False)
    quality_alert_count = Column(Integer, nullable=False)
    combined_alert_count = Column(Integer, nullable=False)
    high_risk_delivery_count = Column(Integer, nullable=False)
    moderate_risk_delivery_count = Column(Integer, nullable=False)
    avg_anomaly_score = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    behavior_profile = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class StationSale(Base):
    __tablename__ = "station_sales"

    id = Column(Integer, primary_key=True, index=True)
    sale_timestamp = Column(DateTime, nullable=False)
    station_id = Column(String, nullable=False)
    batch_id = Column(String, nullable=False)
    fuel_type = Column(String, nullable=False)
    delivered_volume = Column(Float, nullable=False)
    liters_sold = Column(Float, nullable=False)
    remaining_liters_estimate = Column(Float, nullable=False)
    price_per_liter = Column(Float, nullable=False)
    revenue = Column(Float, nullable=False)
    source = Column(String, nullable=False)


class DailyStationSales(Base):
    __tablename__ = "daily_station_sales"

    id = Column(Integer, primary_key=True, index=True)
    sales_date = Column(String, nullable=False)
    station_id = Column(String, nullable=False)
    fuel_type = Column(String, nullable=False)
    opening_stock_liters = Column(Float, nullable=False)
    delivered_liters = Column(Float, nullable=False)
    sold_liters = Column(Float, nullable=False)
    closing_stock_liters = Column(Float, nullable=False)
    avg_price_per_liter = Column(Float, nullable=False)
    revenue = Column(Float, nullable=False)
    stock_variance_liters = Column(Float, nullable=False)
    updated_at = Column(DateTime, nullable=False)