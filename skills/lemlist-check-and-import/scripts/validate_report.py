# -*- coding: utf-8 -*-
"""Completeness validator for a check report: no more inflated or incomplete reports.

A report that fails here is NOT shown: the agent fixes it first. Exit code 1 = refused.

Rules enforced:
  1. every check expected at the given moment (report_manifest.py) appears EXACTLY once; no duplicate, no unknown ID, no ID from another moment;
  2. one numbering only: no "Check 14", "17/27" or "C1-FR" rows (one row per ID; languages are mentioned inside the finding);
  3. the status is exactly ✅ 🔴 ⚠️ ❓ 🖐️ or N/A (nothing else in the cell); "not run" is not a status;
  4. a ✅ hides no reservation (exception, waiver, to confirm, not verified, partial, accepted by) unless it cites a dated decision
     ("decision by <name> on 19/11"); an N/A gives its reason;
  5. every finding starts with "In plain words:" (one sentence anybody can follow: what is checked, why it is fine or not), then "Evidence:" with the
     technical detail;
  6. the line "X checks expected, X executed, X not applicable" and the "Summary:" line match the real rows;
  7. the verdict comes AFTER all checks; READY is forbidden while a 🔴 or ❓ remains; the "Actions to take" table comes AFTER the verdict, lists every
     ID left 🔴 ⚠️ ❓ or 🖐️, and never contains a row without an action;
  8. an input that was already answered (--answered I4,I5,...) is not reopened as ❓ unless the finding says "new fact".

Usage: python validate_report.py --report report.md --moment precheck [--existing-campaign] [--no-blacklist] [--no-extra-fields] [--no-linkedin] [--no-ab]
                                 [--answered I4,I5,I6,I7,I8]
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_manifest as rm

ID_RE = re.compile(r"^[LCEDP]\d+(bis)?$")
SUFFIXED_RE = re.compile(r"^[LCEDP]\d+(bis)?\s*[-/·]\s*\S+")
OLD_RE = re.compile(r"^(check|control)\s*\d|^\d+(\s*/\s*\d+)*\b|^M\d+\b", re.I)
RESERVE_RE = re.compile(r"exception|waiver|waived|to confirm|not verified|unverified|not re-?checked|partial|accepted by", re.I)
MISSING_RE = re.compile(r"\b([1-9]\d*)\s+(?:values?\s+)?(?:empty|missing|absent|incomplete|not covered)\b", re.I)
DECIDED_RE = re.compile(r"decision (?:by|of) [^.;:]{0,80}?\d{1,2}/\d{1,2}", re.I)
NEGATIVE_RE = re.compile(r"\b(?:except|but|however|although)\b|\b(?:missing|empty|incomplete|not covered|gap|error|anomaly)\b", re.I)
NO_ACTION_RE = re.compile(r"no action|nothing to do|nothing to decide|no decision", re.I)


def norm_status(s):
    s = s.replace("️", "").strip()
    for st in rm.STATUSES:
        if s == st.replace("️", ""):
            return st
    return None


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def clean_id(c):
    return c.replace("*", "").replace("`", "").strip()


def green_contradiction(check_id, finding):
    """Return the suspicious fragment when a PASS sentence contradicts itself."""
    m = RESERVE_RE.search(finding) or MISSING_RE.search(finding)
    if m:
        return m.group(0)
    # Remove explicit zero/absence statements before looking for negative wording.
    cleaned = re.sub(r"\b0\s+(?:[\w-]+\s+){0,3}(?:empty|missing|absent|errors?|anomal(?:y|ies)|gaps?)\b", "", finding, flags=re.I)
    cleaned = re.sub(r"\b(?:no|without)\s+(?:[\w-]+\s+){0,3}(?:missing|empty|error|anomaly|gap|problem)\b", "", cleaned, flags=re.I)
    m = NEGATIVE_RE.search(cleaned)
    if m:
        return m.group(0)
    # L11 covers mandatory company-field coverage: a partial ratio cannot be green.
    if check_id == "L11":
        for got, total in re.findall(r"\b(\d+)\s*/\s*(\d+)\b", finding):
            if int(total) > 0 and int(got) < int(total):
                return "%s/%s" % (got, total)
    return None


def validate(text, moment, blacklist=True, extra_fields=True, linkedin=True, ab=True, existing_campaign=False, answered=()):
    errors = []
    lines = text.splitlines()
    exp = rm.expected(moment, blacklist, extra_fields, linkedin, ab, existing_campaign)

    # landmarks: verdict, actions
    verdict_idx = next((i for i, l in enumerate(lines) if re.match(r"^\W*Verdict\s*:", l.strip().replace("*", ""), re.I)), None)
    actions_idx = next((i for i, l in enumerate(lines) if re.search(r"Actions to take", l) and l.lstrip().startswith("#")), None)
    if verdict_idx is None:
        errors.append("verdict missing (\"Verdict: **READY FOR THE NEXT STEP | BLOCKED - reason.**\" after all checks)")
    if actions_idx is None:
        errors.append("'Actions to take' table missing (heading \"Actions to take\")")
    limit = min([x for x in (verdict_idx, actions_idx) if x is not None] or [len(lines)])

    rows = {}  # id -> (status, finding, name)
    row_positions = {}
    seen = []
    last_check_line = -1
    for i, l in enumerate(lines[:limit]):
        if not l.strip().startswith("|"):
            continue
        c = cells(l)
        if len(c) < 3:
            continue
        first = clean_id(c[0])
        if first in ("#", "---:", "---", "Check", "Mailbox") or set(first) <= set("-: "):
            continue
        if SUFFIXED_RE.match(first):
            errors.append("line %d: suffixed ID \"%s\": one row per ID, languages go inside the finding" % (i + 1, first))
            continue
        if ID_RE.match(first):
            last_check_line = i
            seen.append(first)
            if first in rows:
                continue
            status = norm_status(c[2]) if len(c) > 2 else None
            finding = " | ".join(c[3:]).strip() if len(c) > 3 else ""
            if status is None:
                errors.append("%s: invalid status \"%s\" (✅ 🔴 ⚠️ ❓ 🖐️ or N/A, nothing else in the cell)" % (first, c[2] if len(c) > 2 else ""))
            rows[first] = (status, finding, c[1] if len(c) > 1 else "")
            row_positions[first] = i
        elif OLD_RE.match(first):
            errors.append("line %d: old numbering \"%s\": use the single L/C/E/D/P taxonomy" % (i + 1, first))

    # 1. exact presence
    for i in exp:
        n = seen.count(i)
        if n == 0:
            errors.append("%s missing (check expected at this moment)" % i)
        elif n > 1:
            errors.append("%s duplicated (%d rows)" % (i, n))
    for i in set(seen):
        if i not in exp:
            errors.append("%s does not belong to this moment (\"%s\")" % (i, moment))

    # 3 to 5: row content
    for i, (st, finding, name) in rows.items():
        if st is None:
            continue
        if st == "N/A":
            if len(finding) < 10:
                errors.append("%s: N/A without a reason (write \"N/A - reason\")" % i)
            continue
        if len(finding) < 15:
            errors.append("%s: finding empty or without evidence" % i)
        elif not finding.lstrip("* ").startswith("In plain words:"):
            errors.append("%s: the finding must start with \"In plain words:\" + one simple sentence (what is checked, why it is fine or not), then \"Evidence:\" + the technical detail" % i)
        if "Evidence:" not in finding:
            errors.append("%s: \"Evidence:\" label missing" % i)
        # A green row that cites a DATED decision by the user on a gap or incomplete coverage is valid: it is not a problem, it was decided.
        decided = bool(DECIDED_RE.search(finding))
        contradiction = green_contradiction(i, finding) if (st == "✅" and not decided) else None
        if contradiction:
            errors.append("%s: ✅ that hides a reservation (\"%s\"): use ⚠️, ❓ or 🔴, or cite the dated decision (\"decision by <name> on dd/mm\")" % (i, contradiction))
        if st == "❓":
            for inp, chk in rm.INPUT_TO_CHECK.items():
                if chk == i and inp in answered and "new fact" not in finding.lower():
                    errors.append("%s: ❓ on an input already answered (%s): quote the answer, or write \"new fact: ...\"" % (i, inp))

    # 6: sections and totals
    if moment == "precheck":
        required_headings = ["## Leads", "## Sequence and copy", "## Senders", "### E1 detail: mailboxes"]
        heading_positions = []
        for heading in required_headings:
            pos = next((n for n, line in enumerate(lines) if line.strip() == heading), None)
            if pos is None:
                errors.append("required section missing: %s" % heading)
            heading_positions.append(pos)
        if all(p is not None for p in heading_positions) and heading_positions != sorted(heading_positions):
            errors.append("pre-check sections are in the wrong order")
        if all(p is not None for p in heading_positions):
            leads_pos, copy_pos, senders_pos, mailbox_pos = heading_positions
            for cid, pos in row_positions.items():
                if cid.startswith("L") and not (leads_pos < pos < copy_pos):
                    errors.append("%s must be in the Leads section" % cid)
                elif cid.startswith("C") and not (copy_pos < pos < senders_pos):
                    errors.append("%s must be in the Sequence and copy section" % cid)
                elif (cid.startswith("E") or cid.startswith("D")) and not (senders_pos < pos < mailbox_pos):
                    errors.append("%s must be in the Senders section" % cid)
            e1_status = rows.get("E1", (None, "", ""))[0]
            mailbox_rows = []
            for line in lines[mailbox_pos + 1:limit]:
                if line.startswith("##"):
                    break
                if line.strip().startswith("|"):
                    c = cells(line)
                    if len(c) == 7 and clean_id(c[0]) not in ("Mailbox", "---", "---:") and not set(clean_id(c[0])) <= set("-: "):
                        mailbox_rows.append(c)
            if e1_status != "N/A" and not mailbox_rows:
                errors.append("E1: mailbox-by-mailbox table missing or incomplete (7 columns expected)")

    counts = {s: 0 for s in rm.STATUSES}
    for i, (st, _, _) in rows.items():
        if st in counts and i in exp:
            counts[st] += 1
    m = re.search(r"(\d+)\s+checks expected\s*,\s*(\d+)\s+executed\s*,\s*(\d+)\s+not applicable", text, re.I)
    if not m:
        errors.append("line \"X checks expected, X executed, X not applicable\" missing")
    else:
        att, exe, so = map(int, m.groups())
        if att != len(exp):
            errors.append("announced total %d != %d checks expected at this moment" % (att, len(exp)))
        if exe + so != att:
            errors.append("%d executed + %d not applicable != %d expected" % (exe, so, att))
        if so != counts["N/A"]:
            errors.append("%d not applicable announced != %d N/A rows" % (so, counts["N/A"]))
    b = re.search(r"Summary\s*:\s*(.+)", text)
    if not b:
        errors.append("line \"Summary: ✅ n · 🔴 n · ⚠️ n · ❓ n · 🖐️ n · N/A n\" missing")
    else:
        got = {}
        for sym, n in re.findall(r"(✅|🔴|⚠️?|❓|🖐️?|N/A)\s*(\d+)", b.group(1)):
            if norm_status(sym) in got:
                errors.append("Summary: status %s appears twice" % sym)
            got[norm_status(sym)] = int(n)
        for st in rm.STATUSES:
            if got.get(st, 0) != counts[st]:
                errors.append("Summary: %s announced %d, real rows %d" % (st, got.get(st, 0), counts[st]))

    # 7: order and verdict
    if verdict_idx is not None:
        if last_check_line > verdict_idx:
            errors.append("a check appears after the verdict")
        v = lines[verdict_idx].upper()
        ready = "READY FOR THE NEXT STEP" in v
        blocked = "BLOCKED" in v
        if not ready and not blocked:
            errors.append("invalid verdict: use exactly READY FOR THE NEXT STEP or BLOCKED")
        if ready and (counts["🔴"] or counts["❓"]):
            errors.append("verdict READY while %d 🔴 and %d ❓ remain" % (counts["🔴"], counts["❓"]))
        if blocked and not (counts["🔴"] or counts["❓"]):
            errors.append("verdict BLOCKED without any 🔴 or ❓")
    if verdict_idx is not None and actions_idx is not None and actions_idx < verdict_idx:
        errors.append("'Actions to take' must come AFTER the verdict")
    if actions_idx is not None:
        action_rows = []
        for line in lines[actions_idx + 1:]:
            if not line.strip().startswith("|"):
                continue
            c = cells(line)
            if len(c) == 5 and c[0] not in ("#", "---:") and not set(c[0]) <= set("-: "):
                action_rows.append(c)
        for c in action_rows:  # a row without an action is not an action
            if NO_ACTION_RE.search(c[4]):
                errors.append("'Actions to take' row without an action (\"%s\"): not an action. A point already decided is a ✅ with the decision cited; if there is nothing to do it does not belong in this table" % c[4].strip()[:60])
        for i, (st, _, _) in rows.items():
            if st in ("🔴", "⚠️", "❓", "🖐️"):
                matches = [c for c in action_rows if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(i), c[2])]
                if not matches:
                    errors.append("%s (%s) missing from the 'Actions to take' table" % (i, st))
                elif not any(norm_status(c[1]) == st for c in matches):
                    errors.append("%s: action level differs from status %s" % (i, st))
                elif any(len(c[3].strip()) < 2 or len(c[4].strip()) < 5 for c in matches):
                    errors.append("%s: owner or exact action missing" % i)
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--moment", required=True, choices=["precheck", "post_draft", "post_import"])
    ap.add_argument("--no-blacklist", action="store_true")
    ap.add_argument("--no-extra-fields", action="store_true")
    ap.add_argument("--no-linkedin", action="store_true")
    ap.add_argument("--no-ab", action="store_true")
    ap.add_argument("--existing-campaign", action="store_true")
    ap.add_argument("--answered", default="", help="inputs already answered, e.g. I4,I5,I6,I7,I8")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text = Path(a.report).read_text(encoding="utf-8")
    errs = validate(text, a.moment, not a.no_blacklist, not a.no_extra_fields, not a.no_linkedin, not a.no_ab, a.existing_campaign,
                    tuple(x.strip() for x in a.answered.split(",") if x.strip()))
    if errs:
        print("REPORT REFUSED: %d issue(s). Fix them before showing the report." % len(errs))
        for e in errs:
            print(" - " + e)
        return 1
    print("REPORT ACCEPTED: expected checks, totals, verdict and actions are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
