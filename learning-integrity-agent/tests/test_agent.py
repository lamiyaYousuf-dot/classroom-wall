import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
from loaders import load_report, parse_minutes, parse_percent  # noqa: E402
from signals import Settings, analyse  # noqa: E402

LINKEDIN = ROOT / "sample_data" / "linkedin_learning_sample.csv"
UDEMY = ROOT / "sample_data" / "udemy_business_sample.csv"


def findings():
    return {f.name: f for f in analyse(load_report(LINKEDIN) + load_report(UDEMY))}


def codes(f):
    return {s.code for s in f.signals}


@pytest.mark.parametrize("value,header,expected", [
    ("2h 4m", "", 124), ("58m", "", 58), ("01:30:00", "", 90), ("1.5", "Hours Viewed", 90),
    ("540", "Minutes Video Consumed", 540), ("90 seconds", "", 1.5), ("", "", None),
])
def test_parse_minutes(value, header, expected):
    assert parse_minutes(value, header) == expected


def test_parse_percent():
    assert parse_percent("100%") == 100
    assert parse_percent("0.85") == 85
    assert parse_percent("") is None


def test_platform_detection_and_article_skipped():
    li = load_report(LINKEDIN)
    assert {r.platform for r in li} == {"linkedin"}
    assert all(r.course != "How to Be a Good Mentee" for r in li)
    assert {r.platform for r in load_report(UDEMY)} == {"udemy"}


def test_agent_like_patterns_are_high_risk():
    f = findings()
    assert "OVERLAPPING_VIEWING" in codes(f["Jordan Lee"]) and f["Jordan Lee"].tier == "high"
    assert "UNBROKEN_MARATHON" in codes(f["Taylor Brooks"]) and f["Taylor Brooks"].tier == "high"
    assert "FASTER_THAN_POSSIBLE" in codes(f["Sam Patel"])


def test_genuine_learners_are_low_risk():
    f = findings()
    for name in ["Alex Rivera", "Morgan Chen", "Chris Morgan", "Casey Kim"]:
        assert f[name].tier == "low", (name, f[name].signals)
    # One night-time sitting on its own stays low.
    assert f["Priya Nair"].tier == "low"


def test_deadline_rush():
    recs = load_report(UDEMY)
    from datetime import datetime
    out = {f.name: f for f in analyse(recs, Settings(deadline=datetime(2026, 9, 28, 23, 59)))}
    assert "DEADLINE_RUSH" in codes(out["Taylor Brooks"])


def test_workspace_hides_names_and_reveal_restores_them():
    fs = analyse(load_report(LINKEDIN) + load_report(UDEMY))
    ws = agent.Workspace(fs, Settings())
    blob = ws.call("list_flagged_learners", {"min_tier": "low", "limit": 50})
    blob += "".join(ws.call("get_learner_detail", {"learner_ref": r}) for r in ws.by_ref)
    blob += ws.call("get_cohort_overview", {})
    assert "@example.com" not in blob and "Jordan" not in blob
    assert ws.reveal("Talk to L001 first.", share_names=True) == f"Talk to L001 ({fs[0].name}) first."
    assert ws.reveal("Talk to L001 first.", share_names=False) == "Talk to L001 first."
    with pytest.raises(KeyError):
        ws.call("get_learner_detail", {"learner_ref": "L999"})


def test_agent_loop_runs_tools_and_returns_report(monkeypatch):
    calls = []

    def tool_use(id_, name, inp):
        return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)

    replies = [
        SimpleNamespace(stop_reason="tool_use", content=[
            tool_use("t1", "get_cohort_overview", {}),
            tool_use("t2", "get_learner_detail", {"learner_ref": "nope"}),
        ]),
        SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="# Report\nL001")]),
    ]

    class FakeMessages:
        def create(self, **kw):
            calls.append(json.loads(json.dumps(kw["messages"], default=lambda o: o.__dict__)))
            assert kw["model"] == agent.MODEL and kw["fallbacks"] == "default"
            return replies[len(calls) - 1]

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    ws = agent.Workspace(analyse(load_report(LINKEDIN)), Settings())
    assert agent.run_agent(ws, "go", "low", verbose=False) == "# Report\nL001"
    results = calls[1][-1]["content"]
    assert results[0]["tool_use_id"] == "t1" and "learners" in results[0]["content"]
    assert results[1]["is_error"] is True
