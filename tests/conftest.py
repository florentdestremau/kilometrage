import os

import pytest

# Clés factices pour les tests (les appels HTTP sont mockés par respx)
os.environ.setdefault("GRAPHHOPPER_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("STORAGE_DIR", "/tmp/test-storage-rc")

os.makedirs("/tmp/test-storage-rc", exist_ok=True)


@pytest.fixture
def sample_path():
    """Chemin Graphhopper minimal pour les tests."""
    return {
        "distance": 500_000,  # 500 km
        "time": 18_000_000,   # 5h en ms
        "points": {
            "type": "LineString",
            "coordinates": [
                [6.12, 45.90],   # Annecy
                [4.83, 45.75],   # Lyon
                [2.35, 48.85],   # Paris
            ],
        },
        "details": {
            "road_class": [
                [0, 1, "MOTORWAY"],
                [1, 2, "MOTORWAY"],
            ],
            "toll": [
                [0, 1, "ALL"],
                [1, 2, "NO"],
            ],
            "max_speed": [
                [0, 1, 130],
                [1, 2, 110],
            ],
        },
    }
