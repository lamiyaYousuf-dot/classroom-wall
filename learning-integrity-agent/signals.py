"""Deterministic checks that flag completions a human probably didn't learn from.

None of these signals is proof on its own: people play videos at 2x, skip
sections they already know, or leave a tab running at lunch. The point is to
find the completions worth a short, friendly verification check, not to
punish anyone. Weights reflect how hard each pattern is to explain innocently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from loaders import Record


@dataclass
class Settings:
    max_playback_speed: float = 2.0      # fastest speed both platforms offer
    low_watch_ratio: float = 0.6         # completed but watched less than this share of runtime
    binge_courses_per_day: int = 4
    binge_hours_per_day: float = 6.0
    marathon_minutes: float = 90.0       # a single unbroken sitting this long, matching runtime exactly
    off_hours: tuple[int, int] = (0, 5)  # local hours [start, end)
    deadline: datetime | None = None
    deadline_window_hours: int = 48


@dataclass
class Signal:
    code: str
    weight: int
    course: str | None
    detail: str


@dataclass
class LearnerFinding:
    learner_id: str
    name: str
    email: str
    records: list[Record]
    signals: list[Signal] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(s.weight for s in self.signals)

    @property
    def tier(self) -> str:
        return "high" if self.score >= 8 else "medium" if self.score >= 4 else "low"

    @property
    def completions(self) -> list[Record]:
        return [r for r in self.records if r.completed]


SIGNAL_INFO = {
    "OVERLAPPING_VIEWING": "Two or more courses were 'watched' in overlapping time windows. A person can't follow two videos at once; an agent running several browser tabs can.",
    "FASTER_THAN_POSSIBLE": "Time from first opening the course to completion is shorter than the runtime at the fastest playback speed.",
    "BINGE_DAY": "An unusually large amount of content completed within one day.",
    "LOW_WATCH_RATIO": "Marked complete, but recorded viewing time is well below the course runtime (skipping or scrubbing to the end).",
    "UNBROKEN_MARATHON": "A long course was finished in one sitting whose length matches the runtime almost exactly, with no pauses or rewinds. Typical of automated playback.",
    "SKIPPED_ASSESSMENT": "The course offers a quiz or assessment, but it wasn't attempted.",
    "WEAK_ASSESSMENT": "The course was completed but the assessment score is low.",
    "OFF_HOURS": "Completed in the middle of the night.",
    "DEADLINE_RUSH": "Many completions packed into the hours before a compliance deadline.",
}


def _window(r: Record) -> tuple[datetime, datetime] | None:
    end = r.completed_at or r.last_at
    if r.started_at and end and r.has_time_of_day and end > r.started_at:
        return r.started_at, end
    return None


def analyse(records: list[Record], settings: Settings | None = None) -> list[LearnerFinding]:
    s = settings or Settings()
    by_learner: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        by_learner[r.learner_id].append(r)

    findings = []
    for learner_id, recs in by_learner.items():
        f = LearnerFinding(learner_id, recs[0].name, recs[0].email, recs)
        done = f.completions

        for r in done:
            dur = r.duration_min
            win = _window(r)

            if dur and win:
                elapsed = (win[1] - win[0]).total_seconds() / 60
                if elapsed < dur / s.max_playback_speed * 0.95:
                    f.signals.append(Signal("FASTER_THAN_POSSIBLE", 4, r.course,
                        f"{elapsed:.0f} min from start to completion for a {dur:.0f} min course "
                        f"(minimum at {s.max_playback_speed:g}x is {dur / s.max_playback_speed:.0f} min)"))
                elif dur >= s.marathon_minutes and abs(elapsed - dur) <= max(3, dur * 0.03):
                    f.signals.append(Signal("UNBROKEN_MARATHON", 2, r.course,
                        f"{dur:.0f} min course finished in a single {elapsed:.0f} min sitting with no breaks"))

            if dur and r.watched_min is not None and r.watched_min < dur * s.low_watch_ratio:
                f.signals.append(Signal("LOW_WATCH_RATIO", 2, r.course,
                    f"watched {r.watched_min:.0f} of {dur:.0f} min ({r.watched_min / dur:.0%}) but marked complete"))

            if r.assessment_available and r.assessment is None:
                f.signals.append(Signal("SKIPPED_ASSESSMENT", 1, r.course, "assessment available but not attempted"))
            elif r.assessment is not None and r.assessment < 50:
                f.signals.append(Signal("WEAK_ASSESSMENT", 2, r.course, f"assessment score {r.assessment:.0f}%"))

            if r.completed_at and r.has_time_of_day and s.off_hours[0] <= r.completed_at.hour < s.off_hours[1]:
                f.signals.append(Signal("OFF_HOURS", 1, r.course, f"completed at {r.completed_at:%H:%M}"))

        # Overlapping viewing windows across different courses.
        windows = sorted(((w, r) for r in done if (w := _window(r))), key=lambda x: x[0][0])
        seen_pairs = set()
        for i, (wa, ra) in enumerate(windows):
            for wb, rb in windows[i + 1:]:
                if wb[0] >= wa[1]:
                    break
                overlap = (min(wa[1], wb[1]) - wb[0]).total_seconds() / 60
                pair = frozenset((ra.course, rb.course))
                if overlap >= 15 and ra.course != rb.course and pair not in seen_pairs:
                    seen_pairs.add(pair)
                    f.signals.append(Signal("OVERLAPPING_VIEWING", 4, f"{ra.course} / {rb.course}",
                        f"viewing windows overlap by {overlap:.0f} min "
                        f"({wa[0]:%Y-%m-%d %H:%M}–{wa[1]:%H:%M} and {wb[0]:%H:%M}–{wb[1]:%H:%M})"))

        # Binge days.
        per_day: dict = defaultdict(list)
        for r in done:
            if r.completed_at:
                per_day[r.completed_at.date()].append(r)
        for day, rs in sorted(per_day.items()):
            hours = sum(r.duration_min or 0 for r in rs) / 60
            if len(rs) >= s.binge_courses_per_day or hours >= s.binge_hours_per_day:
                f.signals.append(Signal("BINGE_DAY", 3, None,
                    f"{len(rs)} courses / {hours:.1f} h of content completed on {day}"))

        # Deadline rush.
        if s.deadline:
            start = s.deadline - timedelta(hours=s.deadline_window_hours)
            rushed = [r for r in done if r.completed_at and start <= r.completed_at <= s.deadline]
            if len(rushed) >= 3 and len(rushed) >= 0.6 * len(done):
                f.signals.append(Signal("DEADLINE_RUSH", 2, None,
                    f"{len(rushed)} of {len(done)} completions in the {s.deadline_window_hours} h before the deadline"))

        findings.append(f)

    findings.sort(key=lambda f: f.score, reverse=True)
    return findings


def cohort_stats(findings: list[LearnerFinding]) -> dict:
    completions = [r for f in findings for r in f.completions]
    ratios = [r.watched_min / r.duration_min for r in completions if r.watched_min is not None and r.duration_min]
    tiers = defaultdict(int)
    codes = defaultdict(int)
    for f in findings:
        tiers[f.tier] += 1
        for sig in f.signals:
            codes[sig.code] += 1
    return {
        "learners": len(findings),
        "completions": len(completions),
        "median_watch_ratio": round(sorted(ratios)[len(ratios) // 2], 2) if ratios else None,
        "learners_by_tier": dict(tiers),
        "signal_counts": dict(sorted(codes.items(), key=lambda kv: -kv[1])),
        "data_has_time_of_day": any(r.has_time_of_day for f in findings for r in f.records),
    }
