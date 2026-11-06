"""A quota response should stop the remaining grid requests."""

from contextlib import nullcontext
from types import SimpleNamespace

import requests

from frontend import agent_views


def test_rate_limit_stops_remaining_layers_and_keeps_loaded_grid(monkeypatch):
    calls = []
    warnings = []
    state = {}

    def get_grid(_latitude, _longitude, _day, name, **options):
        calls.append(name)
        assert options["grid_rows"] == options["grid_columns"] == 5
        if name == "Waves":
            response = requests.Response()
            response.status_code = 429
            raise requests.HTTPError(response=response)
        return {"title": name}

    monkeypatch.setattr(agent_views, "get_map_grid", get_grid)
    monkeypatch.setattr(agent_views, "st", SimpleNamespace(
        session_state=state, spinner=lambda _message: nullcontext(),
        warning=warnings.append, error=lambda _message: None,
    ))

    names = ["Ocean currents", "Waves", "Wind waves"]
    assert agent_views.load_layer_grids(names, 33.7, -118.3, "2026-06-15") == [
        {"title": "Ocean currents"}
    ]
    assert calls == ["Ocean currents", "Waves"]
    assert state["marine_rate_limited"] is True
    assert len(warnings) == 1

    assert agent_views.load_layer_grids(names, 33.7, -118.3, "2026-06-15") == [
        {"title": "Ocean currents"}
    ]
    assert calls == ["Ocean currents", "Waves"]
