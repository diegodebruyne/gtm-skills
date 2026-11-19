# -*- coding: utf-8 -*-
"""Regression tests for the report contract. Run: python test_validate_report.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_manifest as rm
import validate_report as vr
import finalize_report as fr

GOOD = "In plain words: everything is in order. Evidence: 12 leads re-read, 0 anomalies, numeric proof"


def build(moment="precheck", statuses=None, finding=GOOD, **flags):
    ids = rm.expected(moment, **flags)
    statuses = dict(statuses or {})
    rows = []
    counts = {s: 0 for s in rm.STATUSES}
    current_section = None
    for i in ids:
        if moment == "precheck":
            section = "Leads" if i.startswith("L") else "Sequence and copy" if i.startswith("C") else "Senders"
            if section != current_section:
                rows += ["## " + section, "", "| # | Check | Result | Evidence and finding |", "|---:|---|---|---|"]
                current_section = section
        st = statuses.get(i, "✅")
        counts[st] += 1
        c = "N/A - not applicable to this campaign" if st == "N/A" else finding
        rows.append("| %s | %s | %s | %s |" % (i, rm.CHECKS[i], st, c))
    if moment == "precheck":
        rows += [
            "", "### E1 detail: mailboxes", "",
            "| Mailbox | Score | Spam 14 d | Lemwarm | Connection | DNS/blacklist | Verdict |",
            "|---|---:|---:|---|---|---|---|",
            "| sender@example.com | 95 | 1.2% | active | connected | compliant | ✅ |",
        ]
    summary = " · ".join("%s %d" % (s, counts[s]) for s in rm.STATUSES)
    open_ids = [i for i in ids if statuses.get(i, "✅") in ("🔴", "⚠️", "❓", "🖐️")]
    blocked = any(statuses.get(i, "✅") in ("🔴", "❓") for i in ids)
    verdict = "Verdict: **%s - short reason.**" % ("BLOCKED" if blocked else "READY FOR THE NEXT STEP")
    actions = ["### Actions to take", "", "| # | Level | Problem | Owner | Exact action |", "|---:|---|---|---|---|"]
    for n, i in enumerate(open_ids, 1):
        actions.append("| %d | %s | %s: to handle | Owner | decide |" % (n, statuses[i], i))
    na = counts["N/A"]
    return "\n".join(rows) + "\n\n**Summary: %s**\n\n**%d checks expected, %d executed, %d not applicable.**\n\n%s\n\n%s\n" % (
        summary, len(ids), len(ids) - na, na, verdict, "\n".join(actions))


def errs(text, moment="precheck", **kw):
    return vr.validate(text, moment, **kw)


def has(es, needle):
    return any(needle in e for e in es)


def main():
    # 1. a clean report passes, for every moment
    assert errs(build()) == [], errs(build())
    assert errs(build("post_draft"), "post_draft") == []
    assert errs(build("post_import"), "post_import") == []
    assert errs(build(existing_campaign=True), existing_campaign=True) == []
    assert errs(build(blacklist=False, linkedin=False), blacklist=False, linkedin=False) == []

    # 2. a missing check is refused
    t = build()
    t2 = "\n".join(l for l in t.splitlines() if not l.startswith("| L9 |"))
    assert has(errs(t2), "L9 missing"), errs(t2)

    # 3. a duplicate is refused
    t3 = t.replace("| L3 |", "| L2 | duplicate | ✅ | In plain words: ok. Evidence: 12 leads re-read, 0 anomalies |\n| L3 |", 1)
    assert has(errs(t3), "L2 duplicated"), errs(t3)

    # 4. a check from a later stage is refused (P1 in a pre-check)
    t4 = t.replace("| L3 |", "| P1 | Complete import | ✅ | In plain words: ok. Evidence: 12 leads re-read, 0 anomalies |\n| L3 |", 1)
    assert has(errs(t4), "P1 does not belong"), errs(t4)

    # 5. old numbering and suffixed IDs are refused
    t5 = t.replace("| L3 |", "| Check 14 | Mailboxes | ✅ | In plain words: ok. Evidence: 12 leads re-read, 0 anomalies |\n| L3 |", 1)
    assert has(errs(t5), "old numbering"), errs(t5)
    t5b = t.replace("| C1 |", "| C1-FR | Architecture | ✅ | In plain words: ok. Evidence: 12 leads re-read, 0 anomalies |\n| C1 |", 1)
    assert has(errs(t5b), "suffixed ID"), errs(t5b)
    t5c = t.replace("| L3 |", "| 17/27 | Unsubscribe | ✅ | In plain words: ok. Evidence: 12 leads re-read, 0 anomalies |\n| L3 |", 1)
    assert has(errs(t5c), "old numbering"), errs(t5c)

    # 6. invalid status or "not run"
    name = rm.CHECKS["L1"]
    t6 = t.replace("| L1 | %s | ✅ |" % name, "| L1 | %s | ✅ with waiver |" % name)
    assert has(errs(t6), "invalid status"), errs(t6)
    t6b = t.replace("| L1 | %s | ✅ |" % name, "| L1 | %s | not run |" % name)
    assert has(errs(t6b), "invalid status"), errs(t6b)

    # 7. a ✅ that hides a reservation
    t7 = build(finding="In plain words: ok. Evidence: 0 anomalies but exception declared by the agent")
    assert has(errs(t7), "hides a reservation"), errs(t7)

    # 8. N/A without a reason, empty finding
    t8 = build(statuses={"C8bis": "N/A"}).replace("N/A - not applicable to this campaign", "N/A")
    assert has(errs(t8), "N/A without a reason"), errs(t8)
    t8b = t.replace("| L2 | %s | ✅ | %s |" % (rm.CHECKS["L2"], GOOD), "| L2 | %s | ✅ | ok |" % rm.CHECKS["L2"])
    assert has(errs(t8b), "L2: finding empty"), errs(t8b)

    # 9. wrong totals
    t9 = t.replace("%d checks expected" % len(rm.expected("precheck")), "46 checks expected")
    assert has(errs(t9), "announced total"), errs(t9)
    t9b = build(statuses={"L4": "❓"}).replace("Summary: ✅", "Summary: ✅ 99 · ✅", 1)
    assert errs(t9b), "a wrong summary must be refused"
    t9c = build(statuses={"L4": "❓"}).replace("❓ 1", "❓ 2")
    assert has(errs(t9c), "Summary"), errs(t9c)

    # 10. verdict READY with a ❓ or a 🔴
    t10 = build(statuses={"L4": "❓"}).replace("BLOCKED", "READY FOR THE NEXT STEP")
    assert has(errs(t10), "verdict READY"), errs(t10)

    # 11. verdict before the checks
    good = build(statuses={"L4": "❓"})
    vline = [l for l in good.splitlines() if l.startswith("Verdict")][0]
    t11 = vline + "\n\n" + good.replace(vline, "")
    assert has(errs(t11), "after the verdict") or has(errs(t11), "missing"), errs(t11)

    # 12. a ⚠️ row absent from the actions
    t12 = build(statuses={"L5": "⚠️"})
    t12 = "\n".join(l for l in t12.splitlines() if "L5: to handle" not in l)
    assert has(errs(t12), "L5 (⚠️) missing"), errs(t12)

    # 13. input already answered: ❓ forbidden unless "new fact"
    t13 = build(statuses={"L9": "❓"})
    assert has(errs(t13, answered=("I6",)), "already answered"), errs(t13, answered=("I6",))
    t13b = build(statuses={"L4": "❓"}, finding="In plain words: new fact: a lead already replied in the account. Evidence: export")
    assert not has(errs(t13b, answered=("I5",)), "already answered"), errs(t13b, answered=("I5",))

    # 14. verdict or actions missing
    t14 = "\n".join(l for l in good.splitlines() if not l.startswith("Verdict"))
    assert has(errs(t14), "verdict missing"), errs(t14)
    t14b = good.replace("### Actions to take", "### Something else")
    assert has(errs(t14b), "Actions to take"), errs(t14b)

    # 15. "L1" must not satisfy "L11" in the actions
    t15 = build(statuses={"L1": "⚠️", "L11": "⚠️"})
    t15 = "\n".join(l for l in t15.splitlines() if "| L1:" not in l)
    assert has(errs(t15), "L1 (⚠️) missing"), errs(t15)

    # 16. finding without "In plain words:"
    t16 = build(finding="12 leads re-read, 0 anomalies, numeric proof")
    assert has(errs(t16), "In plain words"), errs(t16)

    # 17. false greens seen in practice, and missing evidence label
    for bad in [
        "In plain words: all good. Evidence: LinkedIn page 116/189, 73 empty",
        "In plain words: all good. Evidence: 73 missing values out of 189",
        "In plain words: all good except three companies above the cap. Evidence: file re-read",
    ]:
        assert has(errs(build(finding=bad)), "hides a reservation"), (bad, errs(build(finding=bad)))
    assert has(errs(build(finding="In plain words: all good, 189 leads re-read")), "Evidence:")

    # 18. BLOCKED without a blocker, missing sections and E1 detail
    t18 = build().replace("READY FOR THE NEXT STEP", "BLOCKED")
    assert has(errs(t18), "BLOCKED without"), errs(t18)
    t18b = build().replace("## Leads", "## Other")
    assert has(errs(t18b), "required section missing"), errs(t18b)
    t18c = "\n".join(line for line in build().splitlines() if "sender@example.com" not in line)
    assert has(errs(t18c), "mailbox-by-mailbox"), errs(t18c)

    # 19. inconsistent action level
    t19 = build(statuses={"L5": "⚠️"}).replace("| 1 | ⚠️ | L5: to handle", "| 1 | ❓ | L5: to handle")
    assert has(errs(t19), "action level"), errs(t19)

    # 20. the finalizer writes nothing when the report is refused
    with tempfile.TemporaryDirectory() as td:
        draft = Path(td) / "draft.md"
        final = Path(td) / "final.md"
        draft.write_text(build(), encoding="utf-8")
        assert fr.main(["--draft", str(draft), "--output", str(final), "--moment", "precheck"]) == 0
        assert final.read_text(encoding="utf-8") == draft.read_text(encoding="utf-8")
        final.unlink()
        draft.write_text(build(finding="In plain words: all good. Evidence: 73 missing values"), encoding="utf-8")
        assert fr.main(["--draft", str(draft), "--output", str(final), "--moment", "precheck"]) == 1
        assert not final.exists()

    # 21. a green row that cites a DATED decision on a known gap is valid
    decided = "In plain words: the gap is known and accepted. Evidence: 3 values missing, decision by the sender owner on 19/11"
    assert errs(build(finding=decided)) == [], errs(build(finding=decided))
    assert errs(build(finding=decided.replace("decision by the sender owner on 19/11", "accepted"))), "no dated decision: must be refused"

    # 22. an 'Actions to take' row without an action is refused
    t22 = build(statuses={"L5": "⚠️"}).replace("| Owner | decide |", "| Owner | no action needed |")
    assert has(errs(t22), "without an action"), errs(t22)

    print("OK: all report-validator tests pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
