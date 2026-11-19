# -*- coding: utf-8 -*-
"""Report manifest: ONE check numbering (L, C, E, D, P) and the exact list of checks expected at each moment.

This file is the single source of truth. `validate_report.py` refuses any report that departs from it.

Moments:
  precheck     before any write (copy, leads, senders, and, for an existing target campaign, its live settings)
  post_draft   after a NEW campaign structure was created as a draft
  post_import  after the leads were imported

Conditions (defaults in brackets):
  blacklist (yes)         : L9 exists only when a blacklist applies
  extra_fields (yes)      : L10 exists only when the campaign defines extra required fields
  linkedin (yes)          : C8bis exists only when the sequence has LinkedIn messages
  ab (yes)                : C9 exists only when the sequence has an email 1
  existing_campaign (no)  : the target campaign ALREADY exists, so the checks that read its live state (D2, D5, D7) are required in the
                            pre-check. D1, D3, D4, D6 get no row of their own: D1 = not applicable (nothing written), D3 = E1 + E2,
                            D4 = E3, D6 = C7.

Usage: python report_manifest.py --moment precheck [--existing-campaign] [--no-blacklist] [--no-extra-fields] [--no-linkedin] [--no-ab]
       prints the table skeleton to fill (one row per ID, never two IDs merged, never a language suffix).
"""
import argparse
import sys

CHECKS = {
    # Leads
    "L1": "Variables and fallbacks",
    "L2": "Available channels and routing",
    "L3": "Duplicates inside the batch",
    "L4": "Leads already in Lemlist",
    "L5": "Email addresses",
    "L6": "Identity quality",
    "L7": "Language of lead, campaign and variables",
    "L8": "Contacts per company",
    "L9": "Blacklist",
    "L10": "Required extra fields",
    "L11": "Native company fields",
    # Sequence and copy
    "C1": "Architecture and email threads",
    "C2": "Delays",
    "C3": "Liquid syntax, fallbacks and agreements",
    "C4": "LinkedIn continuity",
    "C5": "Personalized content composition",
    "C6": "Signatures per channel and spacing",
    "C7": "Unsubscribe",
    "C8": "Whitespace and paragraph rendering",
    "C8bis": "LinkedIn media",
    "C9": "Email 1 A/B",
    "C10": "Hard-coded links",
    "C11": "Register and cross-language consistency",
    "C12": "Subject quality",
    "C13": "Spelling and typography",
    # Senders
    "E1": "Sending mailbox health",
    "E2": "Mailbox coverage per sender",
    "E3": "Capacity available before the draft",
    # After the draft is created (or live read of an existing campaign)
    "D1": "Source / Lemlist match",
    "D2": "Reply, tracking and stop settings",
    "D3": "Senders and connections",
    "D4": "Schedule and capacity",
    "D5": "Labels",
    "D6": "Real signatures and unsubscribe",
    "D7": "Lemlist readiness",
    # After the import
    "P1": "Complete import",
    "P2": "Variables on 100% of the batch",
    "P3": "Lemlist renders",
    "P4": "Real routing",
    "P5": "CRM sync",
}

# Setup input -> check it drives. An input already answered is never reopened as a question without "new fact".
INPUT_TO_CHECK = {"I4": "L5", "I5": "L4", "I6": "L9", "I7": "L8", "I8": "L10"}

STATUSES = ["✅", "🔴", "⚠️", "❓", "🖐️", "N/A"]


def expected(moment, blacklist=True, extra_fields=True, linkedin=True, ab=True, existing_campaign=False):
    ids = []
    if moment == "precheck":
        ids += ["L%d" % i for i in range(1, 12)]
        ids += ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C8bis", "C9", "C10", "C11", "C12", "C13"]
        ids += ["E1", "E2", "E3"]
        if existing_campaign:
            ids += ["D2", "D5", "D7"]
    elif moment == "post_draft":
        ids += ["D%d" % i for i in range(1, 8)]
    elif moment == "post_import":
        ids += ["P%d" % i for i in range(1, 6)]
    else:
        raise ValueError("unknown moment: %s" % moment)
    if not blacklist:
        ids = [i for i in ids if i != "L9"]
    if not extra_fields:
        ids = [i for i in ids if i != "L10"]
    if not linkedin:
        ids = [i for i in ids if i != "C8bis"]
    if not ab:
        ids = [i for i in ids if i != "C9"]
    return ids


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--moment", required=True, choices=["precheck", "post_draft", "post_import"])
    ap.add_argument("--no-blacklist", action="store_true")
    ap.add_argument("--no-extra-fields", action="store_true")
    ap.add_argument("--no-linkedin", action="store_true")
    ap.add_argument("--no-ab", action="store_true")
    ap.add_argument("--existing-campaign", action="store_true")
    a = ap.parse_args(argv)
    ids = expected(a.moment, not a.no_blacklist, not a.no_extra_fields, not a.no_linkedin, not a.no_ab, a.existing_campaign)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("| # | Check | Result | Evidence and finding |")
    print("|---:|---|---|---|")
    for i in ids:
        print("| %s | %s | | |" % (i, CHECKS[i]))
    print("\n%d checks expected." % len(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
