"""Read LinkedIn Learning and Udemy Business activity exports into one common shape.

Both platforms let admins export learner activity as CSV, but the column names
differ between platforms (and sometimes between report types and years). Each
field below lists the header names we recognise; matching ignores case, spaces
and punctuation. If your export uses a header we don't know, pass a column map
(see README) instead of editing this file.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ALIASES: dict[str, list[str]] = {
    "learner_id": ["learner id", "user id", "employee id", "unique user id", "email", "user email", "learner email"],
    "name": ["learner name", "user name", "name", "full name"],
    "first_name": ["first name"],
    "last_name": ["last name"],
    "email": ["email", "user email", "learner email", "email address"],
    "course": ["content title", "course title", "course name", "course", "title"],
    "content_type": ["content type", "type"],
    "duration": ["content duration", "course duration", "duration", "course length", "length",
                 "content length", "estimated duration"],
    "watched": ["hours viewed", "minutes viewed", "seconds viewed", "time viewed", "minutes video consumed",
                "video minutes consumed", "minutes consumed", "time spent", "viewing time", "watch time"],
    "percent": ["percent completed", "percent complete", "completion ratio", "completion percentage",
                "progress", "% complete", "completion"],
    "completed": ["completed", "is completed", "completion status", "status"],
    "started_at": ["first engagement date", "first viewed", "course first accessed date", "first accessed",
                   "start date", "started date", "enrolled date", "course enroll date"],
    "last_at": ["last engagement date", "last viewed", "last accessed date", "last activity date"],
    "completed_at": ["completed date", "completion date", "course completion date", "date completed",
                     "completed at"],
    "assessment": ["assessment score", "quiz score", "exam score", "score", "assessment result"],
    "assessment_available": ["has assessment", "assessment available", "has quiz"],
}

DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p", "%d/%m/%Y %H:%M",
    "%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%b %d, %Y",
]


@dataclass
class Record:
    """One learner's activity on one course."""

    platform: str
    learner_id: str
    name: str
    email: str
    course: str
    duration_min: float | None
    watched_min: float | None
    percent: float | None
    completed: bool
    started_at: datetime | None
    last_at: datetime | None
    completed_at: datetime | None
    assessment: float | None
    assessment_available: bool | None
    has_time_of_day: bool = False
    raw: dict = field(default_factory=dict, repr=False)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", s.lower())


def _find_columns(headers: list[str], overrides: dict[str, str]) -> dict[str, str]:
    by_norm = {_norm(h): h for h in headers}
    found: dict[str, str] = {}
    for key, aliases in ALIASES.items():
        if key in overrides:
            if overrides[key] not in headers:
                raise ValueError(f"Column map says {key!r} is {overrides[key]!r}, but the file has no such column.")
            found[key] = overrides[key]
            continue
        for alias in aliases:
            if _norm(alias) in by_norm:
                found[key] = by_norm[_norm(alias)]
                break
    return found


def parse_minutes(value: str, header: str = "") -> float | None:
    """Turn '1h 23m', '01:23:00', '83 minutes', '1.5' (hours column) etc. into minutes."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v or v in {"-", "n/a", "na", "none"}:
        return None
    if re.fullmatch(r"\d+:\d{1,2}(:\d{1,2})?", v):
        parts = [int(p) for p in v.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] * 60 + parts[1] + parts[2] / 60
    units = re.findall(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", v)
    if units:
        total = 0.0
        for num, unit in units:
            n = float(num)
            total += n * 60 if unit.startswith("h") else n / 60 if unit.startswith("s") else n
        return total
    try:
        n = float(v.replace(",", ""))
    except ValueError:
        return None
    h = header.lower()
    if "hour" in h:
        return n * 60
    if "second" in h:
        return n / 60
    return n


def parse_percent(value: str) -> float | None:
    if value is None or not str(value).strip():
        return None
    v = str(value).strip().rstrip("%")
    try:
        n = float(v)
    except ValueError:
        return None
    return n * 100 if n <= 1.0 and "." in v else n


def parse_date(value: str) -> tuple[datetime | None, bool]:
    """Returns (datetime, has_time_of_day)."""
    if value is None or not str(value).strip():
        return None, False
    v = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(v, fmt)
            return dt, ("%H" in fmt or "%I" in fmt)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
        return dt, "T" in v or ":" in v
    except ValueError:
        return None, False


def parse_bool(value: str) -> bool | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"y", "yes", "true", "1", "completed", "complete", "done", "passed"}:
        return True
    if v in {"n", "no", "false", "0", "in progress", "not started", "incomplete", "not completed"}:
        return False
    return None


def detect_platform(headers: list[str]) -> str:
    joined = " ".join(_norm(h) for h in headers)
    if "minutesvideoconsumed" in joined or "courseenrolldate" in joined or "completionratio" in joined:
        return "udemy"
    if "contenttitle" in joined or "hoursviewed" in joined or "firstengagementdate" in joined:
        return "linkedin"
    return "unknown"


def load_report(path: str | Path, platform: str = "auto", column_map: str | Path | None = None) -> list[Record]:
    overrides = json.loads(Path(column_map).read_text()) if column_map else {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        cols = _find_columns(headers, overrides)
        if platform == "auto":
            platform = detect_platform(headers)
        if "course" not in cols:
            raise ValueError(f"{path}: couldn't find a course/content title column. Headers: {headers}")
        if "learner_id" not in cols and "name" not in cols and "first_name" not in cols:
            raise ValueError(f"{path}: couldn't find a learner id, email or name column. Headers: {headers}")

        def get(row: dict, key: str) -> str | None:
            return row.get(cols[key]) if key in cols else None

        records = []
        for row in reader:
            name = (get(row, "name") or " ".join(filter(None, [get(row, "first_name"), get(row, "last_name")]))).strip()
            email = (get(row, "email") or "").strip()
            learner_id = (get(row, "learner_id") or email or name).strip()
            course = (get(row, "course") or "").strip()
            if not learner_id or not course:
                continue
            ctype = (get(row, "content_type") or "").strip().lower()
            if ctype and ctype not in {"course", "video", "learning path", "path"}:
                continue  # skip articles, books, audio etc.
            percent = parse_percent(get(row, "percent"))
            started, t1 = parse_date(get(row, "started_at"))
            last, t2 = parse_date(get(row, "last_at"))
            completed_at, t3 = parse_date(get(row, "completed_at"))
            completed_flag = parse_bool(get(row, "completed"))
            if completed_flag is None:
                completed_flag = bool(completed_at) or (percent is not None and percent >= 99.5)
            records.append(Record(
                platform=platform,
                learner_id=learner_id,
                name=name or learner_id,
                email=email,
                course=course,
                duration_min=parse_minutes(get(row, "duration"), cols.get("duration", "")),
                watched_min=parse_minutes(get(row, "watched"), cols.get("watched", "")),
                percent=percent,
                completed=completed_flag,
                started_at=started,
                last_at=last,
                completed_at=completed_at,
                assessment=parse_percent(get(row, "assessment")),
                assessment_available=parse_bool(get(row, "assessment_available")),
                has_time_of_day=t1 or t2 or t3,
                raw=row,
            ))
    return records
