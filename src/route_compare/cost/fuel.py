"""
Calcul de consommation de carburant.

Modèle : conso(v) = conso_ref * (1 + 0.01 * max(0, v - 90))
- À 90 km/h → conso_ref (référence constructeur)
- À 110 km/h → conso_ref * 1.20 (+20%)
- À 130 km/h → conso_ref * 1.40 (+40%)

Ce modèle est indicatif (±15%). Voir README pour les limites.
"""

from route_compare.models import Segment


def consumption_factor(avg_speed_kmh: float) -> float:
    """Facteur multiplicatif de conso par rapport à 90 km/h."""
    return 1.0 + 0.01 * max(0.0, avg_speed_kmh - 90.0)


def segment_liters(
    distance_m: float,
    avg_speed_kmh: float,
    consumption_ref_l_per_100: float,
) -> float:
    """Litres consommés sur un segment donné."""
    factor = consumption_factor(avg_speed_kmh)
    distance_km = distance_m / 1000.0
    return distance_km * consumption_ref_l_per_100 * factor / 100.0


def total_fuel(
    segments: list[Segment],
    consumption_ref_l_per_100: float,
) -> float:
    """Litres totaux pour l'ensemble de l'itinéraire."""
    return sum(
        segment_liters(s.distance_m, s.avg_speed_kmh, consumption_ref_l_per_100)
        for s in segments
    )


def capped_duration_min(segments: list[Segment], max_speed: int) -> float:
    """
    Durée recalculée en appliquant un plafond de vitesse.

    Pour chaque segment dont la vitesse dépasse max_speed,
    on recalcule le temps : distance / max_speed.
    """
    total_s = 0.0
    for s in segments:
        effective = min(s.avg_speed_kmh, float(max_speed))
        if effective > 0:
            total_s += (s.distance_m / 1000.0 / effective) * 3600.0
    return total_s / 60.0


def parse_segments_from_path(path: dict) -> list[Segment]:
    """
    Extrait les segments depuis un chemin Graphhopper.

    Graphhopper retourne les détails sous forme d'intervalles :
    [{interval: [0, 5], values: ["MOTORWAY"]}, ...]
    """
    segments: list[Segment] = []
    points = path.get("points", {}).get("coordinates", [])
    details = path.get("details", {})

    road_class_details = details.get("road_class", [])
    toll_details = details.get("toll", [])
    max_speed_details = details.get("max_speed", [])

    # Index toll par intervalle de points
    toll_map = _build_interval_map(toll_details)
    speed_map = _build_interval_map(max_speed_details)

    if not road_class_details:
        # Pas de détails : un seul segment avec la durée/distance globale
        distance = path.get("distance", 0)
        duration_s = path.get("time", 0) / 1000  # ms → s
        avg_speed = (distance / 1000) / (duration_s / 3600) if duration_s > 0 else 90.0
        segments.append(Segment(distance_m=distance, avg_speed_kmh=avg_speed))
        return segments

    for interval_item in road_class_details:
        start, end = interval_item[0], interval_item[1]
        if end <= start or end > len(points) - 1:
            continue

        seg_points = points[start : end + 1]
        dist_m = _haversine_path(seg_points)

        # Vitesse : depuis max_speed si dispo, sinon estimation depuis durée globale
        speed = _speed_from_interval(speed_map, start, end)
        if speed is None:
            total_dist = path.get("distance", 1)
            total_time_s = path.get("time", 3600000) / 1000
            overall_speed = (total_dist / 1000) / (total_time_s / 3600)
            speed = overall_speed

        has_toll = _toll_from_interval(toll_map, start, end)

        segments.append(
            Segment(
                distance_m=dist_m,
                avg_speed_kmh=speed,
                has_toll=has_toll,
            )
        )

    return segments or [
        Segment(
            distance_m=path.get("distance", 0),
            avg_speed_kmh=90.0,
        )
    ]


def _build_interval_map(details: list) -> dict[tuple[int, int], object]:
    result = {}
    for item in details:
        result[(item[0], item[1])] = item[2]
    return result


def _speed_from_interval(
    speed_map: dict[tuple[int, int], object], start: int, end: int
) -> float | None:
    # Cherche l'intervalle qui contient le point médian du segment
    mid = (start + end) // 2
    for (s, e), val in speed_map.items():
        if s <= mid < e and isinstance(val, int | float):
            return float(val)
    return None


def _toll_from_interval(
    toll_map: dict[tuple[int, int], object], start: int, end: int
) -> bool:
    # Utilise le point médian : évite le problème des segments road_class qui
    # chevauchent plusieurs intervalles toll (ex: [96, 3708] sur Paris→Lyon).
    mid = (start + end) // 2
    for (s, e), val in toll_map.items():
        if s <= mid < e:
            return str(val).lower() not in ("no", "none", "")
    return False


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en mètres entre deux coordonnées (formule haversine)."""
    import math

    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _haversine_path(coords: list[list[float]]) -> float:
    """Distance totale d'une liste de coordonnées [lng, lat]."""
    total = 0.0
    for i in range(len(coords) - 1):
        lng1, lat1 = coords[i]
        lng2, lat2 = coords[i + 1]
        total += _haversine(lat1, lng1, lat2, lng2)
    return total
