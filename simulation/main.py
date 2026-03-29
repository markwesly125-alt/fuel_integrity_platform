import csv
import os
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from simulation.classes import FuelBatch, Depot, FuelStation, Tanker
from simulation.cloud import CloudServer
from simulation.comms import GSMTransmitter, LoRaWANTransmitter, WiFiTransmitter
from simulation.iot import IoTGateway, SensorNode
from simulation.api_client import send_telemetry
from simulation.utils import (
    apply_anomaly_detection,
    apply_sensor_fault,
    detect_possible_diversion,
    detect_quality_issue,
    random_sensor_fault_profile,
    simulate_quality,
)

from backend.analytics_db import (
    sync_delivery_analytics_from_dataframe,
    sync_tanker_profiles_from_dataframe,
    sync_station_profiles_from_dataframe,
    sync_station_sales_from_dataframe,
    sync_daily_station_sales_from_dataframe,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

DELIVERY_RESULTS_PATH = os.path.join(DATA_DIR, "delivery_results.csv")
STATION_STATUS_PATH = os.path.join(DATA_DIR, "station_status.csv")
TANKER_POSITIONS_PATH = os.path.join(DATA_DIR, "tanker_positions.csv")
HISTORY_PATH = os.path.join(DATA_DIR, "historical_delivery_results.csv")
TANKER_PROFILE_PATH = os.path.join(DATA_DIR, "tanker_profiles.csv")
STATION_PROFILE_PATH = os.path.join(DATA_DIR, "station_profiles.csv")
IOT_TRAFFIC_PATH = os.path.join(DATA_DIR, "iot_traffic_log.csv")
CLOUD_INGESTION_PATH = os.path.join(DATA_DIR, "cloud_ingestion_log.csv")
GATEWAY_STATUS_PATH = os.path.join(DATA_DIR, "gateway_status.csv")
COMMS_INCIDENTS_PATH = os.path.join(DATA_DIR, "comms_incidents.csv")
BUFFER_ACTIVITY_PATH = os.path.join(DATA_DIR, "gateway_buffer_log.csv")
SENSOR_EVENTS_PATH = os.path.join(DATA_DIR, "sensor_events_log.csv")

FUEL_TYPES = {
    "petrol": 750,
    "diesel": 840,
}

FUEL_PRICES = {
    "petrol": 182.0,
    "diesel": 168.0,
}

DEPOT_COORDS = {
    "Depot-A": (-1.286389, 36.817223),
    "Depot-B": (-4.043477, 39.668206),
    "Depot-C": (-0.102206, 34.761711),
}

STATION_COORDS = {
    "Station-01": (-1.2921, 36.8219),
    "Station-02": (-1.2833, 36.8167),
    "Station-03": (-3.2192, 40.1169),
    "Station-04": (-0.0917, 34.7680),
    "Station-05": (-0.3031, 36.0800),
    "Station-06": (-1.0332, 37.0692),
    "Station-07": (0.5143, 35.2698),
    "Station-08": (-0.2833, 36.0667),
    "Station-09": (-1.5167, 37.2667),
    "Station-10": (-2.5167, 40.1167),
}


def ensure_data_folder() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def create_depots() -> Dict[str, Depot]:
    return {
        depot_id: Depot(depot_id, storage_liters, coords[0], coords[1])
        for depot_id, storage_liters, coords in [
            ("Depot-A", 300000, DEPOT_COORDS["Depot-A"]),
            ("Depot-B", 250000, DEPOT_COORDS["Depot-B"]),
            ("Depot-C", 200000, DEPOT_COORDS["Depot-C"]),
        ]
    }


def create_stations() -> Dict[str, FuelStation]:
    return {
        station_id: FuelStation(station_id, coords[0], coords[1])
        for station_id, coords in STATION_COORDS.items()
    }


def create_tankers() -> Dict[str, Tanker]:
    return {
        "Tanker-001": Tanker("Tanker-001", 20000),
        "Tanker-002": Tanker("Tanker-002", 15000),
        "Tanker-003": Tanker("Tanker-003", 18000),
        "Tanker-004": Tanker("Tanker-004", 22000),
        "Tanker-005": Tanker("Tanker-005", 16000),
    }


def create_gateways(
    depots: Dict[str, Depot],
    stations: Dict[str, FuelStation],
    tankers: Dict[str, Tanker],
) -> Dict[str, IoTGateway]:
    gateways: Dict[str, IoTGateway] = {}

    for depot_id in depots:
        gateways[depot_id] = IoTGateway(
            gateway_id=f"GW-{depot_id}",
            asset_id=depot_id,
            asset_type="DEPOT",
            primary_network="LoRaWAN",
            fallback_network="GSM",
            retry_limit=2,
        )

    for station_id in stations:
        gateways[station_id] = IoTGateway(
            gateway_id=f"GW-{station_id}",
            asset_id=station_id,
            asset_type="STATION",
            primary_network="WiFi",
            fallback_network="GSM",
            retry_limit=2,
        )

    for tanker_id in tankers:
        gateways[tanker_id] = IoTGateway(
            gateway_id=f"GW-{tanker_id}",
            asset_id=tanker_id,
            asset_type="TANKER",
            primary_network="GSM",
            fallback_network=None,
            retry_limit=2,
        )

    return gateways


def randomize_gateway_statuses(gateways: Dict[str, IoTGateway]) -> None:
    for gateway in gateways.values():
        gateway.randomize_status()


def get_transmitter(network_type: str):
    if network_type == "WiFi":
        return WiFiTransmitter()
    if network_type == "GSM":
        return GSMTransmitter()
    return LoRaWANTransmitter()


def generate_random_batch(
    batch_number: int,
    depots: Dict[str, Depot],
    stations: Dict[str, FuelStation],
) -> FuelBatch:
    fuel_type = random.choice(list(FUEL_TYPES.keys()))
    expected_density = FUEL_TYPES[fuel_type]
    actual_density, quality_alert = simulate_quality(fuel_type, expected_density)

    depot = random.choice(list(depots.values()))
    station = random.choice(list(stations.values()))
    volume = random.randint(8000, 20000)

    return FuelBatch(
        batch_id=f"BATCH-{batch_number:03d}",
        fuel_type=fuel_type,
        volume_liters=volume,
        density=expected_density,
        origin=depot.depot_id,
        destination=station.station_id,
        expected_density=expected_density,
        actual_density=actual_density,
        quality_alert=quality_alert,
    )


def assign_tanker(tankers: Dict[str, Tanker], required_volume: float) -> Optional[Tanker]:
    available = [
        tanker for tanker in tankers.values()
        if tanker.capacity_liters >= required_volume and tanker.batch is None
    ]
    return random.choice(available) if available else None


def interpolate_route(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    steps: int = 20,
):
    points = []
    for step in range(steps + 1):
        fraction = step / steps
        lat = start_lat + (end_lat - start_lat) * fraction + random.uniform(-0.0015, 0.0015)
        lon = start_lon + (end_lon - start_lon) * fraction + random.uniform(-0.0015, 0.0015)
        points.append((step, round(lat, 6), round(lon, 6)))
    return points


def sensor_read_with_fault(sensor: SensorNode, raw_value: float, sensor_events: List[Dict]) -> Dict:
    fault_profile = random_sensor_fault_profile()
    adjusted_value, sensor_status = apply_sensor_fault(raw_value, sensor.unit, fault_profile)

    reading = sensor.read(
        value=adjusted_value,
        sensor_status=sensor_status,
        fault_type=fault_profile["fault_type"],
    )

    sensor_events.append({
        "timestamp": reading["timestamp"],
        "sensor_id": reading["sensor_id"],
        "sensor_type": reading["sensor_type"],
        "asset_id": reading["asset_id"],
        "unit": reading["unit"],
        "raw_value": raw_value,
        "adjusted_value": adjusted_value,
        "sensor_status": sensor_status,
        "fault_type": fault_profile["fault_type"],
    })
    return reading


def build_api_event_from_packet(packet: Dict, network_type: str) -> Dict:
    value = packet.get("value", "")
    if value is None:
        value = ""

    return {
        "asset_type": packet.get("asset_type", ""),
        "asset_id": packet.get("asset_id", ""),
        "gateway_id": packet.get("gateway_id", ""),
        "sensor_id": packet.get("sensor_id", ""),
        "sensor_type": packet.get("sensor_type", ""),
        "value": str(value),
        "unit": packet.get("unit", ""),
        "network_type": network_type,
    }


def log_comms_incident(packet: Dict, comms_incidents: List[Dict]) -> None:
    if packet.get("comms_incident") and packet["comms_incident"] != "NONE":
        comms_incidents.append({
            "timestamp": packet["timestamp"],
            "gateway_id": packet["gateway_id"],
            "asset_id": packet["asset_id"],
            "asset_type": packet["asset_type"],
            "network_type": packet["transmission_network"],
            "incident_type": packet["comms_incident"],
            "latency_ms": packet["latency_ms"],
            "transmission_status": packet["transmission_status"],
            "buffered": packet.get("buffered", False),
        })


def attempt_network_send(
    packet: Dict,
    network_type: str,
    cloud_server: CloudServer,
    iot_log: List[Dict],
    cloud_log: List[Dict],
    comms_incidents: List[Dict],
) -> Dict:
    transmitter = get_transmitter(network_type)
    transmitted = transmitter.send(packet)
    ingested = cloud_server.ingest(transmitted)

    iot_log.append(transmitted)
    cloud_log.append(ingested)
    log_comms_incident(transmitted, comms_incidents)

    if transmitted.get("delivered"):
        api_event = build_api_event_from_packet(transmitted, network_type)
        send_telemetry(api_event)

    return transmitted


def attempt_gateway_delivery(
    gateway: IoTGateway,
    packet: Dict,
    cloud_server: CloudServer,
    iot_log: List[Dict],
    cloud_log: List[Dict],
    comms_incidents: List[Dict],
    buffer_log: List[Dict],
    is_buffer_flush: bool = False,
) -> Dict:
    primary_network = gateway.primary_network
    fallback_network = gateway.fallback_network

    packet_to_send = packet.copy()
    packet_to_send["buffered"] = packet_to_send.get("buffered", False)

    for attempt in range(1, gateway.retry_limit + 2):
        packet_to_send["retry_attempt"] = attempt
        result = attempt_network_send(
            packet_to_send,
            primary_network,
            cloud_server,
            iot_log,
            cloud_log,
            comms_incidents,
        )
        if result["delivered"]:
            if is_buffer_flush:
                buffer_log.append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "gateway_id": gateway.gateway_id,
                    "asset_id": gateway.asset_id,
                    "event": "BUFFER_FLUSH_SUCCESS",
                    "buffer_size": gateway.buffer_count(),
                })
            return result

    if fallback_network:
        packet_to_send["fallback_used"] = True
        result = attempt_network_send(
            packet_to_send,
            fallback_network,
            cloud_server,
            iot_log,
            cloud_log,
            comms_incidents,
        )
        if result["delivered"]:
            buffer_log.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "gateway_id": gateway.gateway_id,
                "asset_id": gateway.asset_id,
                "event": "FALLBACK_SUCCESS",
                "buffer_size": gateway.buffer_count(),
            })
            return result

    gateway.buffer_packet(packet)
    buffer_log.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "gateway_id": gateway.gateway_id,
        "asset_id": gateway.asset_id,
        "event": "BUFFERED_PACKET",
        "buffer_size": gateway.buffer_count(),
    })

    return {
        **packet,
        "delivered": False,
        "transmission_status": "BUFFERED",
        "transmission_network": primary_network,
        "comms_incident": "BUFFERED_FOR_RETRY",
        "latency_ms": None,
        "delay_flag": False,
    }


