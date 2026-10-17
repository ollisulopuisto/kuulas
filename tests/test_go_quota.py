"""OpenCode Go spend against its dollar caps, from opencode's own records."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "go_quota", Path(__file__).parent.parent / "scripts" / "go_quota.py")
quota = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quota)

HOUR = 3_600_000
NOW = 1_000 * HOUR


def row(hours_ago, cost, model="kimi-k2.7-code", provider="opencode-go"):
    return {"providerID": provider, "modelID": model, "cost": cost,
            "time": {"created": NOW - hours_ago * HOUR}}


def test_spend_is_summed_per_window():
    rows = [row(1, 1.0), row(4, 2.0), row(6, 4.0), row(24 * 6, 8.0), row(24 * 20, 16.0)]
    spend = quota.spend(rows, NOW)
    assert spend == {"5h": 3.0, "7d": 15.0, "30d": 31.0}


def test_only_go_models_count():
    rows = [row(1, 5.0, provider="nvidia"), row(1, 1.0)]
    assert quota.spend(rows, NOW)["5h"] == 1.0


def test_records_without_a_cost_or_time_are_ignored():
    rows = [{"providerID": "opencode-go", "modelID": "x"},
            {"providerID": "opencode-go", "cost": None, "time": {"created": NOW}}]
    assert quota.spend(rows, NOW) == {"5h": 0.0, "7d": 0.0, "30d": 0.0}


def test_per_model_spend_in_the_short_window():
    rows = [row(1, 1.0), row(2, 0.5), row(1, 2.0, model="glm-5.2")]
    assert quota.by_model(rows, NOW) == {"kimi-k2.7-code": 1.5, "glm-5.2": 2.0}


def test_warning_levels():
    caps = quota.CAPS
    assert quota.level({"5h": 0.0, "7d": 0.0, "30d": 0.0}) == "ok"
    assert quota.level({"5h": caps["5h"] * 0.75, "7d": 0, "30d": 0}) == "warn"
    assert quota.level({"5h": 0, "7d": caps["7d"] * 0.95, "30d": 0}) == "stop"
