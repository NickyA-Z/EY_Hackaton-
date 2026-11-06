"""Every view of the merged dashboard (colleague's globe/Live design + the Previous strategy tab + AI panels) renders its own page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DASHBOARD = str(Path(__file__).resolve().parents[3] / "frontend" / "dashboard.py")

VIEWS = {  # active_view -> a header that proves it is that page and not an empty or fallback one
    "venue": "Geoinformation", "rules": "Venue rules", "coach_brief": "Coach brief", "sailor_brief": "Sailor brief",
    "overview": "Strategy overview", "speed": "Race replay & forecast", "previous": "Previous strategy", "coach": "Coach file",
}


def app(**state):
    at = AppTest.from_file(DASHBOARD, default_timeout=120)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def test_the_dashboard_opens_on_the_event_globe():
    at = app()
    assert not at.exception and not at.button  # no header navigation until a venue is entered


@pytest.mark.parametrize(("view", "header"), VIEWS.items())
def test_each_preparation_view_renders_its_own_page(view, header):
    at = app(globe_entered=True, active_view=view)
    assert not at.exception, at.exception
    assert header in [h.value for h in at.header]


def test_live_mode_shows_the_hourly_live_view():
    at = app(globe_entered=True, showcase_mode="● Live")
    assert not at.exception, at.exception
    assert any("kt" in b.label for b in at.button)  # the hour buttons carry the wind, e.g. "09:00  SW 3 kt"


def test_header_has_the_previous_strategy_tab_and_the_globe_button_but_no_live_button():
    at = app(globe_entered=True, active_view="venue")
    keys = [b.key for b in at.button]
    assert "show_previous_view" in keys and "show_globe" in keys and "show_live_view" not in keys
    next(b for b in at.button if b.key == "show_previous_view").click().run()
    assert at.session_state["active_view"] == "previous" and not at.exception
    next(b for b in at.button if b.key == "show_globe").click().run()
    assert at.session_state["globe_entered"] is False and not at.exception
