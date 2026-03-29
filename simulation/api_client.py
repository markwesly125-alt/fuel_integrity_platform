import requests
from datetime import datetime

API_URL = "http://127.0.0.1:8000/api/telemetry"
API_KEY = "fuel-iot-secure-key"


def send_telemetry(event):
    try:
        payload = {
            "asset_type": event["asset_type"],
            "asset_id": event["asset_id"],
            "gateway_id": event["gateway_id"],
            "sensor_id": event["sensor_id"],
            "sensor_type": event["sensor_type"],
            "value": str(event["value"]),
            "unit": event["unit"],
            "timestamp": datetime.now().isoformat(),
            "network_type": event["network_type"],
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
        }

        response = requests.post(API_URL, json=payload, headers=headers, timeout=5)

        if response.status_code != 200:
            print(f"API ERROR {response.status_code}: {response.text}")

    except Exception as e:
        print(f"TRANSMISSION FAILED: {e}")