"""evaluate_strategy (split out of the CLI for the plan pipeline) reproduces the committed evaluation exactly."""

import json

from backend import paths
from backend.location_agent.evaluate import evaluate_strategy

DAY = paths.LOCATION_AGENT_OUTPUT_DIR / "2026-07-19_port_la_course"


def test_evaluate_strategy_matches_the_committed_evaluation(tmp_path):
    committed = json.loads((DAY / "evaluation.json").read_text())
    strategy_file = DAY / committed["strategy_file"]
    races = {x["race"] for x in committed["races"]}
    fresh = evaluate_strategy("2026-07-19", "port_la_course", json.loads(strategy_file.read_text()),
                              strategy_file.name, races, tmp_path)
    fresh = json.loads(json.dumps(fresh, default=str))
    for doc in (committed, fresh):
        doc.pop("created")
    assert fresh == committed
    assert (tmp_path / "evaluation.md").read_text() == (DAY / "evaluation.md").read_text()
