"""Learning Integrity Agent.

Reads LinkedIn Learning / Udemy Business activity exports, flags completions
that look like nobody was really watching (for example an AI agent playing the
course in a background tab), and asks Claude to investigate the flags and write
a fair, actionable report: who to check in with, a short verification check per
flagged course, and changes that make "fake completion" pointless.

    python agent.py sample_data/linkedin_learning_sample.csv sample_data/udemy_business_sample.csv
    python agent.py export.csv --offline               # signals only, no API call
    python agent.py export.csv --ask "Who should I talk to first, and why?"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from loaders import Record, load_report
from signals import SIGNAL_INFO, LearnerFinding, Settings, analyse, cohort_stats

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You are a learning-integrity analyst working for an L&D team. Some learners have started using AI \
agents or auto-play tools to "watch" video courses on LinkedIn Learning and Udemy Business for them, \
so courses get marked complete without any learning happening. Your job is to look at the activity \
data through the tools you have, decide which completions deserve a follow-up, and write a report the \
L&D lead can act on today.

How to work:
- Start with the cohort overview, then look at the flagged learners in detail. Read the actual records \
before concluding anything; a single weak signal (one late-night completion, one skipped quiz) is normal \
behaviour.
- Treat signals as reasons to verify learning, never as proof of cheating. Some patterns are very hard \
to explain innocently (overlapping viewing windows, completing faster than possible at 2x); others have \
everyday explanations (skipping a course you already know, studying late). Say which is which.
- Learners are identified by pseudonymous references like L007. Use those references; you don't have \
names and shouldn't ask for them.
- If the data lacks something you need (for example times of day, so overlap can't be checked), say so \
plainly and explain what export setting would fix it.

The report (Markdown) should contain:
1. A short summary: how many learners and completions, how many look worth a follow-up, and how \
confident you are.
2. Learners to follow up with, most concerning first. For each: the evidence in plain language, the \
innocent explanations you considered, and a recommended action (verification check, conversation, or \
no action).
3. For each course you recommend verifying: a 3–5 question verification check. Make the questions \
applied and specific to the course topic (scenarios, "what would you do", explain-in-your-own-words), \
the kind that someone who actually followed the course can answer in ten minutes, and that someone who \
let an agent play it in the background can't.
4. A short, friendly message the L&D lead can send to flagged learners that invites them to the check \
without accusing anyone.
5. Program changes that remove the incentive and make passive completion useless on LinkedIn Learning \
and Udemy Business: e.g. stop rewarding raw completion counts, require the built-in quizzes or \
hands-on exercises, add reflection or apply-it tasks with manager sign-off, and measure outcomes \
rather than hours. Keep it to the changes this data suggests matter most.
"""

TOOLS = [
    {
        "name": "get_cohort_overview",
        "description": "Totals for the loaded exports: learners, completions, learners per risk tier, how often each signal fired, and whether the data includes time of day.",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "list_flagged_learners",
        "description": "Learners sorted by risk score, with their tier and which signals fired. Use min_tier 'low' to see everyone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_tier": {"type": "string", "enum": ["low", "medium", "high"]},
                "limit": {"type": "integer", "description": "Maximum learners to return (1-200)."},
            },
            "required": ["min_tier", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "get_learner_detail",
        "description": "Every course record for one learner (runtime, minutes watched, start/completion timestamps, assessment) plus each signal with its evidence.",
        "input_schema": {
            "type": "object",
            "properties": {"learner_ref": {"type": "string", "description": "Pseudonymous reference such as L003."}},
            "required": ["learner_ref"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "get_signal_definitions",
        "description": "What each signal code means, its weight, and the thresholds in use.",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
]


class Workspace:
    """Holds the findings and hands Claude pseudonymised views of them."""

    def __init__(self, findings: list[LearnerFinding], settings: Settings):
        self.settings = settings
        self.findings = findings
        self.ref_of = {f.learner_id: f"L{i:03d}" for i, f in enumerate(findings, 1)}
        self.by_ref = {self.ref_of[f.learner_id]: f for f in findings}

    def _record(self, r: Record) -> dict:
        fmt = "%Y-%m-%d %H:%M" if r.has_time_of_day else "%Y-%m-%d"
        return {
            "platform": r.platform,
            "course": r.course,
            "runtime_min": r.duration_min and round(r.duration_min),
            "watched_min": r.watched_min and round(r.watched_min),
            "percent": r.percent,
            "completed": r.completed,
            "started": r.started_at and r.started_at.strftime(fmt),
            "last_activity": r.last_at and r.last_at.strftime(fmt),
            "completed_at": r.completed_at and r.completed_at.strftime(fmt),
            "assessment_score": r.assessment,
            "assessment_available": r.assessment_available,
        }

    def call(self, name: str, args: dict) -> str:
        if name == "get_cohort_overview":
            return json.dumps(cohort_stats(self.findings))
        if name == "list_flagged_learners":
            order = {"low": 0, "medium": 1, "high": 2}
            limit = max(1, min(int(args.get("limit", 50)), 200))
            rows = [
                {"ref": self.ref_of[f.learner_id], "tier": f.tier, "score": f.score,
                 "completions": len(f.completions), "signals": sorted({s.code for s in f.signals})}
                for f in self.findings if order[f.tier] >= order[args.get("min_tier", "medium")]
            ]
            return json.dumps(rows[:limit])
        if name == "get_learner_detail":
            f = self.by_ref.get(args.get("learner_ref", "").strip().upper())
            if not f:
                raise KeyError(f"No learner {args.get('learner_ref')!r}. Use list_flagged_learners to see references.")
            return json.dumps({
                "ref": self.ref_of[f.learner_id], "tier": f.tier, "score": f.score,
                "records": [self._record(r) for r in f.records],
                "signals": [{"code": s.code, "weight": s.weight, "course": s.course, "evidence": s.detail} for s in f.signals],
            })
        if name == "get_signal_definitions":
            weights = {}
            for f in self.findings:
                for s in f.signals:
                    weights[s.code] = s.weight
            st = self.settings
            return json.dumps({
                "signals": {code: {"meaning": text, "weight": weights.get(code)} for code, text in SIGNAL_INFO.items()},
                "tiers": {"high": "score >= 8", "medium": "score 4-7", "low": "score < 4"},
                "thresholds": {
                    "max_playback_speed": st.max_playback_speed, "low_watch_ratio": st.low_watch_ratio,
                    "binge_courses_per_day": st.binge_courses_per_day, "binge_hours_per_day": st.binge_hours_per_day,
                    "marathon_minutes": st.marathon_minutes, "off_hours": list(st.off_hours),
                    "deadline": st.deadline and st.deadline.isoformat(),
                },
            })
        raise KeyError(f"Unknown tool {name!r}")

    def reveal(self, text: str, share_names: bool) -> str:
        """Add real names next to pseudonymous refs in the final, local-only report."""
        if not share_names:
            return text
        def label(m: re.Match) -> str:
            f = self.by_ref.get(m.group(0))
            return f"{m.group(0)} ({f.name})" if f else m.group(0)
        return re.sub(r"\bL\d{3,}\b", label, text)


def run_agent(ws: Workspace, task: str, effort: str, verbose: bool) -> str:
    import anthropic

    client = anthropic.Anthropic()
    messages: list = [{"role": "user", "content": task}]
    for _ in range(40):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined this request. Try rephrasing the question.")
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            if response.stop_reason == "max_tokens":
                text += "\n\n_(Report cut off at the length limit.)_"
            return text

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"  → {block.name}({json.dumps(block.input)})", file=sys.stderr)
            try:
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": ws.call(block.name, block.input)})
            except Exception as e:  # report tool errors back to Claude instead of crashing
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(e), "is_error": True})
        messages.append({"role": "user", "content": results})
    raise RuntimeError("Agent did not finish within 40 steps.")


