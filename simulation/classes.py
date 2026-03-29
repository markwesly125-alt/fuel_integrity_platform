from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FuelBatch:
    batch_id: str
    fuel_type: str
    volume_liters: float
    density: float
    origin: str
    destination: str
    expected_density: float
    actual_density: float
    quality_alert: bool = False


@dataclass
class Depot:
    depot_id: str
    storage_liters: float
    lat: float
    lon: float

    def load_tanker(self, tanker: "Tanker", fuel_batch: FuelBatch) -> None:
        tanker.batch = fuel_batch
        tanker.current_volume_liters = fuel_batch.volume_liters


@dataclass
class FuelStation:
    station_id: str
    lat: float
    lon: float
    tank_volume_liters: float = 0.0
    received_batches: List[FuelBatch] = field(default_factory=list)

    def receive_batch(self, batch: FuelBatch) -> None:
        self.received_batches.append(batch)
        self.tank_volume_liters += batch.volume_liters


@dataclass
class Tanker:
    tanker_id: str
    capacity_liters: float
    batch: Optional[FuelBatch] = None
    current_volume_liters: float = 0.0

    def transport(self, route_name: str, loss_liters: float) -> None:
        self.current_volume_liters = max(0.0, self.current_volume_liters - loss_liters)

    def deliver_to_station(self, station: FuelStation) -> FuelBatch:
        if self.batch is None:
            raise ValueError(f"{self.tanker_id} has no batch loaded.")

        delivered_batch = FuelBatch(
            batch_id=self.batch.batch_id,
            fuel_type=self.batch.fuel_type,
            volume_liters=self.current_volume_liters,
            density=self.batch.density,
            origin=self.batch.origin,
            destination=self.batch.destination,
            expected_density=self.batch.expected_density,
            actual_density=self.batch.actual_density,
            quality_alert=self.batch.quality_alert,
        )

        station.receive_batch(delivered_batch)
        self.batch = None
        self.current_volume_liters = 0.0
        return delivered_batch