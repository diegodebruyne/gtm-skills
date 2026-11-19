# -*- coding: utf-8 -*-
"""Tests for company_dedupe.py (fictional data only). Run: python test_company_dedupe.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import company_dedupe as cd

ACCOUNT = [
    ("Campaign A", {"firstName": "Ann", "lastName": "Example", "companyName": "Alpha Hotel", "companyDomain": "www.alpha-hotel.com",
                    "companyLinkedinUrl": "https://www.linkedin.com/company/alpha-hotel", "lastState": "emailsReplied"}),
    ("Campaign A", {"firstName": "Bob", "lastName": "Sample", "companyName": "Beta Suites", "companyDomain": "beta-suites.com",
                    "companyLinkedinUrl": "", "lastState": "emailsInterested"}),
    ("Campaign A", {"firstName": "Cy", "lastName": "Demo", "companyName": "Gamma Inn", "companyDomain": "gamma-inn.com", "lastState": "emailsSent"}),
    ("Campaign B", {"firstName": "Di", "lastName": "Test", "companyName": "Chain Paris", "companyDomain": "chain.com", "lastState": "emailsReplied"}),
    ("Campaign B", {"firstName": "Ed", "lastName": "Test", "companyName": "Chain Lyon", "companyDomain": "chain.com", "lastState": "emailsSent"}),
]
COMPANIES = [
    {"name": "Alpha Hotel", "domain": "alpha-hotel.com"},                       # same domain
    {"name": "Alpha (page only)", "domain": "other.com", "linkedin": "https://be.linkedin.com/company/Alpha-Hotel"},  # same LinkedIn page
    {"name": "Beta Suites", "domain": "beta-suites.com"},
    {"name": "Gamma Inn", "domain": "gamma-inn.com"},
    {"name": "Alpha Hotel (other country)", "domain": "alpha-hotel.be"},        # different domain: passes
    {"name": "Chain Marseille", "domain": "chain.com"},                          # shared domain: information only
]


def names(rows, key="company"):
    return sorted(r[key] for r in rows)


def main():
    r = cd.run(COMPANIES, ACCOUNT, "all", "test")
    assert "Alpha Hotel (other country)" not in names(r["excluded"]), "a different domain must pass"
    assert "Chain Marseille" not in names(r["excluded"]), "a shared domain never excludes"
    assert names(r["excluded"]) == ["Alpha (page only)", "Alpha Hotel", "Beta Suites", "Gamma Inn"], names(r["excluded"])

    r = cd.run(COMPANIES, ACCOUNT, "replied", "test")
    assert names(r["excluded"]) == ["Alpha (page only)", "Alpha Hotel", "Beta Suites"], names(r["excluded"])
    assert names(r["present_kept"]) == ["Gamma Inn"], names(r["present_kept"])

    r = cd.run(COMPANIES, ACCOUNT, "interested", "test")
    assert names(r["excluded"]) == ["Beta Suites"], names(r["excluded"])

    r = cd.run(COMPANIES, ACCOUNT, "none", "test")
    assert r["excluded"] == [] and len(r["present_kept"]) == 4

    r = cd.run(COMPANIES, ACCOUNT, "replied", "test")
    assert names(r["same_group_information"]) == ["Chain Marseille"], r["same_group_information"]

    try:
        cd.decide("bogus", [])
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown policy must be refused")
    print("OK: company_dedupe tests pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
