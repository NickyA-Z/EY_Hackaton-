"""Run the strategy plan from the terminal (the same LangGraph workflow the dashboard uses).

    PYTHONPATH=src uv run python -m backend.ai.plan --date 2026-07-19 --area port_la_course
    PYTHONPATH=src uv run python -m backend.ai.plan --no-rag          # strategist on the stored features alone
    PYTHONPATH=src uv run python -m backend.ai.plan --no-evaluate     # skip the simulator
    PYTHONPATH=src uv run python -m backend.ai.plan --repeat 3        # several samples, for an A/B comparison

Each run writes a folder under data/location_agent/runs/ and never touches the committed outputs.
"""

from __future__ import annotations

import argparse
import sys

from backend import paths
from backend.ai import service


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default="2026-07-19")
    p.add_argument("--area", default="port_la_course", choices=["port_la_course", "belmont_course"])
    p.add_argument("--no-rag", action="store_true", help="do not build or attach RAG insights")
    p.add_argument("--no-evaluate", action="store_true", help="skip the simulator evaluation")
    p.add_argument("--races", default="1,2,3", help="races to evaluate, e.g. 1,2,3")
    p.add_argument("--repeat", type=int, default=1, help="run the whole plan this many times")
    a = p.parse_args()
    for i in range(a.repeat):
        print(f"=== run {i + 1} of {a.repeat}: {a.date} {a.area}, RAG {'off' if a.no_rag else 'on'} ===")
        for event in service.plan(a.date, a.area, use_rag=not a.no_rag, run_evaluation=not a.no_evaluate,
                                  races=[int(x) for x in a.races.split(",")]):
            if isinstance(event, service.PlanStep):
                print(f"  [{event.name}] {event.detail}")
            else:
                print(f"  -> {paths.shown(paths.ROOT / event.run_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
