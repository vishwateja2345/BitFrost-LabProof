"""Pure checks of the runtime acceptance recipe; do not launch Docker."""
import importlib.util
from pathlib import Path

import pytest

from labproof.local_profiles import validate_experiment_plan


@pytest.mark.parametrize("pack", ["python", "typescript", "c", "rust"])
def test_runtime_acceptance_covers_all_four_variants(pack):
    path = Path(__file__).resolve().parents[1] / "sandboxes/accept_runtime_v2.py"
    spec = importlib.util.spec_from_file_location("runtime_acceptance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = module.full_plan(pack)
    validate_experiment_plan(plan)
    assert len(plan["steps"]) == plan["budgets"]["actions"] == 8
    assert {(step["request"]["parameters"]["variant"], step["phase"]) for step in plan["steps"]} == {
        (variant, phase) for variant in ("alpha", "beta", "gamma", "delta")
        for phase in ("observation", "verification")}
