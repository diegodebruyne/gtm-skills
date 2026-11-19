# -*- coding: utf-8 -*-
"""Progress tracker for the lemlist-check-and-import workflow.

Why: the user should never have to ask "where are we?" or "what do I do now?". One state file per run; the agent updates a step the moment it
changes and shows `show` at the top of every message to the user.

Eight fixed steps. The three APPROVALS (draft architecture, import of the exact batch, launch) are the only mandatory stops; everything else
chains on its own without asking.
  1 check             Check the copy and the leads (validated pre-check report)
  2 structure         Create the Lemlist campaigns (only if they do not exist yet)
  3 dossier           Import dossier (dry run of the exact batch: duplicates, caps, mapping)
  4 import_approval   APPROVAL to import THIS exact batch into THIS campaign
  5 import            Import the leads (they wait in "review", nothing is sent)
  6 post_import       Post-import checks (+ optional reply test)
  7 launch_approval   APPROVAL to launch THIS batch
  8 launch            Launch, then read the status back

States: done | in_progress | todo | waiting_user | not_needed

An approval can only be set to "done" with the user's own words in --note (at least 5 characters). It is never inferred from "continue".

Usage:
  python progression.py init --dir <run>
  python progression.py set  --dir <run> --step 5 --state done --note "182 leads imported, 83 + 99"
  python progression.py show --dir <run>
"""
import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

STEPS = [
    ("check", "Check the copy and the leads"),
    ("structure", "Create the Lemlist campaigns (only if they do not exist yet)"),
    ("dossier", "Import dossier (dry run of the exact batch)"),
    ("import_approval", "APPROVAL to import (user)"),
    ("import", "Import the leads (in review, nothing is sent)"),
    ("post_import", "Post-import checks (+ optional reply test)"),
    ("launch_approval", "APPROVAL to launch (user)"),
    ("launch", "Launch"),
]
STATES = ("done", "in_progress", "todo", "waiting_user", "not_needed")
ICON = {"done": "✅", "in_progress": "🔶", "todo": "⏳", "waiting_user": "⏸️", "not_needed": "➖"}
LABEL = {"done": "done", "in_progress": "in progress", "todo": "to do", "waiting_user": "waiting for you", "not_needed": "not needed"}
APPROVALS = ("import_approval", "launch_approval")

# One light line when a step succeeds. Never shown on an error, a blocker or a serious decision.
HUMOR = {
    "check": "All checks passed: the copy and the leads were inspected more thoroughly than a passenger at the airport.",
    "structure": "Structure settled: the campaigns now stand up on their own.",
    "dossier": "Import dossier ready: tidier than a Monday-morning spreadsheet.",
    "import_approval": "Approval received: a real green light, not one of those orange ones that pretend.",
    "import": "Import finished: everybody got on the bus and nobody forgot their bag.",
    "post_import": "Post-import checks OK: even the variables were verified one by one.",
    "launch_approval": "Launch approval given: engines on, seat belts fastened.",
    "launch": "Lift-off: now the prospects can reply (or not, but with style).",
}

# Paraphrases of ideas from Marcus Aurelius, "Meditations", written from memory. They are NOT exact translations and are always labelled so.
MARCUS = {
    "check": ["The quality of your life depends on the quality of your thoughts.", "The soul takes on the color of its thoughts.", "See things as they are, not as it suits you to see them."],
    "structure": ["Do nothing at random, or without a purpose.", "Lay each stone as if the building had to last."],
    "dossier": ["Stop discussing what a good person should be: be one.", "What is not good for the hive is not good for the bee."],
    "import_approval": ["If it is not right, do not do it; if it is not true, do not say it.", "Act with seriousness and justice, without haste."],
    "import": ["Do each act as if it were the last of your day.", "Do one thing at a time, and do it well."],
    "post_import": ["You have power over your judgment, not over events: understand this and you will be strong.", "Verify before you trust: appearance is not the thing itself."],
    "launch_approval": ["When you struggle to get up, tell yourself: I am getting up to do a human being's work.", "Do what depends on you without waiting; leave the rest to fate."],
    "launch": ["The obstacle on the path becomes the path.", "What stands in the way of the action advances the action.", "Do what has to be done and accept the result calmly."],
}


def humor(step):
    return HUMOR.get(step, "")


def quote(step):
    options = MARCUS.get(step)
    return random.choice(options) if options else ""


def path(run):
    return Path(run) / "progress.json"


def load(run):
    p = path(run)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"steps": {k: {"state": "todo", "note": "", "date": ""} for k, _ in STEPS}}


def save(run, data):
    p = path(run)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def key_of(arg):
    """Accept the step number (1 to 8) or its key."""
    if arg.isdigit() and 1 <= int(arg) <= len(STEPS):
        return STEPS[int(arg) - 1][0]
    if arg in dict(STEPS):
        return arg
    raise SystemExit("unknown step: %s (1 to %d or %s)" % (arg, len(STEPS), ", ".join(k for k, _ in STEPS)))


def next_step(data):
    """(key, label, reason) of the next thing to do; a pending approval comes first."""
    for k, label in STEPS:
        s = data["steps"][k]["state"]
        if s == "waiting_user":
            return k, label, "waiting for you"
        if s in ("in_progress", "todo"):
            if s == "in_progress":
                return k, label, "in progress"
            return k, label, "approval to ask from the user" if k in APPROVALS else "to do, the agent chains it on its own"
    return None, "everything is done", ""


def show(run):
    data = load(run)
    lines = ["| # | Step | State | Note |", "|---:|---|---|---|"]
    for n, (k, label) in enumerate(STEPS, 1):
        s = data["steps"][k]
        lines.append("| %d | %s | %s %s | %s |" % (n, label, ICON[s["state"]], LABEL[s["state"]], s.get("note", "")))
    k, label, why = next_step(data)
    lines.append("")
    lines.append("**Next step: %s (%s).**" % (label, why) if k else "**All steps are done.**")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "show", "set"):
        s = sub.add_parser(name)
        s.add_argument("--dir", required=True)
        if name == "set":
            s.add_argument("--step", required=True)
            s.add_argument("--state", required=True, choices=STATES)
            s.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "init":
        if not path(a.dir).exists():
            save(a.dir, load(a.dir))
        print("progress initialized:", path(a.dir))
    elif a.cmd == "set":
        data = load(a.dir)
        k = key_of(a.step)
        if k in APPROVALS and a.state == "done" and len(a.note.strip()) < 5:
            raise SystemExit("REFUSED: an approval is set to done only with the user's own words in --note.")
        data["steps"][k] = {"state": a.state, "note": a.note, "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
        save(a.dir, data)
        print("step %s: %s" % (k, a.state))
        if a.state == "done" and humor(k):
            print("😄 " + humor(k))
        if a.state == "done" and quote(k):
            print("🏛️ \"%s\" (Marcus Aurelius, Meditations, paraphrase)" % quote(k))
    print(show(a.dir) if a.cmd in ("show", "set") else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
