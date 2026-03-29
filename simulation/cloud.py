from datetime import datetime
from typing import Dict, List


class CloudServer:
    def __init__(self, server_id: str = "CLOUD-CORE-01"):
        self.server_id = server_id
        self.ingestion_log: List[Dict] = []

    def ingest(self, packet: Dict) -> Dict:
        record = packet.copy()
        record["cloud_server_id"] = self.server_id
        record["cloud_received_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if packet["delivered"]:
            record["cloud_status"] = "INGESTED"
            record["cloud_incident"] = "INGESTED_WITH_DELAY" if packet.get("delay_flag") else "NONE"
        else:
            record["cloud_status"] = "NOT_RECEIVED"
            if packet.get("comms_incident") == "GATEWAY_OFFLINE":
                record["cloud_incident"] = "GATEWAY_OFFLINE"
            else:
                record["cloud_incident"] = "NOT_RECEIVED"

        self.ingestion_log.append(record)
        return record