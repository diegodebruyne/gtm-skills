# -*- coding: utf-8 -*-
"""Validate a draft report and publish it only when the contract accepts it."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_report as vr


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--moment", required=True, choices=["precheck", "post_draft", "post_import"])
    ap.add_argument("--no-blacklist", action="store_true")
    ap.add_argument("--no-extra-fields", action="store_true")
    ap.add_argument("--no-linkedin", action="store_true")
    ap.add_argument("--no-ab", action="store_true")
    ap.add_argument("--existing-campaign", action="store_true")
    ap.add_argument("--answered", default="")
    a = ap.parse_args(argv)

    draft = Path(a.draft).resolve()
    output = Path(a.output).resolve()
    if draft == output:
        print("REPORT REFUSED: draft and final output must be different files.")
        return 1
    text = draft.read_text(encoding="utf-8")
    errors = vr.validate(
        text,
        a.moment,
        not a.no_blacklist,
        not a.no_extra_fields,
        not a.no_linkedin,
        not a.no_ab,
        a.existing_campaign,
        tuple(x.strip() for x in a.answered.split(",") if x.strip()),
    )
    if errors:
        print("REPORT REFUSED: %d issue(s). No final report written." % len(errors))
        for error in errors:
            print(" - " + error)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print("REPORT ACCEPTED AND FINALIZED: %s" % output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