def flush_gateway_buffer(
    gateway: IoTGateway,
    cloud_server: CloudServer,
    iot_log: List[Dict],
    cloud_log: List[Dict],
    comms_incidents: List[Dict],
    buffer_log: List[Dict],
) -> None:
    buffered_packets = gateway.pop_buffered_packets()
    if not buffered_packets:
        return

    for packet in buffered_packets:
        packet["buffer_flush_attempt"] = True
        result = attempt_gateway_delivery(
            gateway,
            packet,
            cloud_server,
            iot_log,
            cloud_log,
            comms_incidents,
            buffer_log,
            is_buffer_flush=True,
        )
        if not result["delivered"]:
            gateway.buffer_packet(packet)
            buffer_log.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "gateway_id": gateway.gateway_id,
                "asset_id": gateway.asset_id,
                "event": "BUFFER_REQUEUE",
                "buffer_size": gateway.buffer_count(),
            })


def simulate_gateway_traffic(
    gateway: IoTGateway,
    sensor_readings: List[Dict],
    cloud_server: CloudServer,
    iot_log: List[Dict],
    cloud_log: List[Dict],
    comms_incidents: List[Dict],
    buffer_log: List[Dict],
) -> Dict[str, int]:
    flush_gateway_buffer(gateway, cloud_server, iot_log, cloud_log, comms_incidents, buffer_log)

    stats = {
        "failed_packet_count": 0,
        "delayed_packet_count": 0,
        "sensor_fault_count": 0,
    }

    for reading in sensor_readings:
        packaged = gateway.package(reading)
        result = attempt_gateway_delivery(
            gateway,
            packaged,
            cloud_server,
            iot_log,
            cloud_log,
            comms_incidents,
            buffer_log,
        )

        if reading["sensor_fault_type"] != "NONE":
            stats["sensor_fault_count"] += 1

        if result.get("transmission_status") == "FAILED":
            stats["failed_packet_count"] += 1

        if result.get("delay_flag"):
            stats["delayed_packet_count"] += 1

    return stats


