# -*- coding: utf-8 -*-
"""Company-level duplicates: companies of the batch that already exist in the Lemlist account.

The policy is a SETUP QUESTION asked at the start of every campaign (never a silent default):
  all         : exclude every company already in the account
  replied     : exclude only companies where someone replied or is interested
  interested  : exclude only companies where someone is interested
  none        : exclude nothing (free re-contact); matches are still listed

Re-contacting the SAME PERSON stays forbidden in every case (see dedupe_before_pay.py).

Match rule (strict on purpose, so there is little to review by hand):
  ONLY the same full domain name OR the same company LinkedIn page. example-hotel.com and example-hotel.be are two different domains and do
  not match; a similar company name does not count.
  Common-sense exception: a domain SHARED by several establishments (a hotel chain's own domain used by many properties) identifies a group,
  not one property. It never causes an exclusion; it is only reported as information ("another property of the same group has a reply").

Usage:
  python company_dedupe.py --input companies.json --policy replied --decision "<the user's own words, date>" --out <run>/company_dedupe.json \
         --key-env LEMLIST_API_KEY --env-file <local .env>
  companies.json: list of objects with name (or companyName), domain (or companyDomain), linkedin (or companyLinkedinUrl).
"""
import argparse
import collections
import json
import re
import sys
import unicodedata
import urllib.parse
from datetime import datetime
from pathlib import Path

POLICIES = ("all", "replied", "interested", "none")
INTENT_STATES = {"emailsReplied", "linkedinReplied", "emailsInterested", "linkedinInterested", "meetingBooked"}
INTERESTED_STATES = {"emailsInterested", "linkedinInterested", "meetingBooked"}


