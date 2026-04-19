from route_compare.cost.fuel import consumption_factor, segment_liters, total_fuel
from route_compare.models import Segment


def test_consumption_factor_at_90():
    assert consumption_factor(90) == 1.0


def test_consumption_factor_at_110():
    assert consumption_factor(110) == pytest.approx(1.20)


def test_consumption_factor_below_90():
    assert consumption_factor(70) == 1.0  # pas de bonus sous 90


def test_consumption_factor_at_130():
    assert consumption_factor(130) == pytest.approx(1.40)


def test_segment_liters_basic():
    # 100 km à 90 km/h, conso ref 7 L/100 → 7 L
    liters = segment_liters(100_000, 90.0, 7.0)
    assert liters == pytest.approx(7.0)


def test_segment_liters_at_110():
    # 100 km à 110 km/h, conso ref 7 L/100 → 7 * 1.20 = 8.4 L
    liters = segment_liters(100_000, 110.0, 7.0)
    assert liters == pytest.approx(8.4)


def test_total_fuel_empty():
    assert total_fuel([], 6.5) == 0.0


def test_total_fuel_two_segments():
    segments = [
        Segment(distance_m=100_000, avg_speed_kmh=90.0),
        Segment(distance_m=100_000, avg_speed_kmh=110.0),
    ]
    # 100 km à 90 → 6.5 L ; 100 km à 110 → 6.5 * 1.2 = 7.8 L
    result = total_fuel(segments, 6.5)
    assert result == pytest.approx(6.5 + 7.8)


import pytest