def stable_sales_ratio(batch_id: str) -> float:
    seed_value = sum(ord(char) for char in batch_id)
    rng = random.Random(seed_value)
    return round(rng.uniform(0.35, 0.88), 4)


def build_station_sales_dataframe(sales_history: List[Dict]) -> pd.DataFrame:
    if not sales_history:
        return pd.DataFrame(columns=[
            "sale_timestamp",
            "station_id",
            "batch_id",
            "fuel_type",
            "delivered_volume",
            "liters_sold",
            "remaining_liters_estimate",
            "price_per_liter",
            "revenue",
            "source",
        ])
    return pd.DataFrame(sales_history)


def build_daily_station_sales_dataframe(sales_df: pd.DataFrame) -> pd.DataFrame:
    if sales_df.empty:
        return pd.DataFrame(columns=[
            "sales_date",
            "station_id",
            "fuel_type",
            "opening_stock_liters",
            "delivered_liters",
            "sold_liters",
            "closing_stock_liters",
            "avg_price_per_liter",
            "revenue",
            "stock_variance_liters",
        ])

    df = sales_df.copy()
    df["sales_date"] = pd.to_datetime(df["sale_timestamp"], errors="coerce").dt.strftime("%Y-%m-%d")

    grouped = df.groupby(["sales_date", "station_id", "fuel_type"], as_index=False).agg(
        delivered_liters=("delivered_volume", "sum"),
        sold_liters=("liters_sold", "sum"),
        avg_price_per_liter=("price_per_liter", "mean"),
        revenue=("revenue", "sum"),
    )

    grouped["opening_stock_liters"] = 0.0
    grouped["closing_stock_liters"] = (grouped["delivered_liters"] - grouped["sold_liters"]).round(2)
    grouped["stock_variance_liters"] = 0.0
    grouped["avg_price_per_liter"] = grouped["avg_price_per_liter"].round(2)
    grouped["revenue"] = grouped["revenue"].round(2)

    return grouped


