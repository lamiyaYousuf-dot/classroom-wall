# Learning Integrity Agent

Some learners now let AI agents or auto-play tools "watch" video courses for them. The course gets
marked complete, the dashboard looks great, and nobody learned anything. This agent looks at your
**LinkedIn Learning** and **Udemy Business** activity exports, finds the completions that don't look
like a person was watching, and writes a report you can act on:

- who to follow up with, most concerning first, with the evidence in plain language and the innocent
  explanations it ruled in or out
- a short **verification check** (3–5 applied questions) for each course worth checking. Someone who
  followed the course can answer in ten minutes; someone whose agent played it in a background tab can't
- a friendly, non-accusatory message to send to flagged learners
- program changes that take away the reason to fake completions

It doesn't watch or click anything on the platforms. It only reads the reports you export.

## How it decides what looks wrong

The local checks in `signals.py` run first, with no AI involved:

| Signal | What it means | Weight |
| --- | --- | --- |
| `OVERLAPPING_VIEWING` | Two courses "watched" at the same time. People can't; an agent running several tabs can | 4 |
| `FASTER_THAN_POSSIBLE` | Finished faster than the runtime allows even at 2x | 4 |
| `BINGE_DAY` | 4+ courses or 6+ hours of content completed in one day | 3 |
| `LOW_WATCH_RATIO` | Marked complete but watched under 60% of the runtime | 2 |
| `UNBROKEN_MARATHON` | A 90+ minute course finished in one sitting that matches the runtime almost to the minute, with no pauses | 2 |
| `WEAK_ASSESSMENT` | Completed, but the quiz score is under 50% | 2 |
| `DEADLINE_RUSH` | Most completions packed into the 48 h before a deadline (`--deadline`) | 2 |
| `SKIPPED_ASSESSMENT` | The course has a quiz that wasn't attempted | 1 |
| `OFF_HOURS` | Completed between midnight and 5am | 1 |

Scores add up per learner: **high** is 8 or more, **medium** is 4–7, and **low** is everything else.
Then the agent (Claude) reads the flagged learners' records through four read-only tools, weighs the
evidence and writes the report. You can change the thresholds in `Settings` in `signals.py`.

**These are signals, not proof.** People watch at 2x, skip material they already know, and study late
at night. Use the report to start a conversation or run a verification check. Don't use it to
discipline anyone.

## Privacy

Names and emails stay on your computer. Claude only sees references like `L007` plus course titles,
durations, timestamps and scores. Add `--share-names` if you want real names next to the references in
the saved report. That swap happens locally after the agent is done.

## Setup

```bash
cd learning-integrity-agent
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## Exporting the data

- **LinkedIn Learning**: Admin → Reports → *Learner detail* (or *Content activity*) → Export CSV.
  Include course duration, hours viewed, first engagement and completion dates.
- **Udemy Business**: Manage → Reports → *User activity* / *Course activity* → Export CSV. Include
  minutes video consumed, first accessed and completion dates, plus quiz or assessment columns if you
  have them.

**Include timestamps (date and time), not just dates.** Without them the overlap and speed checks
can't run. The report will tell you when that's the case.

Column names vary between report types. The loader recognises the common headers for both
platforms (see `ALIASES` in `loaders.py`). If yours aren't recognised, map them with a JSON file:

```json
{ "course": "Learning Item", "watched": "Total Minutes", "completed_at": "Finished On" }
```

```bash
python agent.py export.csv --column-map my_columns.json
```

## Usage

```bash
# Full report from both platforms
python agent.py linkedin.csv udemy.csv --share-names

# Try it on the included sample data
python agent.py sample_data/*.csv --share-names -v

# Local checks only (no API call), useful for a quick look
python agent.py sample_data/*.csv --offline --share-names

# Flag rushes before a compliance deadline
python agent.py linkedin.csv --deadline 2026-09-30T23:59

# Ask a specific question
python agent.py udemy.csv --ask "Which courses should get a verification quiz, and what should it ask?"
```

Reports are saved to `reports/integrity-<date>.md` (change this with `--out`). `--effort` trades depth
for speed and cost (`high` by default), and `-v` prints each tool call the agent makes.

The sample data has four suspicious patterns: Jordan Lee (five compliance courses played in parallel
tabs), Taylor Brooks (18 hours back to back until 4am, every quiz skipped), Sam Patel (skipped to the
end) and Riley Ahmed (fast finish and a failed quiz). It also has genuine learners, including Priya
Nair's one late-night study session, which should *not* be flagged.

## Model

The agent uses `claude-opus-5-5` with adaptive thinking. Server-side refusal fallback
(`fallbacks: "default"`) is turned on, so if a request gets declined it's retried on another model.
To change the model, edit `MODEL` in `agent.py`.

## Tests

```bash
pip install pytest
python -m pytest -q tests
```

The tests cover parsing, the signals on the sample data, the pseudonymisation and the agent's tool
loop, using a fake client so they don't call the API.

## Beyond detection

Detection only catches the obvious cases. The lasting fix is to make passive completion pointless:

- stop rewarding raw completion counts and hours watched
- require the platforms' built-in quizzes, hands-on exercises or labs to count a course as done
- add a short "apply it" task (a reflection, a work sample, a conversation with a manager)
- measure outcomes, like skills assessments and on-the-job changes, rather than minutes consumed
