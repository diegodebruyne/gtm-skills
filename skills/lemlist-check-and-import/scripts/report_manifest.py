"""Canonical public report manifest for the 37 documented checks."""
import argparse

CHECKS = {i: "Check %d" % i for i in range(1, 38)}
STATUSES = ["✅", "🔴", "⚠️", "❓", "🖐️", "N/A"]
INPUT_TO_CHECK = {}


def expected(moment, *_, **__):
    if moment == "precheck":
        return [str(i) for i in range(1, 36)]
    if moment == "post_draft":
        return [str(i) for i in range(26, 36)]
    if moment == "post_import":
        return ["36", "37"]
    raise ValueError("unknown moment: %s" % moment)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moment", required=True, choices=["precheck", "post_draft", "post_import"])
    a = ap.parse_args()
    for check_id in expected(a.moment):
        print("| %s | Check %s | | |" % (check_id, check_id))


if __name__ == "__main__":
    main()