def nname(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def ndomain(s):
    s = urllib.parse.unquote(str(s or "")).lower().strip()
    s = re.sub(r"^https?://", "", s).split("/")[0].split("?")[0]
    return s[4:] if s.startswith("www.") else s


def co_slug(u):
    m = re.search(r"linkedin\.com/company/([^/?#]+)", str(u or "").lower())
    if not m:
        return ""
    return unicodedata.normalize("NFKD", urllib.parse.unquote(m.group(1))).encode("ascii", "ignore").decode().lower()


def classify(r):
    """interested > replied > contacted, from the fields of a Lemlist lead export."""
    st, ls = (r.get("status") or ""), (r.get("lastState") or "")
    if st == "interested" or ls in INTERESTED_STATES:
        return "interested"
    if ls in INTENT_STATES or (r.get("lastRepliedDate") or "").strip():
        return "replied"
    return "contacted"


def build_index(account):
    """account: list of (campaign name, lead). Shared domains = used by at least two different company names."""
    idx = {"dom": collections.defaultdict(list), "li": collections.defaultdict(list)}
    names_by_dom = collections.defaultdict(set)
    for camp, r in account:
        n = nname(r.get("companyName"))
        d = ndomain(r.get("companyDomain"))
        s = co_slug(r.get("companyLinkedinUrl"))
        e = (camp, r)
        if d:
            idx["dom"][d].append(e)
            names_by_dom[d].add(n)
        if s:
            idx["li"][s].append(e)
    idx["shared"] = {d for d, ns in names_by_dom.items() if len({x for x in ns if x}) >= 2}
    return idx


def match_company(c, idx, lot_domains=None):
    """Return (strong, weak). Strong = same company LinkedIn page or same non-shared domain. Weak = shared domain (group): information only."""
    dom = ndomain(c.get("domain") or c.get("companyDomain"))
    slug = co_slug(c.get("linkedin") or c.get("companyLinkedinUrl"))
    strong, weak, seen = [], [], set()
    if slug:
        for e in idx["li"].get(slug, []):
            k = (e[0], e[1].get("email") or e[1].get("linkedinUrl") or id(e[1]))
            if k not in seen:
                seen.add(k)
                strong.append((e[0], e[1], "same company LinkedIn page"))
    if dom and dom in idx["dom"]:
        shared = dom in idx["shared"] or (lot_domains and lot_domains.get(dom, 0) >= 2)
        for e in idx["dom"][dom]:
            k = (e[0], e[1].get("email") or e[1].get("linkedinUrl") or id(e[1]))
            if k in seen:
                continue
            seen.add(k)
            if shared:
                weak.append((e[0], e[1], "domain shared by several properties (group): %s" % dom))
            else:
                strong.append((e[0], e[1], "same domain: %s" % dom))
    return strong, weak


def worst(entries):
    order = {"interested": 2, "replied": 1, "contacted": 0}
    return max((classify(r) for _, r, _ in entries), key=lambda k: order[k]) if entries else "none"


def decide(policy, strong):
    """Return (verdict, reason): "exclude" or "keep"."""
    if policy not in POLICIES:
        raise ValueError("unknown policy: %s" % policy)
    ws = worst(strong)
    if strong:
        if policy == "all":
            return "exclude", "already in the account (%s): policy \"all\"" % ws
        if policy == "replied" and ws in ("replied", "interested"):
            return "exclude", "someone replied or is interested: policy \"replied\""
        if policy == "interested" and ws == "interested":
            return "exclude", "someone is interested: policy \"interested\""
    return "keep", ("present in the account, kept by policy \"%s\"" % policy) if strong else ""


def evidence(entries, limit=6):
    out = []
    for camp, r, why in entries[:limit]:
        out.append({"campaign": camp, "person": ((r.get("firstName") or "") + " " + (r.get("lastName") or "")).strip() or (r.get("email") or ""),
                    "state": classify(r), "reason": why})
    return out


def run(companies, account, policy, decision, scanned_at=None):
    idx = build_index(account)
    lot_domains = collections.Counter(ndomain(c.get("domain") or c.get("companyDomain")) for c in companies if ndomain(c.get("domain") or c.get("companyDomain")))
    res = {"policy": policy, "decision": decision, "scanned_at": scanned_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
           "account_leads": len(account), "companies": len(companies), "excluded": [], "present_kept": [], "same_group_information": []}
    for c in companies:
        strong, weak = match_company(c, idx, lot_domains)
        if not strong and not weak:
            continue
        verdict, why = decide(policy, strong)
        row = {"company": c.get("name") or c.get("companyName"), "reason": why, "strong_evidence": evidence(strong), "weak_evidence": evidence(weak)}
        if verdict == "exclude":
            res["excluded"].append(row)
        elif strong:
            res["present_kept"].append(row)
        group = [e for e in weak if e[2].startswith("domain shared")]
        if group and verdict != "exclude" and worst(group) in ("replied", "interested"):
            res["same_group_information"].append({"company": row["company"], "evidence": evidence(group, 3)})
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--policy", required=True, choices=POLICIES)
    ap.add_argument("--decision", required=True, help="the user's own words that set the policy for THIS campaign")
    ap.add_argument("--out", required=True)
    ap.add_argument("--key-env", required=True)
    ap.add_argument("--env-file")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import account_control as ac
    api = ac.Lemlist(ac.key_from_env(a.key_env, a.env_file))
    account = []
    for c in api.campaigns():
        cid = c.get("_id") or c.get("id")
        for r in api.leads(cid):
            account.append((c.get("name"), r))
    companies = json.loads(Path(a.input).read_text(encoding="utf-8"))
    res = run(companies, account, a.policy, a.decision)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Company duplicates (policy \"%s\"): %d account leads read, %d companies checked | excluded %d | present and kept %d | same group with a reply (information) %d" % (
        a.policy, res["account_leads"], res["companies"], len(res["excluded"]), len(res["present_kept"]), len(res["same_group_information"])))
    for r in res["excluded"]:
        print("  EXCLUDED: %s | %s" % (r["company"], r["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
