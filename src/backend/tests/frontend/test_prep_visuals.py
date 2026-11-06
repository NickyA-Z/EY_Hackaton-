from backend import strategy
from frontend.globe import boat_type, globe_events


def test_every_venue_class_has_a_boat_icon():
    kinds = {boat_type(c) for spot in strategy.VENUES.values() for c in spot["classes"]}
    assert kinds == {"dinghy", "470", "skiff", "cat", "windfoil", "kite"}


def test_only_backend_venues_can_be_entered():
    enterable = {e["id"] for e in globe_events() if e["enterable"]}
    assert enterable == set(strategy.VENUES)
