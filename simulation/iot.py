from datetime import datetime
import random
from typing import Dict, List, Optional


class SensorNode:
    def __init__(self, sensor_id: str, sensor_type: str, asset_id: str, unit: str):
        self.sensor_id = sensor_id
        self.sensor_type = sensor_type
        self.asset_id = asset_id
        self.unit = unit

    def read(self, value, sensor_status: str = "ONLINE", fault_type: str = "NONE") -> Dict:
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "asset_id": self.asset_id,
            "unit": self.unit,
            "value": value,
            "sensor_status": sensor_status,
            "sensor_fault_type": fault_type,
        }


class IoTGateway:
    def __init__(
        self,
        gateway_id: str,
        asset_id: str,
        asset_type: str,
        primary_network: str,
        fallback_network: Optional[str] = None,
        retry_limit: int = 2,
        status: str = "ONLINE",
    ):
        self.gateway_id = gateway_id
        self.asset_id = asset_id
        self.asset_type = asset_type
        self.primary_network = primary_network
        self.fallback_network = fallback_network
        self.retry_limit = retry_limit
        self.status = status
        self.buffer_queue: List[Dict] = []

    def randomize_status(self) -> None:
        self.status = random.choices(
            ["ONLINE", "OFFLINE"],
            weights=[0.92, 0.08],
            k=1
        )[0]

    def package(self, sensor_packet: Dict) -> Dict:
        return {
            "timestamp": sensor_packet["timestamp"],
            "gateway_id": self.gateway_id,
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "primary_network": self.primary_network,
            "fallback_network": self.fallback_network if self.fallback_network else "",
            "gateway_status": self.status,
            "sensor_id": sensor_packet["sensor_id"],
            "sensor_type": sensor_packet["sensor_type"],
            "unit": sensor_packet["unit"],
            "value": sensor_packet["value"],
            "sensor_status": sensor_packet["sensor_status"],
            "sensor_fault_type": sensor_packet["sensor_fault_type"],
        }

    def buffer_packet(self, packet: Dict) -> None:
        packet_copy = packet.copy()
        packet_copy["buffered"] = True
        self.buffer_queue.append(packet_copy)

    def pop_buffered_packets(self) -> List[Dict]:
        packets = self.buffer_queue[:]
        self.buffer_queue.clear()
        return packets

    def buffer_count(self) -> int:
        return len(self.buffer_queue)