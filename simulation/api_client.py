import requests
from datetime import datetime

API_URL = "https://fuel-backend-npaw.onrender.com/api/telemetry"   # replace if your backend URL is different
API_KEY = "fuel-iot-secure-key"


def send_telemetry(event):
    try:
        payload = {
            "asset_type": event.get("asset_type"),
            "asset_id": event.get("asset_id"),
            "gateway_id": event.get("gateway_id"),
            "sensor_id": event.get("sensor_id"),
            "sensor_type": event.get("sensor_type"),
            "value": str(event.get("value")),
            "unit": event.get("unit"),
            "timestamp": datetime.now().isoformat(),
            "network_type": event.get("network_type"),
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
        }

        response = requests.post(API_URL, json=payload, headers=headers, timeout=15)

        if response.status_code == 200:
            print(f"✔ SENT: {payload['asset_id']} | {payload['sensor_type']} = {payload['value']}")
        else:
            print(f"❌ API ERROR {response.status_code}: {response.text}")

    except Exception as e:
        print(f"❌ TRANSMISSION FAILED: {e}")