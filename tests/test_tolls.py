import pytest

from route_compare.cost.tolls import toll_km_and_cost
from route_compare.models import Segment


def test_no_toll_segments():
    segments = [
        Segment(distance_m=200_000, avg_speed_kmh=90.0, has_toll=False),
        Segment(distance_m=100_000, avg_speed_kmh=90.0, has_toll=False),
    ]
    km, cost = toll_km_and_cost(segments, rate_eur_per_km=0.10)
    assert km == pytest.approx(0.0)
    assert cost == pytest.approx(0.0)


def test_all_toll_segments():
    segments = [
        Segment(distance_m=200_000, avg_speed_kmh=110.0, has_toll=True),
    ]
    km, cost = toll_km_and_cost(segments, rate_eur_per_km=0.10)
    assert km == pytest.approx(200.0)
    assert cost == pytest.approx(20.0)


def test_mixed_segments():
    segments = [
        Segment(distance_m=100_000, avg_speed_kmh=110.0, has_toll=True),
        Segment(distance_m=50_000, avg_speed_kmh=80.0, has_toll=False),
        Segment(distance_m=50_000, avg_speed_kmh=110.0, has_toll=True),
    ]
    km, cost = toll_km_and_cost(segments, rate_eur_per_km=0.10)
    assert km == pytest.approx(150.0)
    assert cost == pytest.approx(15.0)


def test_custom_rate():
    segments = [Segment(distance_m=100_000, avg_speed_kmh=110.0, has_toll=True)]
    _, cost = toll_km_and_cost(segments, rate_eur_per_km=0.20)
    assert cost == pytest.approx(20.0)
