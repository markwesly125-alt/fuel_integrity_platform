import random
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sklearn.ensemble import IsolationForest


def detect_possible_diversion(loaded_volume: float, delivered_volume: float, tolerance_liters: float = 50) -> Tuple[bool, float]:
    difference = loaded_volume - delivered_volume
    return difference > tolerance_liters, round(difference, 2)


def simulate_quality(fuel_type: str, expected_density: float) -> Tuple[float, bool]:
    adulterated = random.choice([False, False, False, True])

    if not adulterated:
        actual_density = expected_density + random.uniform(-2, 2)
        return round(actual_density, 2), False

    if fuel_type == "petrol":
        actual_density = expected_density + random.uniform(15, 35)
    else:
        actual_density = expected_density - random.uniform(15, 35)

    return round(actual_density, 2), True


def detect_quality_issue(expected_density: float, actual_density: float, tolerance: float = 5) -> bool:
    return abs(actual_density - expected_density) > tolerance


def random_sensor_fault_profile() -> Dict[str, object]:
    fault_type = random.choices(
        ["NONE", "NOISE", "DRIFT", "OFFLINE", "SPIKE"],
        weights=[0.70, 0.12, 0.08, 0.05, 0.05],
        k=1
    )[0]

    return {
        "fault_type": fault_type,
        "drift_value": round(random.uniform(-4, 4), 2) if fault_type == "DRIFT" else 0.0,
        "noise_scale": round(random.uniform(0.5, 3.0), 2) if fault_type == "NOISE" else 0.0,
        "spike_value": round(random.uniform(-25, 25), 2) if fault_type == "SPIKE" else 0.0,
    }


def apply_sensor_fault(value: float, unit: str, fault_profile: Dict[str, object]) -> Tuple[Optional[float], str]:
    fault_type = fault_profile["fault_type"]

    if fault_type == "OFFLINE":
        return None, "OFFLINE"

    adjusted = float(value)

    if fault_type == "NOISE":
        adjusted += random.uniform(-fault_profile["noise_scale"], fault_profile["noise_scale"])

    elif fault_type == "DRIFT":
        adjusted += fault_profile["drift_value"]

    elif fault_type == "SPIKE":
        adjusted += fault_profile["spike_value"]

    return round(adjusted, 2), "ONLINE"


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    feature_columns = [
        "loaded_volume",
        "delivered_volume",
        "difference",
        "expected_density",
        "actual_density",
        "alert",
        "quality_alert",
        "route_risk_score",
        "sensor_fault_count",
        "failed_packet_count",
        "delayed_packet_count",
    ]

    for col in feature_columns:
        if col not in df.columns:
            df[col] = 0

    df["alert"] = df["alert"].astype(int)
    df["quality_alert"] = df["quality_alert"].astype(int)

    return df[feature_columns].fillna(0)


def apply_anomaly_detection(current_results: List[Dict], history_df: Optional[pd.DataFrame] = None) -> List[Dict]:
    if not current_results:
        return current_results

    current_df = pd.DataFrame(current_results).copy()

    if history_df is not None and not history_df.empty:
        training_df = pd.concat([history_df.copy(), current_df.copy()], ignore_index=True)
    else:
        training_df = current_df.copy()

    X_train = prepare_features(training_df)
    X_current = prepare_features(current_df)

    contamination = 0.20
    if len(training_df) >= 60:
        contamination = 0.15
    if len(training_df) >= 120:
        contamination = 0.10

    model = IsolationForest(
        n_estimators=150,
        contamination=contamination,
        random_state=42,
    )
    model.fit(X_train)

    labels = model.predict(X_current)
    scores = model.decision_function(X_current)

    current_df["anomaly_label"] = labels
    current_df["anomaly_score"] = scores.round(6)

    def classify(row):
        if row["anomaly_label"] == -1:
            if row["difference"] > 100 or row["quality_alert"] == 1 or row["failed_packet_count"] >= 2:
                return "HIGH RISK"
            return "MODERATE RISK"
        return "NORMAL"

    current_df["ai_risk_level"] = current_df.apply(classify, axis=1)
    return current_df.to_dict("records")