def create_sale_event(
    station_id: str,
    fuel_type: str,
    liters_sold: float,
    remaining_liters_estimate: float,
    batch_id: str,
    delivered_reference: float,
) -> Dict:
    price_per_liter = FUEL_PRICES.get(fuel_type, 170.0)
    return {
        "sale_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "station_id": station_id,
        "batch_id": batch_id,
        "fuel_type": fuel_type,
        "delivered_volume": round(delivered_reference, 2),
        "liters_sold": round(liters_sold, 2),
        "remaining_liters_estimate": round(max(remaining_liters_estimate, 0), 2),
        "price_per_liter": round(price_per_liter, 2),
        "revenue": round(liters_sold * price_per_liter, 2),
        "source": "STREAMING_STATION_SALES",
    }


def run_dynamic_sales_tick(
    station_inventory: Dict[Tuple[str, str], Dict],
    sales_history: List[Dict],
) -> None:
    for (station_id, fuel_type), stock in station_inventory.items():
        available = stock["remaining_liters"]
        if available <= 0:
            continue

        if random.random() > 0.72:
            continue

        liters_sold = min(round(random.uniform(40, 220), 2), available)
        stock["remaining_liters"] = round(max(available - liters_sold, 0), 2)
        stock["cumulative_sold"] = round(stock["cumulative_sold"] + liters_sold, 2)

        sales_history.append(
            create_sale_event(
                station_id=station_id,
                fuel_type=fuel_type,
                liters_sold=liters_sold,
                remaining_liters_estimate=stock["remaining_liters"],
                batch_id=stock["batch_id"],
                delivered_reference=stock["delivered_reference"],
            )
        )


def delivery_fieldnames():
    return [
        "run_timestamp",
        "batch_id",
        "fuel_type",
        "origin",
        "destination",
        "loaded_volume",
        "delivered_volume",
        "difference",
        "alert",
        "quality_alert",
        "combined_alert",
        "expected_density",
        "actual_density",
        "status",
        "reason",
        "tanker_id",
        "route_risk_score",
        "sensor_fault_count",
        "failed_packet_count",
        "delayed_packet_count",
        "ai_risk_level",
        "anomaly_score",
        "anomaly_label",
    ]


def write_delivery_results(results: List[Dict], run_timestamp: str) -> None:
    rows = []
    for row in results:
        row_copy = row.copy()
        row_copy["run_timestamp"] = run_timestamp
        rows.append(row_copy)

    with open(DELIVERY_RESULTS_PATH, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=delivery_fieldnames())
        writer.writeheader()
        writer.writerows(rows)


def append_historical_results(results: List[Dict], run_timestamp: str) -> None:
    file_exists = os.path.exists(HISTORY_PATH)

    rows = []
    for row in results:
        row_copy = row.copy()
        row_copy["run_timestamp"] = run_timestamp
        rows.append(row_copy)

    with open(HISTORY_PATH, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=delivery_fieldnames())
        if not file_exists or os.path.getsize(HISTORY_PATH) == 0:
            writer.writeheader()
        writer.writerows(rows)


def load_historical_results() -> pd.DataFrame:
    if not os.path.exists(HISTORY_PATH):
        return pd.DataFrame()
    try:
        return pd.read_csv(HISTORY_PATH)
    except Exception:
        return pd.DataFrame()


