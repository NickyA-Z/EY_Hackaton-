"""The selected-location map should request only a small local grid."""

from backend.compute import map_grid


def test_five_by_five_grid_uses_one_batch(monkeypatch):
    calls = []

    def fetch_points(coordinates, _day, _variables, *, batch_size, **_options):
        calls.append((len(coordinates), batch_size))
        return [{
            "latitude": latitude,
            "longitude": longitude,
            "hourly": {
                "time": ["2026-06-15T13:00"],
                "ocean_current_velocity": [1.0],
                "ocean_current_direction": [90.0],
            },
        } for latitude, longitude in coordinates]

    monkeypatch.setattr(map_grid, "fetch_grid_points", fetch_points)
    result = map_grid.get_map_grid.__wrapped__(
        33.7, -118.3, "2026-06-15", "Ocean currents",
        bounds=map_grid.local_bounds(33.7, -118.3, 4_000),
        grid_rows=5, grid_columns=5,
    )

    assert calls == [(25, 45)]
    assert (result["rows"], result["columns"]) == (5, 5)
    assert len(result["frames"][0]["value"]) == 25