def offline_report(ws: Workspace, share_names: bool) -> str:
    stats = cohort_stats(ws.findings)
    lines = [
        "# Learning integrity check (signals only)", "",
        f"{stats['learners']} learners, {stats['completions']} completions. "
        f"Tiers: {stats['learners_by_tier']}.", "",
    ]
    if not stats["data_has_time_of_day"]:
        lines += ["> The export has dates but no times, so overlapping-viewing and speed checks were skipped. "
                  "Export with timestamps for a stronger check.", ""]
    for f in ws.findings:
        if f.tier == "low":
            continue
        ref = ws.ref_of[f.learner_id]
        who = f"{ref} ({f.name})" if share_names else ref
        lines.append(f"## {who}: {f.tier} (score {f.score})")
        for s in f.signals:
            lines.append(f"- **{s.code}**{f' — {s.course}' if s.course else ''}: {s.detail}")
        lines.append("")
    lines += ["Run without `--offline` to have the agent review these flags and write verification checks.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reports", nargs="+", help="CSV exports from LinkedIn Learning and/or Udemy Business")
    p.add_argument("--platform", choices=["auto", "linkedin", "udemy"], default="auto")
    p.add_argument("--column-map", help="JSON file mapping our field names to your export's headers")
    p.add_argument("--deadline", help="Compliance deadline, e.g. 2026-09-30T23:59, to detect last-minute rushes")
    p.add_argument("--ask", help="Ask the agent a specific question instead of the full report")
    p.add_argument("--offline", action="store_true", help="Only run the local checks; don't call Claude")
    p.add_argument("--share-names", action="store_true",
                   help="Show real names in the saved report. Names are never sent to Claude either way.")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default="high")
    p.add_argument("--out", help="Write the report to this file (default: reports/integrity-<date>.md)")
    p.add_argument("-v", "--verbose", action="store_true", help="Print each tool call the agent makes")
    args = p.parse_args(argv)

    records: list[Record] = []
    for path in args.reports:
        loaded = load_report(path, args.platform, args.column_map)
        print(f"Loaded {len(loaded)} records from {path} ({loaded[0].platform if loaded else 'empty'})", file=sys.stderr)
        records += loaded
    if not records:
        print("No course records found.", file=sys.stderr)
        return 1

    settings = Settings(deadline=datetime.fromisoformat(args.deadline) if args.deadline else None)
    ws = Workspace(analyse(records, settings), settings)

    if args.offline:
        report = offline_report(ws, args.share_names)
    else:
        task = args.ask or "Review the loaded course activity and write the learning-integrity report."
        report = ws.reveal(run_agent(ws, task, args.effort, args.verbose), args.share_names)

    out = Path(args.out or f"reports/integrity-{datetime.now():%Y-%m-%d-%H%M}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nSaved to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
