"""Budget flexibility is bounded, disclosed and independent of model arithmetic."""

from decimal import Decimal

import pytest
from conftest import make_build
from pydantic import ValidationError
from test_agent import flow, run

from budgeting import budget_notice, maximum_budget
from schemas import BudgetBreakdown, FinalResponse
from tools.registry import execute_tool


def test_exact_ten_percent_and_cent_boundary():
    assert maximum_budget(1000) == Decimal("1100.00")
    assert maximum_budget(100.01) == Decimal("110.01")
    accepted = BudgetBreakdown(
        flights=1100,
        accommodation=0,
        food=0,
        activities=0,
        local_transport=0,
        total=1100,
        remaining_budget=-100,
    )
    assert accepted.remaining_budget == -100
    with pytest.raises(ValidationError, match="10%"):
        BudgetBreakdown(
            flights=1100.01,
            accommodation=0,
            food=0,
            activities=0,
            local_transport=0,
            total=1100.01,
            remaining_budget=-100.01,
        )


@pytest.mark.parametrize(
    "target,status", [(243, "ok"), (230, "ok"), (220.91, "ok"), (220.90, "error")]
)
def test_demo_flexibility_rejects_above_cap(request_data, target, status):
    request_data["budget"] = target
    result = execute_tool("build_itinerary", make_build(request_data))
    assert result["status"] == status
    if status == "ok":
        b = result["data"]["budget_breakdown"]
        assert b["remaining_budget"] == pytest.approx(target - 243)
        assert b["total"] == 243
        if target < 243:
            assert any("Budget alternative" in w for w in result["data"]["warnings"])
    else:
        assert result["error"]["code"] == "over_budget"


def test_demo_precheck_does_not_reject_accepted_alternative(tmp_path, request_data):
    request_data["budget"] = 230
    agent, client, result = run(tmp_path, request_data, flow(request_data))
    assert result.status == "success"
    assert "above your" in result.message
    assert client.requests
    assert result.itinerary.budget_breakdown.remaining_budget == -13
    assert result.itinerary.trip_summary.origin == request_data["origin"]
    validation = agent.trace.data["budget_validation"]
    assert validation["valid"] and not validation["within_target"]
    assert validation["over_budget_amount"] == 13
    assert validation["maximum_with_flexibility"] == 253
    assert FinalResponse.model_validate_json(result.model_dump_json()) == result


def test_no_overrun_notice_when_within_target():
    assert budget_notice(1000, 999) is None
    assert "10.0%" in budget_notice(1000, 1100)
