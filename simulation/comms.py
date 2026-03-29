import random
from typing import Dict


class BaseTransmitter:
    def __init__(self, network_type: str, success_rate: float, min_latency_ms: int, max_latency_ms: int, delay_threshold_ms: int):
        self.network_type = network_type
        self.success_rate = success_rate
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms
        self.delay_threshold_ms = delay_threshold_ms

    def send(self, packet: Dict) -> Dict:
        enriched = packet.copy()

        if packet.get("gateway_status") == "OFFLINE":
            enriched["transmission_network"] = self.network_type
            enriched["latency_ms"] = None
            enriched["delivered"] = False
            enriched["transmission_status"] = "FAILED"
            enriched["delay_flag"] = False
            enriched["comms_incident"] = "GATEWAY_OFFLINE"
            return enriched

        latency = random.randint(self.min_latency_ms, self.max_latency_ms)
        delivered = random.random() <= self.success_rate
        delay_flag = latency > self.delay_threshold_ms

        enriched["transmission_network"] = self.network_type
        enriched["latency_ms"] = latency
        enriched["delivered"] = delivered
        enriched["transmission_status"] = "DELIVERED" if delivered else "FAILED"
        enriched["delay_flag"] = delay_flag

        if not delivered:
            enriched["comms_incident"] = "PACKET_FAILED"
        elif delay_flag:
            enriched["comms_incident"] = "DELAYED_PACKET"
        else:
            enriched["comms_incident"] = "NONE"

        return enriched


class WiFiTransmitter(BaseTransmitter):
    def __init__(self):
        super().__init__("WiFi", 0.95, 20, 120, 90)


class GSMTransmitter(BaseTransmitter):
    def __init__(self):
        super().__init__("GSM", 0.90, 80, 400, 250)


class LoRaWANTransmitter(BaseTransmitter):
    def __init__(self):
        super().__init__("LoRaWAN", 0.88, 150, 900, 600)