#!/usr/bin/env python3
"""A stand-in for `claude -p` so the eval harness can be tested without spending anything.

It reads the arm's SKILL.md from the `--plugin-dir` it was given, finds a line
`fake-scenario: <name>`, and plays `$FAKE_CLAUDE_SCENARIOS/<name>.json`:

    {"files": {"index.html": "..."},      written into the cwd before the events
     "home_files": {"notes/house.jsonl": "..."},   appended under $DDR_HOME
     "events": [ ...stream-json events... ],
     "sleep": 0, "exit": 0, "stderr": ""}

An init event is always printed first. Its skills list carries `dd:design-director` only
when a plugin with that skill was passed, so the isolation grader can be tested honestly.
If `$FAKE_CLAUDE_ARGV_LOG` is set, the argv is appended to it as one JSON line.
"""
import json
import os
import pathlib
import re
import sys
import time

argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print("9.9.9 (fake claude)")
    sys.exit(0)

log = os.environ.get("FAKE_CLAUDE_ARGV_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "ddr_home": os.environ.get("DDR_HOME")}) + "\n")


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


plugin = opt("--plugin-dir")
skills = ["dataviz", "update-config"]
scenario = "empty"
if plugin:
    for skill_md in pathlib.Path(plugin).glob("skills/*/SKILL.md"):
        skills.insert(0, "dd:" + skill_md.parent.name)
        m = re.search(r"fake-scenario:\s*(\S+)", skill_md.read_text(encoding="utf-8"))
        if m:
            scenario = m.group(1)
extra = os.environ.get("FAKE_CLAUDE_EXTRA_SKILLS")
if extra:
    skills += extra.split(",")

data = {"events": []}
scen_dir = os.environ.get("FAKE_CLAUDE_SCENARIOS")
if scen_dir and (pathlib.Path(scen_dir) / f"{scenario}.json").exists():
    data = json.loads((pathlib.Path(scen_dir) / f"{scenario}.json").read_text(encoding="utf-8"))

# what an agent would record through ddr (domain log, notes, taste): into whatever DDR_HOME it was given
for rel, text in data.get("home_files", {}).items():
    p = pathlib.Path(os.environ["DDR_HOME"]) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(text)

for rel, text in data.get("files", {}).items():
    p = pathlib.Path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def emit(e):
    sys.stdout.write(json.dumps(e) + "\n")
    sys.stdout.flush()


emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "skills": skills,
      "tools": ["Bash", "Edit", "Glob", "Grep", "Read", "Skill", "Write"], "model": opt("--model") or "fake"})
for e in data.get("events", []):
    emit(e)
if data.get("stderr"):
    sys.stderr.write(data["stderr"])
time.sleep(float(data.get("sleep", 0)))
sys.exit(int(data.get("exit", 0)))
