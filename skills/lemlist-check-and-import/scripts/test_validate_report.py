"""Regression tests for the public report contract."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_manifest as rm
import validate_report as vr


def build(finding="In plain English: compliant. Evidence: 100 rows checked, 0 anomalies.", statuses=None):
    statuses = statuses or {}
    ids = rm.expected("precheck")
    counts = {status: 0 for status in rm.STATUSES}
    rows = ["| # | Check | Status | Evidence |", "|---:|---|---|---|"]
    actions = []
    for check_id in ids:
        status = statuses.get(check_id, "✅")
        counts[status] += 1
        rows.append("| %s | Check %s | %s | %s |" % (check_id, check_id, status, finding))
        if status in ("🔴", "⚠️", "❓", "🖐️"):
            actions.append("| %d | %s | %s: issue | Owner | Resolve the issue |" % (len(actions) + 1, status, check_id))
    summary = " · ".join("%s %d" % (status, counts[status]) for status in rm.STATUSES)
    blocked = counts["🔴"] or counts["❓"]
    verdict = "BLOCKED" if blocked else "READY FOR THE NEXT STEP"
    return "\n".join(rows + [
        "", "Summary: " + summary,
        "%d checks expected, %d executed, %d not applicable" % (len(ids), len(ids) - counts["N/A"], counts["N/A"]),
        "Verdict: **%s — reason.**" % verdict,
        "### Actions to take", "",
        "| # | Level | Problem | Owner | Exact action |", "|---:|---|---|---|---|",
        *actions,
    ])


def main():
    assert vr.validate(build(), "precheck") == []
    for bad in [
        "In plain English: compliant. Evidence: 73 values missing.",
        "In plain English: compliant except three companies. Evidence: checked.",
    ]:
        assert vr.validate(build(bad), "precheck")
    assert vr.validate(build("In plain English: compliant, 100 rows checked."), "precheck")
    blocked_without_issue = build().replace("READY FOR THE NEXT STEP", "BLOCKED")
    assert vr.validate(blocked_without_issue, "precheck")
    print("OK: public report-validator regression tests pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
