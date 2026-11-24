"""Regenerate clearly labeled test artifacts, never genuine LLM demonstrations."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_agent import flow, run  # noqa: E402 - script entry point sets its import paths


def main() -> None:
    directory = ROOT / "tests" / "artifacts"
    directory.mkdir(exist_ok=True)
    for name, recover in [("rome", False), ("paris", True)]:
        raw = json.loads((ROOT / "examples" / f"{name}.json").read_text())
        agent, _, result = run(directory, raw, flow(raw, recover))
        assert result.status == "success"
        assert agent.trace.data["execution_mode"] == "mocked_unit_test"
        target = directory / ("paris_recovery_mocked.json" if recover else "rome_mocked.json")
        agent.trace.path.replace(target)
        print(
            f"MOCKED test artifact: {target.name}, EUR {result.itinerary.budget_breakdown.total:.2f}"
        )


if __name__ == "__main__":
    main()
