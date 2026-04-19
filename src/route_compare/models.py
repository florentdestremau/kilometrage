from typing import Literal

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    origin: str = Field(..., description="Adresse ou ville de départ")
    destination: str = Field(..., description="Adresse ou ville d'arrivée")
    max_speed: int = Field(110, ge=50, le=130, description="Vitesse maximale en km/h")
    fuel_consumption_l_per_100: float = Field(
        6.5, ge=2.0, le=25.0, description="Consommation de référence à 90 km/h en L/100km"
    )
    fuel_price: float = Field(1.75, ge=0.5, le=5.0, description="Prix du carburant en €/L")


class Coord(BaseModel):
    lat: float
    lng: float


class Segment(BaseModel):
    distance_m: float
    avg_speed_kmh: float
    has_toll: bool = False


class CostBreakdown(BaseModel):
    fuel_liters: float
    fuel_eur: float
    toll_eur: float
    toll_km: float
    total_eur: float
    toll_confidence: Literal["estimated"] = "estimated"


class WaypointCity(BaseModel):
    name: str
    lat: float
    lng: float


class ExportLinks(BaseModel):
    waze: str
    google_maps: str
    apple_maps: str


class RouteResult(BaseModel):
    label: str
    preset: str
    distance_km: float
    duration_min: float
    avg_speed_kmh: float
    cost: CostBreakdown
    waypoint_cities: list[WaypointCity] = []
    export: ExportLinks
    geometry: list[list[float]]  # [[lng, lat], ...]


class ComparisonResponse(BaseModel):
    origin: str
    destination: str
    max_speed: int
    routes: list[RouteResult]  # triées par coût total croissant
    narrator_available: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