def build_tanker_profiles(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame(columns=[
            "tanker_id", "total_trips", "avg_loss_liters", "quantity_alert_count",
            "quality_alert_count", "combined_alert_count", "high_risk_trip_count",
            "moderate_risk_trip_count", "avg_anomaly_score", "risk_score", "behavior_profile",
        ])

    df = history_df.copy()
    df = df[df["tanker_id"].notna() & (df["tanker_id"] != "")]

    grouped = df.groupby("tanker_id", as_index=False).agg(
        total_trips=("batch_id", "count"),
        avg_loss_liters=("difference", "mean"),
        quantity_alert_count=("alert", "sum"),
        quality_alert_count=("quality_alert", "sum"),
        combined_alert_count=("combined_alert", "sum"),
        high_risk_trip_count=("ai_risk_level", lambda x: (x == "HIGH RISK").sum()),
        moderate_risk_trip_count=("ai_risk_level", lambda x: (x == "MODERATE RISK").sum()),
        avg_anomaly_score=("anomaly_score", "mean"),
    )

    grouped["risk_score"] = (
        grouped["avg_loss_liters"] / 20.0
        + grouped["quantity_alert_count"] * 2.0
        + grouped["quality_alert_count"] * 2.5
        + grouped["high_risk_trip_count"] * 3.0
        + grouped["moderate_risk_trip_count"] * 1.5
    )

    def classify_profile(row):
        if row["risk_score"] >= 15 or row["high_risk_trip_count"] >= 3:
            return "CRITICAL"
        if row["risk_score"] >= 8 or row["combined_alert_count"] >= 3:
            return "WATCHLIST"
        return "TRUSTED"

    grouped["behavior_profile"] = grouped.apply(classify_profile, axis=1)
    grouped["avg_loss_liters"] = grouped["avg_loss_liters"].round(2)
    grouped["avg_anomaly_score"] = grouped["avg_anomaly_score"].round(4)
    grouped["risk_score"] = grouped["risk_score"].round(2)

    return grouped.sort_values(by=["risk_score", "total_trips"], ascending=[False, False])


def build_station_profiles(history_df: pd.DataFrame) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame(columns=[
            "station_id", "total_deliveries", "avg_loss_liters", "quantity_alert_count",
            "quality_alert_count", "combined_alert_count", "high_risk_delivery_count",
            "moderate_risk_delivery_count", "avg_anomaly_score", "risk_score", "behavior_profile",
        ])

    df = history_df.copy()
    df = df[df["destination"].notna() & (df["destination"] != "")]

    grouped = df.groupby("destination", as_index=False).agg(
        total_deliveries=("batch_id", "count"),
        avg_loss_liters=("difference", "mean"),
        quantity_alert_count=("alert", "sum"),
        quality_alert_count=("quality_alert", "sum"),
        combined_alert_count=("combined_alert", "sum"),
        high_risk_delivery_count=("ai_risk_level", lambda x: (x == "HIGH RISK").sum()),
        moderate_risk_delivery_count=("ai_risk_level", lambda x: (x == "MODERATE RISK").sum()),
        avg_anomaly_score=("anomaly_score", "mean"),
    )

    grouped.rename(columns={"destination": "station_id"}, inplace=True)

    grouped["risk_score"] = (
        grouped["avg_loss_liters"] / 25.0
        + grouped["quantity_alert_count"] * 1.8
        + grouped["quality_alert_count"] * 2.2
        + grouped["high_risk_delivery_count"] * 2.8
        + grouped["moderate_risk_delivery_count"] * 1.2
    )

    def classify_profile(row):
        if row["risk_score"] >= 14 or row["high_risk_delivery_count"] >= 3:
            return "CRITICAL"
        if row["risk_score"] >= 7 or row["combined_alert_count"] >= 3:
            return "WATCHLIST"
        return "STABLE"

    grouped["behavior_profile"] = grouped.apply(classify_profile, axis=1)
    grouped["avg_loss_liters"] = grouped["avg_loss_liters"].round(2)
    grouped["avg_anomaly_score"] = grouped["avg_anomaly_score"].round(4)
    grouped["risk_score"] = grouped["risk_score"].round(2)

    return grouped.sort_values(by=["risk_score", "total_deliveries"], ascending=[False, False])


def write_tanker_profiles(profile_df: pd.DataFrame) -> None:
    profile_df.to_csv(TANKER_PROFILE_PATH, index=False)


def write_station_profiles(profile_df: pd.DataFrame) -> None:
    profile_df.to_csv(STATION_PROFILE_PATH, index=False)


def write_station_status(stations: Dict[str, FuelStation]) -> None:
    fieldnames = ["station_id", "tank_volume_liters", "received_batches_count", "lat", "lon"]
    with open(STATION_STATUS_PATH, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for station in stations.values():
            writer.writerow({
                "station_id": station.station_id,
                "tank_volume_liters": station.tank_volume_liters,
                "received_batches_count": len(station.received_batches),
                "lat": station.lat,
                "lon": station.lon,
            })


def write_tanker_positions(tanker_positions: List[Dict]) -> None:
    fieldnames = [
        "trip_id", "frame", "tanker_id", "batch_id", "origin", "destination",
        "lat", "lon", "fuel_type", "quality_alert",
    ]
    with open(TANKER_POSITIONS_PATH, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tanker_positions)


def write_iot_traffic_log(iot_log: List[Dict]) -> None:
    pd.DataFrame(iot_log).to_csv(IOT_TRAFFIC_PATH, index=False)


def write_cloud_ingestion_log(cloud_log: List[Dict]) -> None:
    pd.DataFrame(cloud_log).to_csv(CLOUD_INGESTION_PATH, index=False)


def write_gateway_status(gateways: Dict[str, IoTGateway]) -> None:
    rows = []
    for gateway in gateways.values():
        rows.append({
            "gateway_id": gateway.gateway_id,
            "asset_id": gateway.asset_id,
            "asset_type": gateway.asset_type,
            "primary_network": gateway.primary_network,
            "fallback_network": gateway.fallback_network if gateway.fallback_network else "",
            "gateway_status": gateway.status,
            "buffer_count": gateway.buffer_count(),
            "retry_limit": gateway.retry_limit,
        })
    pd.DataFrame(rows).to_csv(GATEWAY_STATUS_PATH, index=False)


def write_comms_incidents(comms_incidents: List[Dict]) -> None:
    pd.DataFrame(comms_incidents).to_csv(COMMS_INCIDENTS_PATH, index=False)


def write_buffer_activity(buffer_log: List[Dict]) -> None:
    pd.DataFrame(buffer_log).to_csv(BUFFER_ACTIVITY_PATH, index=False)


def write_sensor_events(sensor_events: List[Dict]) -> None:
    pd.DataFrame(sensor_events).to_csv(SENSOR_EVENTS_PATH, index=False)


def finalize_cycle(
    results: List[Dict],
    stations: Dict[str, FuelStation],
    gateways: Dict[str, IoTGateway],
    all_tanker_positions: List[Dict],
    iot_log: List[Dict],
    cloud_log: List[Dict],
    comms_incidents: List[Dict],
    buffer_log: List[Dict],
    sensor_events: List[Dict],
    sales_history: List[Dict],
) -> None:
    history_df = load_historical_results()
    enriched_results = apply_anomaly_detection(results, history_df=history_df)

    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_delivery_results(enriched_results, run_timestamp)
    append_historical_results(enriched_results, run_timestamp)

    updated_history_df = load_historical_results()
    tanker_profiles_df = build_tanker_profiles(updated_history_df)
    station_profiles_df = build_station_profiles(updated_history_df)

    write_tanker_profiles(tanker_profiles_df)
    write_station_profiles(station_profiles_df)
    write_station_status(stations)
    write_tanker_positions(all_tanker_positions)
    write_iot_traffic_log(iot_log)
    write_cloud_ingestion_log(cloud_log)
    write_gateway_status(gateways)
    write_comms_incidents(comms_incidents)
    write_buffer_activity(buffer_log)
    write_sensor_events(sensor_events)

    delivery_df = pd.DataFrame(enriched_results).copy()
    if not delivery_df.empty:
        delivery_df["run_timestamp"] = run_timestamp

    sales_df = build_station_sales_dataframe(sales_history)
    daily_sales_df = build_daily_station_sales_dataframe(sales_df)

    sync_delivery_analytics_from_dataframe(delivery_df)
    sync_tanker_profiles_from_dataframe(tanker_profiles_df)
    sync_station_profiles_from_dataframe(station_profiles_df)
    sync_station_sales_from_dataframe(sales_df)
    sync_daily_station_sales_from_dataframe(daily_sales_df)

    print("SYNC DEBUG -> delivery rows:", len(delivery_df))
    print("SYNC DEBUG -> tanker profile rows:", len(tanker_profiles_df))
    print("SYNC DEBUG -> station profile rows:", len(station_profiles_df))
    print("SYNC DEBUG -> station sales rows:", len(sales_df))
    print("SYNC DEBUG -> daily station sales rows:", len(daily_sales_df))
    print("SYNC DEBUG -> analytics sync completed")


def stream_trip(
    trip_id: int,
    fuel_batch: FuelBatch,
    depot: Depot,
    station: FuelStation,
    tanker: Tanker,
    gateways: Dict[str, IoTGateway],
    cloud_server: CloudServer,
    all_tanker_positions: List[Dict],
    iot_log: List[Dict],
    cloud_log: List[Dict],
    comms_incidents: List[Dict],
    buffer_log: List[Dict],
    sensor_events: List[Dict],
    station_inventory: Dict[Tuple[str, str], Dict],
    sales_history: List[Dict],
) -> Dict:
    loaded_volume = fuel_batch.volume_liters

    depot_volume_sensor = SensorNode(f"SENS-{depot.depot_id}-VOL", "DEPOT_LOADING_VOLUME", depot.depot_id, "L")
    depot_density_sensor = SensorNode(f"SENS-{depot.depot_id}-DEN", "DEPOT_DENSITY", depot.depot_id, "kg/m3")

    depot_readings = [
        sensor_read_with_fault(depot_volume_sensor, fuel_batch.volume_liters, sensor_events),
        sensor_read_with_fault(depot_density_sensor, fuel_batch.expected_density, sensor_events),
    ]
    depot_stats = simulate_gateway_traffic(
        gateways[depot.depot_id], depot_readings, cloud_server, iot_log, cloud_log, comms_incidents, buffer_log
    )

    depot.load_tanker(tanker, fuel_batch)

    route_positions = interpolate_route(depot.lat, depot.lon, station.lat, station.lon, steps=20)
    tanker_gps_sensor = SensorNode(f"SENS-{tanker.tanker_id}-GPS", "TANKER_GPS", tanker.tanker_id, "coords")

    tanker_failed = 0
    tanker_delayed = 0
    tanker_faults = 0

    for frame, lat, lon in route_positions:
        all_tanker_positions.append({
            "trip_id": trip_id,
            "frame": frame,
            "tanker_id": tanker.tanker_id,
            "batch_id": fuel_batch.batch_id,
            "origin": depot.depot_id,
            "destination": station.station_id,
            "lat": lat,
            "lon": lon,
            "fuel_type": fuel_batch.fuel_type,
            "quality_alert": fuel_batch.quality_alert,
        })

        gps_reading = sensor_read_with_fault(tanker_gps_sensor, 0.0, sensor_events)
        gps_reading["value"] = f"{lat},{lon}"

        tanker_stats = simulate_gateway_traffic(
            gateways[tanker.tanker_id], [gps_reading], cloud_server, iot_log, cloud_log, comms_incidents, buffer_log
        )
        tanker_failed += tanker_stats["failed_packet_count"]
        tanker_delayed += tanker_stats["delayed_packet_count"]
        tanker_faults += tanker_stats["sensor_fault_count"]

        run_dynamic_sales_tick(station_inventory, sales_history)
        time.sleep(0.3)

    loss_liters = random.choice([0, 10, 20, 35, 60, 120, 180])
    tanker.transport(f"{depot.depot_id} -> {station.station_id}", loss_liters)
    delivered_batch = tanker.deliver_to_station(station)

    delivered_volume = delivered_batch.volume_liters
    quantity_alert, difference = detect_possible_diversion(loaded_volume, delivered_volume, tolerance_liters=50)

    station_volume_sensor = SensorNode(f"SENS-{station.station_id}-TANK", "STATION_TANK_VOLUME", station.station_id, "L")
    station_density_sensor = SensorNode(f"SENS-{station.station_id}-DEN", "STATION_DENSITY", station.station_id, "kg/m3")

    station_readings = [
        sensor_read_with_fault(station_volume_sensor, delivered_volume, sensor_events),
        sensor_read_with_fault(station_density_sensor, delivered_batch.actual_density, sensor_events),
    ]
    station_stats = simulate_gateway_traffic(
        gateways[station.station_id], station_readings, cloud_server, iot_log, cloud_log, comms_incidents, buffer_log
    )

    quality_alert = detect_quality_issue(delivered_batch.expected_density, delivered_batch.actual_density, tolerance=5)
    combined_alert = quantity_alert or quality_alert

    inventory_key = (station.station_id, delivered_batch.fuel_type)
    previous_stock = station_inventory.get(inventory_key, {
        "remaining_liters": 0.0,
        "batch_id": delivered_batch.batch_id,
        "delivered_reference": delivered_volume,
        "cumulative_sold": 0.0,
    })

    station_inventory[inventory_key] = {
        "remaining_liters": round(previous_stock["remaining_liters"] + delivered_volume, 2),
        "batch_id": delivered_batch.batch_id,
        "delivered_reference": delivered_volume,
        "cumulative_sold": previous_stock.get("cumulative_sold", 0.0),
    }

    sales_ratio = stable_sales_ratio(delivered_batch.batch_id)
    initial_sale = round(min(delivered_volume * (sales_ratio * 0.18), station_inventory[inventory_key]["remaining_liters"]), 2)
    if initial_sale > 0:
        station_inventory[inventory_key]["remaining_liters"] = round(
            station_inventory[inventory_key]["remaining_liters"] - initial_sale, 2
        )
        station_inventory[inventory_key]["cumulative_sold"] = round(
            station_inventory[inventory_key]["cumulative_sold"] + initial_sale, 2
        )
        sales_history.append(
            create_sale_event(
                station_id=station.station_id,
                fuel_type=delivered_batch.fuel_type,
                liters_sold=initial_sale,
                remaining_liters_estimate=station_inventory[inventory_key]["remaining_liters"],
                batch_id=delivered_batch.batch_id,
                delivered_reference=delivered_volume,
            )
        )

    sensor_fault_count = depot_stats["sensor_fault_count"] + tanker_faults + station_stats["sensor_fault_count"]
    failed_packet_count = depot_stats["failed_packet_count"] + tanker_failed + station_stats["failed_packet_count"]
    delayed_packet_count = depot_stats["delayed_packet_count"] + tanker_delayed + station_stats["delayed_packet_count"]

    route_risk_score = round(
        (difference / 40.0)
        + (3.0 if quality_alert else 0.0)
        + (1.5 * failed_packet_count)
        + (0.7 * delayed_packet_count)
        + (0.8 * sensor_fault_count),
        2,
    )

    return {
        "batch_id": delivered_batch.batch_id,
        "fuel_type": delivered_batch.fuel_type,
        "origin": delivered_batch.origin,
        "destination": delivered_batch.destination,
        "loaded_volume": loaded_volume,
        "delivered_volume": delivered_volume,
        "difference": difference,
        "alert": quantity_alert,
        "quality_alert": quality_alert,
        "combined_alert": combined_alert,
        "expected_density": delivered_batch.expected_density,
        "actual_density": round(delivered_batch.actual_density, 2),
        "status": "SUCCESS",
        "reason": "",
        "tanker_id": tanker.tanker_id,
        "route_risk_score": route_risk_score,
        "sensor_fault_count": sensor_fault_count,
        "failed_packet_count": failed_packet_count,
        "delayed_packet_count": delayed_packet_count,
        "ai_risk_level": "NORMAL",
        "anomaly_score": 0.0,
        "anomaly_label": 1,
    }


def main() -> None:
    print("\n=== National Fuel Integrity Real-Time Streaming Simulation With Dynamic Sales ===\n")
    print("Press Ctrl + C to stop.\n")

    ensure_data_folder()

    depots = create_depots()
    stations = create_stations()
    tankers = create_tankers()
    gateways = create_gateways(depots, stations, tankers)
    cloud_server = CloudServer()

    results: List[Dict] = []
    all_tanker_positions: List[Dict] = []
    iot_log: List[Dict] = []
    cloud_log: List[Dict] = []
    comms_incidents: List[Dict] = []
    buffer_log: List[Dict] = []
    sensor_events: List[Dict] = []
    sales_history: List[Dict] = []
    station_inventory: Dict[Tuple[str, str], Dict] = {}

    batch_number = 1
    trip_id = 1

    try:
        while True:
            randomize_gateway_statuses(gateways)
            run_dynamic_sales_tick(station_inventory, sales_history)

            fuel_batch = generate_random_batch(batch_number, depots, stations)
            depot = depots[fuel_batch.origin]
            station = stations[fuel_batch.destination]
            tanker = assign_tanker(tankers, fuel_batch.volume_liters)

            if tanker is None:
                print(f"Trip {trip_id}: no tanker available, skipping.")
                time.sleep(1)
                batch_number += 1
                trip_id += 1
                continue

            print(f"Streaming trip {trip_id}: {fuel_batch.batch_id} | {depot.depot_id} -> {station.station_id} | {tanker.tanker_id}")

            result = stream_trip(
                trip_id=trip_id,
                fuel_batch=fuel_batch,
                depot=depot,
                station=station,
                tanker=tanker,
                gateways=gateways,
                cloud_server=cloud_server,
                all_tanker_positions=all_tanker_positions,
                iot_log=iot_log,
                cloud_log=cloud_log,
                comms_incidents=comms_incidents,
                buffer_log=buffer_log,
                sensor_events=sensor_events,
                station_inventory=station_inventory,
                sales_history=sales_history,
            )

            results.append(result)

            finalize_cycle(
                results=results,
                stations=stations,
                gateways=gateways,
                all_tanker_positions=all_tanker_positions,
                iot_log=iot_log,
                cloud_log=cloud_log,
                comms_incidents=comms_incidents,
                buffer_log=buffer_log,
                sensor_events=sensor_events,
                sales_history=sales_history,
            )

            print(
                f"Completed trip {trip_id} | diff={result['difference']} L | "
                f"quality_alert={result['quality_alert']} | risk_score={result['route_risk_score']}"
            )

            batch_number += 1
            trip_id += 1
            time.sleep(0.8)

    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")
        finalize_cycle(
            results=results,
            stations=stations,
            gateways=gateways,
            all_tanker_positions=all_tanker_positions,
            iot_log=iot_log,
            cloud_log=cloud_log,
            comms_incidents=comms_incidents,
            buffer_log=buffer_log,
            sensor_events=sensor_events,
            sales_history=sales_history,
        )


if __name__ == "__main__":
    main()